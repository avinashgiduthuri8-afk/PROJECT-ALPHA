"""
V2 DashboardService — bridges the internal event bus to real-time WebSockets
and generates single-call unified dashboard overview snapshots.
"""

from __future__ import annotations

from typing import Any, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.logging import get_logger

from .websocket import WebSocketManager

logger = get_logger("v2.services.dashboard_service")


class DashboardService:
    """Manages real-time UI broadcasting and state aggregation."""

    def __init__(
        self,
        bus: EventBus,
        config: V2Config,
        ws_manager: Optional[WebSocketManager] = None,
        scanner_service: Optional[Any] = None,
        ai_service: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        portfolio_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        shadow_service: Optional[Any] = None,
        scheduler: Optional[Any] = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._ws_manager = ws_manager or WebSocketManager()

        self._scanner_service = scanner_service
        self._ai_service = ai_service
        self._risk_service = risk_service
        self._portfolio_service = portfolio_service
        self._trading_service = trading_service
        self._shadow_service = shadow_service
        self._scheduler = scheduler

        self._started = False

    @property
    def ws_manager(self) -> WebSocketManager:
        return self._ws_manager

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        # Subscribe to all user-facing live events for real-time push
        for et in [
            EventType.SIGNAL_GENERATED,
            EventType.SIGNAL_AI_CONFIRMED,
            EventType.SIGNAL_AI_REJECTED,
            EventType.TRADE_APPROVED,
            EventType.TRADE_DENIED,
            EventType.TRADE_EXECUTED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.PORTFOLIO_UPDATED,
            EventType.DIVERGENCE_DETECTED,
            EventType.CIRCUIT_BREAKER_TRIGGERED,
            EventType.ALERT_GENERATED,
        ]:
            self._bus.subscribe(et, self._on_event_broadcast)

        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "dashboard_service"})
        logger.info("DashboardService started with real-time push enabled")

    async def stop(self) -> None:
        self._started = False
        for et in [
            EventType.SIGNAL_GENERATED,
            EventType.SIGNAL_AI_CONFIRMED,
            EventType.SIGNAL_AI_REJECTED,
            EventType.TRADE_APPROVED,
            EventType.TRADE_DENIED,
            EventType.TRADE_EXECUTED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.PORTFOLIO_UPDATED,
            EventType.DIVERGENCE_DETECTED,
            EventType.CIRCUIT_BREAKER_TRIGGERED,
            EventType.ALERT_GENERATED,
        ]:
            self._bus.unsubscribe(et, self._on_event_broadcast)

        logger.info("DashboardService stopped")

    # ── Event Relay ───────────────────────────────────────────────────────────

    async def _on_event_broadcast(self, event_type: EventType, payload: dict) -> None:
        """Forward any bus event to connected WebSocket clients."""
        try:
            await self._ws_manager.broadcast(
                event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
                payload=payload,
            )
        except Exception as exc:
            logger.warning("Error broadcasting event over WebSocket", extra={"error": str(exc)})

    # ── System Overview Snapshot ──────────────────────────────────────────────

    async def get_overview(self) -> dict[str, Any]:
        """Aggregate the full platform state in a single call for dashboard initial load."""
        portfolio = await self._portfolio_service.get_snapshot() if self._portfolio_service else None
        risk_state = await self._risk_service.get_state() if self._risk_service else None
        shadow_summary = await self._shadow_service.get_summary() if self._shadow_service else {}

        return {
            "status": "ok",
            "active_ws_clients": self._ws_manager.active_count,
            "portfolio": {
                "total_aum": portfolio.total_aum if portfolio else 0.0,
                "total_deployed": portfolio.total_deployed if portfolio else 0.0,
                "total_cash": portfolio.total_cash if portfolio else 0.0,
                "daily_pnl": portfolio.daily_pnl if portfolio else 0.0,
                "capital_utilisation": portfolio.capital_utilisation if portfolio else 0.0,
            } if portfolio else None,
            "risk": {
                "trading_enabled": risk_state.trading_enabled if risk_state else False,
                "circuit_breaker_open": risk_state.circuit_breaker_open if risk_state else False,
                "emergency_stop": risk_state.emergency_stop if risk_state else False,
                "per_bot_deployed": risk_state.per_bot_deployed if risk_state else {},
            } if risk_state else None,
            "shadow": shadow_summary,
            "subsystems": {
                "scanner": self._scanner_service.get_health() if self._scanner_service else {"healthy": False},
                "ai": self._ai_service.get_health() if self._ai_service else {"healthy": False},
                "trading": self._trading_service.get_health() if self._trading_service else {"healthy": False},
            },
        }

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "active_clients": self._ws_manager.active_count,
        }
