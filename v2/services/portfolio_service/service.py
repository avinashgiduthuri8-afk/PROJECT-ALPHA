"""
V2 PortfolioService — tracks open positions, AUM, cash, and publishes portfolio updates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.types import PortfolioSnapshot
from v2.core.logging import get_logger
from v2.repository.metrics_repo import MetricsRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository

from .aggregator import PortfolioAggregator

logger = get_logger("v2.services.portfolio_service")


class PortfolioService:
    """Manages cross-bot portfolio state, AUM aggregation, and metrics broadcasting."""

    def __init__(
        self,
        bus: EventBus,
        position_repo: Optional[PositionRepository] = None,
        trade_repo: Optional[TradeRepository] = None,
        metrics_repo: Optional[MetricsRepository] = None,
        config: Optional[V2Config] = None,
    ) -> None:
        self._bus = bus
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._metrics_repo = metrics_repo
        self._config = config
        self._last_snapshot: Optional[PortfolioSnapshot] = None
        self._started = False

    @property
    def is_started(self) -> bool:
        """Return True if the service is currently started and active."""
        return self._started

    @property
    def bus(self) -> EventBus:
        """Return the attached EventBus instance."""
        return self._bus

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the PortfolioService, connect to EventBus, and register subscriptions."""
        if self._started:
            return
        self._started = True
        self._bus.subscribe(EventType.POSITION_OPENED, self._on_position_event)
        self._bus.subscribe(EventType.POSITION_CLOSED, self._on_position_event)
        self._bus.subscribe(EventType.POSITION_UPDATED, self._on_position_event)
        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "portfolio_service"})
        logger.info("PortfolioService started")

    async def stop(self) -> None:
        """Stop the PortfolioService and unsubscribe from all events."""
        if not self._started:
            return
        self._started = False
        self._bus.unsubscribe(EventType.POSITION_OPENED, self._on_position_event)
        self._bus.unsubscribe(EventType.POSITION_CLOSED, self._on_position_event)
        self._bus.unsubscribe(EventType.POSITION_UPDATED, self._on_position_event)
        logger.info("PortfolioService stopped")

    # ── Aggregation & State ───────────────────────────────────────────────────

    async def get_snapshot(self) -> PortfolioSnapshot:
        """Fetch current positions and completed trades from database, then aggregate."""
        open_positions = []
        if self._position_repo is not None:
            open_positions = await self._position_repo.get_open()

        recent_trades = []
        if self._trade_repo is not None:
            since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            recent_trades = await self._trade_repo.get_since(since, limit=200)

        snapshot = PortfolioAggregator.aggregate(
            positions=open_positions,
            closed_trades=recent_trades,
            base_cash=100000.0,
        )
        self._last_snapshot = snapshot
        return snapshot

    async def capture_and_publish_snapshot(self) -> PortfolioSnapshot:
        """Compute snapshot, persist to MetricsRepository, and publish PORTFOLIO_UPDATED."""
        snapshot = await self.get_snapshot()

        if self._metrics_repo is not None:
            await self._metrics_repo.insert_snapshot(snapshot)

        await self._bus.publish(
            EventType.PORTFOLIO_UPDATED,
            {
                "total_aum": snapshot.total_aum,
                "total_deployed": snapshot.total_deployed,
                "total_cash": snapshot.total_cash,
                "total_unrealised_pnl": snapshot.total_unrealised_pnl,
                "total_realised_pnl": snapshot.total_realised_pnl,
                "daily_pnl": snapshot.daily_pnl,
                "capital_utilisation": snapshot.capital_utilisation,
                "captured_at": snapshot.captured_at.isoformat(),
            },
        )
        return snapshot

    # ── Event Handlers ────────────────────────────────────────────────────────

    async def _on_position_event(self, event_type: EventType, payload: dict) -> None:
        """Event handler for position changes (POSITION_OPENED, POSITION_CLOSED, POSITION_UPDATED)."""
        logger.debug("PortfolioService received position event: %s", event_type.value)
        try:
            if self._position_repo is not None:
                await self.capture_and_publish_snapshot()
        except Exception as exc:
            logger.warning("Error updating portfolio on position event", extra={"error": str(exc)})

    # ── Health & Diagnostics ──────────────────────────────────────────────────

    def get_health(self) -> dict:
        """Return health status dictionary for monitoring."""
        return {
            "healthy": self._started,
            "last_snapshot_at": self._last_snapshot.captured_at.isoformat() if self._last_snapshot else None,
            "last_aum": self._last_snapshot.total_aum if self._last_snapshot else 0.0,
            "last_deployed": self._last_snapshot.total_deployed if self._last_snapshot else 0.0,
        }
