"""
V2 Subscriber Registry — Skeleton only.

This module is the single place where handlers are wired to the event bus.
No logic is implemented yet. Wire-up happens at V2 service startup.

Pattern:
    from v2.bus.event_bus import bus
    from v2.bus.event_types import EventType

    def register_all() -> None:
        bus.subscribe(EventType.SIGNAL_GENERATED, on_signal_generated)
        bus.subscribe(EventType.POSITION_OPENED,  on_position_opened)
        ...
"""

from __future__ import annotations

from .event_bus import EventBus
from .event_types import EventType


def register_all(event_bus: EventBus) -> None:
    """
    Wire all V2 handlers to the supplied event bus.

    Called once at V2 service startup. Not yet implemented.
    """
    pass


# ── Placeholder handlers (implement in V2.1) ────────────────────────────────

async def on_signal_generated(event_type: EventType, payload: dict) -> None:
    """Handle SIGNAL_GENERATED — route to portfolio_service."""
    pass


async def on_signal_expired(event_type: EventType, payload: dict) -> None:
    """Handle SIGNAL_EXPIRED — clean up stale positions."""
    pass


async def on_position_opened(event_type: EventType, payload: dict) -> None:
    """Handle POSITION_OPENED — update portfolio metrics."""
    pass


async def on_position_closed(event_type: EventType, payload: dict) -> None:
    """Handle POSITION_CLOSED — record trade, update analytics."""
    pass


async def on_capital_limit_hit(event_type: EventType, payload: dict) -> None:
    """Handle CAPITAL_LIMIT_HIT — trigger circuit breaker."""
    pass


async def on_circuit_breaker_triggered(event_type: EventType, payload: dict) -> None:
    """Handle CIRCUIT_BREAKER_TRIGGERED — halt all bots, fire alert."""
    pass


async def on_alert_generated(event_type: EventType, payload: dict) -> None:
    """Handle ALERT_GENERATED — dispatch to notification_service."""
    pass
