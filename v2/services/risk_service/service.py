"""
V2 RiskService — centralized risk gatekeeper and capital manager.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.types import (
    BotName,
    OppType,
    PositionStatus,
    RiskDecision,
    RiskState,
    Signal,
)
from v2.core.logging import get_logger
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository

from .capital_guard import CapitalGuard
from .circuit_breaker import CircuitBreaker

logger = get_logger("v2.services.risk_service")


class RiskService:
    """Manages trade permission checks, capital allocation, and breaker states."""

    def __init__(
        self,
        bus: EventBus,
        position_repo: PositionRepository,
        trade_repo: TradeRepository,
        event_log_repo: EventLogRepository,
        config: V2Config,
    ) -> None:
        self._bus = bus
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._event_log = event_log_repo
        self._config = config

        self._capital_guard = CapitalGuard(config)
        self._circuit_breaker = CircuitBreaker(config)
        self._started = False

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def capital_guard(self) -> CapitalGuard:
        return self._capital_guard

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._bus.subscribe(EventType.SIGNAL_AI_CONFIRMED, self.on_signal_ai_confirmed)
        self._bus.subscribe(EventType.POSITION_CLOSED, self.on_position_closed)
        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "risk_service"})
        logger.info("RiskService started")

    async def stop(self) -> None:
        self._started = False
        self._bus.unsubscribe(EventType.SIGNAL_AI_CONFIRMED, self.on_signal_ai_confirmed)
        self._bus.unsubscribe(EventType.POSITION_CLOSED, self.on_position_closed)
        logger.info("RiskService stopped")

    # ── Trade Permission Evaluation ───────────────────────────────────────────

    async def check_trade_allowed(
        self,
        bot: BotName,
        requested_amount: float,
    ) -> RiskDecision:
        """Run complete risk evaluation (CircuitBreaker + CapitalGuard) against live repository state."""
        # 1. Circuit breaker check
        breaker_dec = self._circuit_breaker.check_breaker(bot, requested_amount)
        if not breaker_dec.allowed:
            return breaker_dec

        # 2. Query live open positions for deployed capital
        open_positions = await self._position_repo.get_open_by_bot(bot)
        all_open = await self._position_repo.get_open()

        bot_deployed = sum(p.deployed_capital for p in open_positions)
        total_deployed = sum(p.deployed_capital for p in all_open)
        bot_pos_count = len(open_positions)

        # 3. CapitalGuard evaluation
        return self._capital_guard.check_trade(
            bot=bot,
            requested_amount=requested_amount,
            current_bot_deployed=bot_deployed,
            total_deployed=total_deployed,
            current_bot_positions=bot_pos_count,
        )

    # ── Event Handlers ────────────────────────────────────────────────────────

    async def on_signal_ai_confirmed(self, event_type: EventType, payload: dict) -> None:
        """Evaluate trade feasibility for an AI-confirmed candidate signal."""
        try:
            signal_id = payload.get("signal_id")
            coin = payload.get("coin", "UNKNOWN")
            pair = payload.get("pair") or f"B-{coin}_USDT"
            ai_adjustments = payload.get("suggested_adjustments") or {}
            
            # Select target bot strategy archetype
            bot = self._select_bot_for_signal(payload)
            default_amount = self._get_default_amount_for_bot(bot)

            # Apply AI position size scaling multiplier
            size_multiplier = float(ai_adjustments.get("size_multiplier", 1.0))
            scaled_amount = max(0.0, default_amount * size_multiplier)

            decision = await self.check_trade_allowed(bot, scaled_amount)

            if decision.allowed:
                approved_payload = {
                    "signal_id": signal_id,
                    "coin": coin,
                    "pair": pair,
                    "bot": bot.value,
                    "approved_amount": decision.adjusted_amount,
                    "ai_adjustments": ai_adjustments,
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                }
                await self._bus.publish(EventType.TRADE_APPROVED, approved_payload)
                await self._event_log.append(
                    event_type=EventType.TRADE_APPROVED.value,
                    source_service="risk_service",
                    entity_id=signal_id,
                    payload=approved_payload,
                )
                logger.info("Trade APPROVED by risk engine", extra={"coin": coin, "bot": bot.value, "amount": decision.adjusted_amount})
            else:
                denied_payload = {
                    "signal_id": signal_id,
                    "coin": coin,
                    "pair": pair,
                    "bot": bot.value,
                    "requested_amount": scaled_amount,
                    "code": decision.code,
                    "reason": decision.reason,
                    "denied_at": datetime.now(timezone.utc).isoformat(),
                }
                await self._bus.publish(EventType.TRADE_DENIED, denied_payload)
                if decision.code in ("BLOCKED_BOT_CAPITAL", "BLOCKED_TOTAL_CAPITAL"):
                    await self._bus.publish(EventType.CAPITAL_LIMIT_HIT, denied_payload)
                elif decision.code in ("BLOCKED_CIRCUIT_BREAKER", "BLOCKED_EMERGENCY_STOP"):
                    await self._bus.publish(EventType.CIRCUIT_BREAKER_TRIGGERED, denied_payload)

                await self._event_log.append(
                    event_type=EventType.TRADE_DENIED.value,
                    source_service="risk_service",
                    entity_id=signal_id,
                    payload=denied_payload,
                )
                logger.warning("Trade DENIED by risk engine", extra={"coin": coin, "bot": bot.value, "code": decision.code, "reason": decision.reason})

        except Exception as exc:
            logger.error("Error evaluating risk on SIGNAL_AI_CONFIRMED", exc_info=True)

    async def on_position_closed(self, event_type: EventType, payload: dict) -> None:
        """Update consecutive losses and circuit breaker on position close."""
        try:
            bot_str = payload.get("bot", "MTB")
            pnl = float(payload.get("pnl", 0.0))
            try:
                bot = BotName(bot_str)
                self._circuit_breaker.record_trade_result(bot, pnl)
            except ValueError:
                pass
        except Exception as exc:
            logger.warning("Error processing position close in RiskService", extra={"error": str(exc)})

    # ── Helpers & State Queries ───────────────────────────────────────────────

    def _select_bot_for_signal(self, payload: dict) -> BotName:
        opp_type = payload.get("opportunity_type") or payload.get("market_state")
        if opp_type in ("pullback", "accumulation", OppType.ACCUMULATION.value):
            return BotName.PMB
        if opp_type in ("sideways", OppType.WATCHLIST.value):
            return BotName.VGX
        return BotName.MTB

    def _get_default_amount_for_bot(self, bot: BotName) -> float:
        if bot == BotName.MTB:
            return self._config.v2_default_trade_amount_mtb
        if bot == BotName.PMB:
            return self._config.v2_default_trade_amount_pmb
        if bot == BotName.VGX:
            return self._config.v2_default_trade_amount_vgx
        return 100.0

    async def get_state(self) -> RiskState:
        open_mtb = await self._position_repo.get_open_by_bot(BotName.MTB)
        open_pmb = await self._position_repo.get_open_by_bot(BotName.PMB)
        open_vgx = await self._position_repo.get_open_by_bot(BotName.VGX)

        return RiskState(
            trading_enabled=self._config.v2_trading_enabled,
            emergency_stop=self._circuit_breaker.emergency_stop,
            circuit_breaker_open=self._circuit_breaker.is_open,
            per_bot_deployed={
                BotName.MTB.value: sum(p.deployed_capital for p in open_mtb),
                BotName.PMB.value: sum(p.deployed_capital for p in open_pmb),
                BotName.VGX.value: sum(p.deployed_capital for p in open_vgx),
            },
            per_bot_open_count={
                BotName.MTB.value: len(open_mtb),
                BotName.PMB.value: len(open_pmb),
                BotName.VGX.value: len(open_vgx),
            },
            daily_pnl={},
            last_checked_at=datetime.now(timezone.utc),
        )

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "trading_enabled": self._config.v2_trading_enabled,
            "circuit_breaker_open": self._circuit_breaker.is_open,
            "emergency_stop": self._circuit_breaker.emergency_stop,
            "breaker_reason": self._circuit_breaker.reason,
            "total_capital_limit": self._config.total_capital_limit,
            "mtb_capital_limit": self._config.mtb_capital_limit,
            "pmb_capital_limit": self._config.pmb_capital_limit,
            "vgx_capital_limit": self._config.vgx_capital_limit,
        }
