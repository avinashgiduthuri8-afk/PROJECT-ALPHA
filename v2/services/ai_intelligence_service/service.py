"""
V2 AI Intelligence Service.

Acts as an independent quantitative and LLM-assisted confirmation gate
between the Market Scanner and Trade Construction / Risk Engine.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.types import AIAnalysis, AIRecommendation, Priority, Signal
from v2.core.logging import get_logger
from v2.repository.ai_repo import AIAnalysisRepository
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.signal_repo import SignalRepository

from .client import GeminiClient
from .evaluator import FallbackEvaluator

logger = get_logger("v2.services.ai_intelligence_service")


class AIIntelligenceService:
    """Coordinates AI-driven signal evaluation, confirmation gating, and persistence."""

    def __init__(
        self,
        bus: EventBus,
        ai_repo: AIAnalysisRepository,
        event_log_repo: EventLogRepository,
        config: V2Config,
        signal_repo: Optional[SignalRepository] = None,
    ) -> None:
        self._bus = bus
        self._ai_repo = ai_repo
        self._event_log = event_log_repo
        self._config = config
        self._signal_repo = signal_repo

        self._client: Optional[GeminiClient] = None
        if self._config.gemini_api_key:
            self._client = GeminiClient(
                api_key=self._config.gemini_api_key,
                model=self._config.v2_ai_model,
                timeout_seconds=self._config.v2_ai_timeout_seconds,
                max_retries=self._config.v2_ai_max_retries,
            )

        self._min_priority = Priority(self._config.v2_ai_min_priority)
        self._total_evaluations = 0
        self._confirmed_count = 0
        self._rejected_count = 0
        self._fallback_count = 0
        self._latencies: list[float] = []
        self._last_error: Optional[str] = None
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe event bus handlers."""
        if self._started:
            return
        self._started = True
        self._bus.subscribe(EventType.SIGNAL_GENERATED, self.on_signal_generated)
        await self._bus.publish(
            EventType.SYSTEM_STARTUP,
            {"service": "ai_intelligence_service", "model": self._config.v2_ai_model},
        )
        logger.info("AIIntelligenceService started", extra={"model": self._config.v2_ai_model})

    async def stop(self) -> None:
        """Unsubscribe handlers."""
        self._started = False
        self._bus.unsubscribe(EventType.SIGNAL_GENERATED, self.on_signal_generated)
        logger.info("AIIntelligenceService stopped")

    # ── Signal Evaluation Core ────────────────────────────────────────────────

    async def evaluate_signal(self, signal: Signal) -> AIAnalysis:
        """
        Evaluate a candidate signal through Gemini API or Fallback Evaluator,
        persist analysis, and publish confirmation/rejection events.
        """
        t0 = time.perf_counter()
        analysis: Optional[AIAnalysis] = None
        used_fallback = False

        if self._config.v2_ai_enabled and self._client is not None:
            try:
                analysis = await self._client.evaluate_signal(signal)
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning(
                    "Gemini evaluation failed; falling back to heuristic evaluator",
                    extra={"coin": signal.coin, "error": str(exc)},
                )
                used_fallback = True
                analysis = FallbackEvaluator.evaluate(signal, start_time=t0)
        else:
            used_fallback = True
            analysis = FallbackEvaluator.evaluate(signal, start_time=t0)

        if used_fallback:
            self._fallback_count += 1

        self._total_evaluations += 1
        self._latencies.append(analysis.execution_latency_ms)
        if len(self._latencies) > 200:
            self._latencies.pop(0)

        # 1. Persist analysis
        await self._ai_repo.insert(analysis)

        # 2. Publish SIGNAL_AI_EVALUATED
        eval_payload = {
            "analysis_id": analysis.id,
            "signal_id": signal.id,
            "coin": signal.coin,
            "pair": signal.pair,
            "recommendation": analysis.recommendation.value,
            "confidence_score": analysis.confidence_score,
            "model_name": analysis.model_name,
            "setup_quality": analysis.setup_quality,
            "latency_ms": analysis.execution_latency_ms,
        }
        await self._bus.publish(EventType.SIGNAL_AI_EVALUATED, eval_payload)

        # 3. Confirmation vs Rejection Gating
        is_confirmed = (
            analysis.recommendation in (AIRecommendation.APPROVE, AIRecommendation.SCALE_DOWN)
            and analysis.confidence_score >= self._config.v2_ai_confidence_threshold
        )

        raw_p = signal.raw_payload or {}
        price = float(raw_p.get("price") or raw_p.get("close") or 0.0)
        bot = signal.source_bot if signal.source_bot in ("STE", "HDA", "VCP", "BBS") else raw_p.get("bot", "STE")

        if is_confirmed:
            self._confirmed_count += 1
            confirm_payload = {
                "signal_id": signal.id,
                "analysis_id": analysis.id,
                "coin": signal.coin,
                "pair": signal.pair,
                "price": price,
                "market_state": signal.market_state.value,
                "opportunity_type": signal.opportunity_type.value,
                "bot": bot,
                "recommendation": analysis.recommendation.value,
                "confidence_score": analysis.confidence_score,
                "suggested_adjustments": analysis.suggested_adjustments,
                "model_name": analysis.model_name,
            }
            await self._bus.publish(EventType.SIGNAL_AI_CONFIRMED, confirm_payload)
            await self._event_log.append(
                event_type=EventType.SIGNAL_AI_CONFIRMED.value,
                source_service="ai_intelligence_service",
                entity_id=signal.id,
                payload=confirm_payload,
            )
            logger.info(
                "Signal AI confirmed",
                extra={"coin": signal.coin, "rec": analysis.recommendation.value, "conf": analysis.confidence_score},
            )
        else:
            self._rejected_count += 1
            reject_payload = {
                "signal_id": signal.id,
                "analysis_id": analysis.id,
                "coin": signal.coin,
                "pair": signal.pair,
                "price": price,
                "market_state": signal.market_state.value,
                "opportunity_type": signal.opportunity_type.value,
                "bot": bot,
                "recommendation": analysis.recommendation.value,
                "confidence_score": analysis.confidence_score,
                "conflicts": analysis.conflicts,
                "risk_factors": analysis.risk_factors,
                "model_name": analysis.model_name,
            }
            await self._bus.publish(EventType.SIGNAL_AI_REJECTED, reject_payload)
            await self._event_log.append(
                event_type=EventType.SIGNAL_AI_REJECTED.value,
                source_service="ai_intelligence_service",
                entity_id=signal.id,
                payload=reject_payload,
            )
            logger.info(
                "Signal AI rejected / gated",
                extra={"coin": signal.coin, "rec": analysis.recommendation.value, "conf": analysis.confidence_score},
            )

        return analysis

    # ── Bus Event Handlers ────────────────────────────────────────────────────

    async def on_signal_generated(self, event_type: EventType, payload: dict) -> None:
        """Handle incoming signal from scanner and evaluate if priority criteria is met."""
        try:
            signal_id = payload.get("signal_id") or payload.get("id")
            if not signal_id and self._signal_repo:
                return

            signal: Optional[Signal] = None
            if self._signal_repo and signal_id:
                signal = await self._signal_repo.get_by_id(signal_id)

            if signal is None:
                # Construct temporary Signal from payload dictionary
                from v2.services.scanner_service.adapter import v1_signal_to_domain
                signal = v1_signal_to_domain(payload)

            if signal.priority.gte(self._min_priority):
                await self.evaluate_signal(signal)
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("Error processing SIGNAL_GENERATED in AIIntelligenceService", exc_info=True)

    # ── Telemetry & Health ────────────────────────────────────────────────────

    def get_health(self) -> dict:
        """Return health, latency, and throughput statistics."""
        avg_lat = round(sum(self._latencies) / len(self._latencies), 2) if self._latencies else 0.0
        return {
            "healthy": self._started,
            "ai_enabled": self._config.v2_ai_enabled,
            "model": self._config.v2_ai_model,
            "has_api_key": bool(self._config.gemini_api_key),
            "min_priority": self._min_priority.value,
            "confidence_threshold": self._config.v2_ai_confidence_threshold,
            "total_evaluations": self._total_evaluations,
            "confirmed_count": self._confirmed_count,
            "rejected_count": self._rejected_count,
            "fallback_count": self._fallback_count,
            "avg_latency_ms": avg_lat,
            "last_error": self._last_error,
        }
