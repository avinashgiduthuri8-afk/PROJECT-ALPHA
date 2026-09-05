"""
V2 Dynamic Parameter Calibrator.

Calculates strategy weight multipliers and confluence score thresholds dynamically
based on mistake pattern insights and quantitative performance metrics.
Publishes LEARNING_INSIGHT_GENERATED and STRATEGY_CALIBRATED events over EventBus.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.logging import get_logger
from v2.repository.learning_repo import LearningRepository
from v2.services.analytics_service.engine import AnalyticsEngine

logger = get_logger("v2.services.learning_service.calibrator")


class StrategyCalibrator:
    """Dynamic Strategy Weight & Score Threshold Calibrator."""

    def __init__(
        self,
        learning_repo: LearningRepository,
        analytics_engine: AnalyticsEngine,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._learning_repo = learning_repo
        self._analytics_engine = analytics_engine
        self._bus = bus

    async def calibrate_all_strategies(
        self, insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Evaluate performance metrics and insights for all production bots (STE, HDA, VCP, BBS)
        and update their strategy calibrations in SQLite.
        Returns list of updated calibration dictionaries.
        """
        metrics_summary = await self._analytics_engine.compute_performance_metrics()
        strategy_stats = metrics_summary.get("strategy_attribution", {})

        calibrations: List[Dict[str, Any]] = []

        for bot_name in ("STE", "HDA", "VCP", "BBS"):
            bot_insights = [
                ins for ins in insights
                if str(ins.get("bot_name", "")).upper() == bot_name
            ]

            stats = strategy_stats.get(bot_name, {})
            win_rate = float(stats.get("win_rate_pct", 0.0))
            profit_factor = float(stats.get("profit_factor", 0.0))
            trades_count = int(stats.get("trades", 0))

            # Calibration decision matrix
            has_cooling_trigger = any(
                ins.get("pattern_type") == "CONSECUTIVE_LOSSES"
                or ins.get("severity") in ("HIGH", "CRITICAL")
                for ins in bot_insights
            )

            if has_cooling_trigger:
                status = "COOLING_DOWN"
                weight_multiplier = 0.5
                min_confluence_threshold = 90.0
            elif trades_count >= 3 and win_rate >= 70.0 and profit_factor >= 1.8:
                status = "BOOSTED"
                weight_multiplier = 1.2
                min_confluence_threshold = 80.0
            else:
                status = "ACTIVE"
                weight_multiplier = 1.0
                min_confluence_threshold = 85.0

            # Upsert into SQLite
            await self._learning_repo.upsert_calibration(
                bot_name=bot_name,
                pair=None,
                weight_multiplier=weight_multiplier,
                min_confluence_threshold=min_confluence_threshold,
                status=status,
            )

            cal_record = {
                "bot_name": bot_name,
                "status": status,
                "weight_multiplier": weight_multiplier,
                "min_confluence_threshold": min_confluence_threshold,
                "win_rate_pct": win_rate,
                "profit_factor": profit_factor,
                "insights_count": len(bot_insights),
            }
            calibrations.append(cal_record)

            # Publish EventBus events
            if self._bus:
                for ins in bot_insights:
                    await self._bus.publish(
                        EventType.ALERT_GENERATED,
                        ins,
                    )

                await self._bus.publish(
                    EventType.CALIBRATION_UPDATED,
                    cal_record,
                )

            logger.info(
                "Calibrated bot %s -> Status: %s | Weight: %.2fx | Min Score: %.1f",
                bot_name, status, weight_multiplier, min_confluence_threshold,
            )

        return calibrations
