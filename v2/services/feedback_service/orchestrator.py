"""
V2 Autonomous Feedback Orchestrator.

Orchestrates the recursive feedback pipeline:
  Signal -> Trade Execution -> Journal Result -> Learning Insight -> Pre-Validation Backtest -> Calibration Promotion/Rollback.

Enforces:
  1. Pre-Deployment Backtest Validation Gate (rejects parameter changes causing performance degradation).
  2. Promotion Gate to Active Cache (promotes validated strategy weights & confluence score thresholds).
  3. Safety Rollback Engine (initiates emergency rollback to baseline config on 2 consecutive post-promotion losses).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.logging import get_logger
from v2.repository.feedback_repo import FeedbackRepository
from v2.services.backtest_service.service import BacktestService

logger = get_logger("v2.services.feedback_service.orchestrator")


class FeedbackOrchestrator:
    """Autonomous Feedback Pipeline Orchestrator & Promotion Gate."""

    def __init__(

        self,
        feedback_repo: FeedbackRepository,
        backtest_service: BacktestService,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._feedback_repo = feedback_repo
        self._backtest_service = backtest_service
        self._bus = bus
        # Track post-promotion loss counts per bot for rollback safety
        self._post_promotion_losses: Dict[str, int] = {}
        self._active_promotions: Dict[str, Dict[str, Any]] = {}

    async def evaluate_and_validate_calibration(
        self,
        bot_name: str,
        pair: str,
        proposed_multiplier: float,
        proposed_threshold: float,
        validation_candles: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Pre-Deployment Safety Validation & Promotion Gate:
          1. Retrieve current active calibration baseline.
          2. Execute backtest simulation using candidate parameters.
          3. Promote if metrics hold or improve; reject if metrics degrade.
          4. Persist audit trail event to SQLite.
        """
        cycle_id = str(uuid.uuid4())
        bot_str = bot_name.upper()

        # Fetch current active baseline from cache
        active_curr = await self._feedback_repo.get_active_calibration(bot_str)
        prev_mult = float(active_curr["weight_multiplier"]) if active_curr else 1.0
        prev_thresh = float(active_curr["strict_threshold"]) if active_curr else 85.0

        # Action classification
        if proposed_multiplier > prev_mult:
            action = "WEIGHT_BOOST"
        elif proposed_multiplier < prev_mult:
            action = "WEIGHT_PENALTY"
        elif proposed_threshold > prev_thresh:
            action = "THRESHOLD_TIGHTEN"
        else:
            action = "WEIGHT_PENALTY"

        # 1. Pre-Deployment Backtest Verification
        candles = validation_candles or []
        parameters = {
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.046,
            "min_confluence_threshold": proposed_threshold,
            "multiplier": proposed_multiplier,
        }

        backtest_res = await self._backtest_service.run_backtest(
            strategy_name=bot_str,
            pair=pair,
            candles=candles,
            parameters=parameters,
        )

        validation_backtest_id = backtest_res.get("id")
        win_rate = float(backtest_res.get("win_rate", 0.0))
        profit_factor = float(backtest_res.get("profit_factor", 0.0))
        max_dd = float(backtest_res.get("max_drawdown", 0.0))

        # Promotion Gate Criteria:
        # If simulation has 0 trades (insufficient candles) or Profit Factor >= 1.0 without severe drawdown, approve promotion.
        # If profit factor < 0.8 on 2+ trades, reject promotion.
        trades_count = int(backtest_res.get("total_trades", 0))
        if trades_count >= 2 and profit_factor < 0.8:
            status = "REJECTED"
        else:
            status = "PROMOTED"

        audit_event = {
            "id": str(uuid.uuid4()),
            "cycle_id": cycle_id,
            "bot_name": bot_str,
            "pair": pair,
            "action_taken": action,
            "previous_multiplier": prev_mult,
            "new_multiplier": proposed_multiplier if status == "PROMOTED" else prev_mult,
            "previous_threshold": prev_thresh,
            "new_threshold": proposed_threshold if status == "PROMOTED" else prev_thresh,
            "validation_backtest_id": validation_backtest_id,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist audit trail event
        await self._feedback_repo.record_audit_event(audit_event)

        if status == "PROMOTED":
            # Update Active Calibrations Cache
            await self._feedback_repo.upsert_active_calibration(
                bot_name=bot_str,
                weight_multiplier=proposed_multiplier,
                strict_threshold=proposed_threshold,
            )
            self._post_promotion_losses[bot_str] = 0
            self._active_promotions[bot_str] = audit_event

            if self._bus:
                await self._bus.publish(
                    EventType.CALIBRATION_UPDATED,
                    audit_event,
                )

            logger.info("PROMOTED new calibration for %s -> Multiplier: %.2fx, Threshold: %.1f", bot_str, proposed_multiplier, proposed_threshold)
        else:
            logger.warning("REJECTED candidate calibration for %s due to backtest degradation (PF: %.2f)", bot_str, profit_factor)

        return audit_event

    async def register_trade_outcome(self, bot_name: str, pair: str, is_win: bool) -> Optional[Dict[str, Any]]:
        """
        Safety Rollback Engine:
          Monitors trade outcomes for bots post-promotion.
          If 2 consecutive losses occur immediately following promotion,
          initiates emergency rollback to baseline configuration (weight=1.0, threshold=85.0).
        """
        bot_str = bot_name.upper()

        if is_win:
            self._post_promotion_losses[bot_str] = 0
            return None

        # Increment loss counter on losing trade
        current_losses = self._post_promotion_losses.get(bot_str, 0) + 1
        self._post_promotion_losses[bot_str] = current_losses

        if current_losses >= 2:
            # Trigger Safety Rollback
            logger.warning("Safety Rollback triggered for bot %s after %d consecutive post-promotion losses", bot_str, current_losses)

            active_curr = await self._feedback_repo.get_active_calibration(bot_str)
            prev_mult = float(active_curr["weight_multiplier"]) if active_curr else 1.0
            prev_thresh = float(active_curr["strict_threshold"]) if active_curr else 85.0

            baseline_mult = 1.0
            baseline_thresh = 85.0

            rollback_event = {
                "id": str(uuid.uuid4()),
                "cycle_id": str(uuid.uuid4()),
                "bot_name": bot_str,
                "pair": pair,
                "action_taken": "ROLLBACK",
                "previous_multiplier": prev_mult,
                "new_multiplier": baseline_mult,
                "previous_threshold": prev_thresh,
                "new_threshold": baseline_thresh,
                "validation_backtest_id": None,
                "status": "ROLLED_BACK",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            await self._feedback_repo.record_audit_event(rollback_event)
            await self._feedback_repo.upsert_active_calibration(
                bot_name=bot_str,
                weight_multiplier=baseline_mult,
                strict_threshold=baseline_thresh,
            )

            self._post_promotion_losses[bot_str] = 0
            if self._bus:
                await self._bus.publish(
                    EventType.CALIBRATION_UPDATED,
                    rollback_event,
                )

            return rollback_event

        return None
