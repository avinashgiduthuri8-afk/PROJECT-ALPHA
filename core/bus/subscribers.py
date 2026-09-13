"""
V2 Subscriber Registry.

Central place where all service handlers are wired to the event bus.
Called once at application startup via register_all().

V2.1 wires: ScannerService (no inbound subscriptions needed for V2.1).
Later phases add: RiskService, PortfolioService, NotificationService, DashboardService.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .event_bus import EventBus
from .event_types import EventType

if TYPE_CHECKING:
    from v2.services.scanner_service import ScannerService
    from v2.services.ai_intelligence_service import AIIntelligenceService
    from v2.services.risk_service import RiskService
    from v2.services.portfolio_service import PortfolioService
    from v2.services.trading_service import TradingService
    from v2.services.shadow_service import ShadowService
    from v2.services.notification_service import NotificationService
    from v2.services.dashboard_service import DashboardService

logger = logging.getLogger("v2.bus.subscribers")


def register_all(
    bus: EventBus,
    scanner_service: "ScannerService | None" = None,
    ai_service: "AIIntelligenceService | None" = None,
    risk_service: "RiskService | None" = None,
    portfolio_service: "PortfolioService | None" = None,
    trading_service: "TradingService | None" = None,
    shadow_service: "ShadowService | None" = None,
    notification_service: "NotificationService | None" = None,
    dashboard_service: "DashboardService | None" = None,
) -> None:
    """
    Wire all service handlers to the event bus.

    Parameters are optional so callers can register only the services
    available in the current phase.
    """
    if ai_service is not None:
        bus.subscribe(EventType.SIGNAL_GENERATED, ai_service.on_signal_generated)

    if risk_service is not None:
        bus.subscribe(EventType.SIGNAL_AI_CONFIRMED, risk_service.on_signal_ai_confirmed)
        bus.subscribe(EventType.POSITION_CLOSED, risk_service.on_position_closed)

    if portfolio_service is not None:
        bus.subscribe(EventType.POSITION_OPENED, portfolio_service._on_position_event)
        bus.subscribe(EventType.POSITION_CLOSED, portfolio_service._on_position_event)
        bus.subscribe(EventType.POSITION_UPDATED, portfolio_service._on_position_event)

    if trading_service is not None:
        bus.subscribe(EventType.TRADE_APPROVED, trading_service.on_trade_approved)

    if shadow_service is not None:
        bus.subscribe(EventType.SIGNAL_AI_REJECTED, shadow_service._on_signal_ai_rejected)
        bus.subscribe(EventType.TRADE_DENIED, shadow_service._on_trade_denied)

    logger.info(
        "V2 subscriber registry initialised — "
        "scanner=%s ai=%s risk=%s portfolio=%s trading=%s shadow=%s notif=%s dash=%s",
        "✓" if scanner_service else "-",
        "✓" if ai_service else "-",
        "✓" if risk_service else "-",
        "✓" if portfolio_service else "-",
        "✓" if trading_service else "-",
        "✓" if shadow_service else "-",
        "✓" if notification_service else "-",
        "✓" if dashboard_service else "-",
    )


# ── Placeholder handlers (filled in as phases land) ──────────────────────────

async def on_signal_generated(event_type: EventType, payload: dict) -> None:
    """V2.2: RiskService evaluates signal for capital pre-check."""
    pass


async def on_signal_expired(event_type: EventType, payload: dict) -> None:
    """V2.2+: Cancel any pending TRADE_APPROVED for this signal."""
    pass


async def on_position_opened(event_type: EventType, payload: dict) -> None:
    """V2.3: PortfolioService updates deployed capital cache."""
    pass


async def on_position_closed(event_type: EventType, payload: dict) -> None:
    """V2.3: PortfolioService updates cash + PnL; RiskService updates daily_pnl."""
    pass


async def on_capital_limit_hit(event_type: EventType, payload: dict) -> None:
    """V2.2: AlertManager emits ALERT_GENERATED (WARN level)."""
    pass


async def on_circuit_breaker_triggered(event_type: EventType, payload: dict) -> None:
    """V2.2: TradingService halts; AlertManager emits ALERT_GENERATED (CRITICAL)."""
    pass


async def on_alert_generated(event_type: EventType, payload: dict) -> None:
    """V2.4: NotificationService dispatches to Telegram."""
    pass


async def on_job_failed(event_type: EventType, payload: dict) -> None:
    """V2.4: NotificationService dispatches job-failure alert."""
    pass
