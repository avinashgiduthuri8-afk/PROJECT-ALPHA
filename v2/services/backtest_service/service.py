"""
V2 Backtest Service.

Unified service facade coordinating HistoricalRunner and StrategyOptimizer, storing
simulation runs and trade logs in SQLite via BacktestRepository.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2.backtest.historical_runner import HistoricalRunner
from v2.backtest.optimizer import StrategyOptimizer
from v2.core.logging import get_logger
from v2.repository.backtest_repo import BacktestRepository

logger = get_logger("v2.services.backtest_service")


class BacktestService:
    """Historical Backtesting & Strategy Optimization Service Facade."""

    def __init__(
        self,
        backtest_repo: BacktestRepository,
        runner: Optional[HistoricalRunner] = None,
        optimizer: Optional[StrategyOptimizer] = None,
    ) -> None:
        self._backtest_repo = backtest_repo
        self.runner = runner or HistoricalRunner()
        self.optimizer = optimizer or StrategyOptimizer(runner=self.runner)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        logger.info("BacktestService started with HistoricalRunner and StrategyOptimizer")

    async def stop(self) -> None:
        self._started = False
        logger.info("BacktestService stopped")

    async def run_backtest(
        self,
        strategy_name: str,
        pair: str,
        candles: List[Dict[str, Any]],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run a historical backtest replay simulation, persist summary run and trade logs to SQLite,
        and return complete results dictionary.
        """
        run_summary, trades = self.runner.run_simulation(
            strategy_name=strategy_name,
            pair=pair,
            candles=candles,
            parameters=parameters,
        )

        run_id = await self._backtest_repo.record_run(run_summary)
        await self._backtest_repo.record_trades(trades)

        run_summary["trades_count"] = len(trades)
        run_summary["trades"] = trades

        logger.info("Executed and persisted backtest run %s for %s on %s", run_id, strategy_name, pair)
        return run_summary

    async def get_runs(
        self, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch historical backtest summary runs."""
        return await self._backtest_repo.get_runs(limit=limit, offset=offset)

    async def get_run_detail(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch summary run details and executed trade logs for a specific run_id."""
        run_info = await self._backtest_repo.get_run_detail(run_id)
        if not run_info:
            return None

        trades = await self._backtest_repo.get_run_trades(run_id)
        run_info["trades"] = trades
        return run_info

    async def get_run_trades(self, run_id: str) -> List[Dict[str, Any]]:
        """Fetch simulated trade log list for a specific run_id."""
        return await self._backtest_repo.get_run_trades(run_id)
