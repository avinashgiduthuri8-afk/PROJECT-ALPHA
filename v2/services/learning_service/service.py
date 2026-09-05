"""
V2 Learning Service.

Unified service facade coordinating LearningEngine and StrategyCalibrator.
Exposes run_learning_cycle() for automated or on-demand execution.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2.bus.event_bus import EventBus
from v2.core.logging import get_logger
from v2.repository.journal_repo import JournalRepository
from v2.repository.learning_repo import LearningRepository
from v2.services.analytics_service.engine import AnalyticsEngine
from .engine import LearningEngine
from .calibrator import StrategyCalibrator

logger = get_logger("v2.services.learning_service")


class LearningService:
    """Learning Engine Service Facade."""

    def __init__(
        self,
        bus: EventBus,
        journal_repo: JournalRepository,
        learning_repo: LearningRepository,
        analytics_engine: Optional[AnalyticsEngine] = None,
    ) -> None:
        self._bus = bus
        self._journal_repo = journal_repo
        self._learning_repo = learning_repo
        self._analytics_engine = analytics_engine or AnalyticsEngine(journal_repo)

        self.engine = LearningEngine(
            journal_repo=self._journal_repo,
            learning_repo=self._learning_repo,
        )
        self.calibrator = StrategyCalibrator(
            learning_repo=self._learning_repo,
            analytics_engine=self._analytics_engine,
            bus=self._bus,
        )
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        logger.info("LearningService started with LearningEngine & StrategyCalibrator")

    async def stop(self) -> None:
        self._started = False
        logger.info("LearningService stopped")

    async def run_learning_cycle(self, limit: int = 100) -> Dict[str, Any]:
        """
        Execute a complete learning evaluation pass:
          1. Extract mistake pattern insights from recent trade journal entries.
          2. Calculate dynamic strategy parameter calibrations.
          3. Return execution report summary.
        """
        insights = await self.engine.analyze_trades_and_extract_insights(limit=limit)
        calibrations = await self.calibrator.calibrate_all_strategies(insights)

        report = {
            "insights_generated": len(insights),
            "calibrations_updated": len(calibrations),
            "insights": insights,
            "calibrations": calibrations,
        }
        logger.info("Completed learning cycle pass: %d insights, %d calibrations", len(insights), len(calibrations))
        return report

    async def get_active_insights(
        self, bot_name: Optional[str] = None, pair: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return await self._learning_repo.get_active_insights(bot_name=bot_name, pair=pair)

    async def get_calibrations(self) -> List[Dict[str, Any]]:
        return await self._learning_repo.get_calibrations()
