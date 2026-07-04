"""
V2 Event Type Definitions — Placeholder only.

All event names used by the V2 event bus. No logic here — pure constants.
Import from this module to publish or subscribe to events.
"""

from enum import Enum


class EventType(str, Enum):

    # ── Signal lifecycle ────────────────────────────────────────────────────
    SIGNAL_GENERATED  = "signal.generated"
    SIGNAL_UPDATED    = "signal.updated"
    SIGNAL_EXPIRED    = "signal.expired"

    # ── Position lifecycle ──────────────────────────────────────────────────
    POSITION_OPENED   = "position.opened"
    POSITION_CLOSED   = "position.closed"
    POSITION_UPDATED  = "position.updated"

    # ── Risk / circuit-breaker ──────────────────────────────────────────────
    CAPITAL_LIMIT_HIT          = "risk.capital_limit_hit"
    DRAWDOWN_LIMIT_HIT         = "risk.drawdown_limit_hit"
    CIRCUIT_BREAKER_TRIGGERED  = "risk.circuit_breaker_triggered"

    # ── Bot lifecycle ───────────────────────────────────────────────────────
    BOT_STARTED = "bot.started"
    BOT_STOPPED = "bot.stopped"
    BOT_ERROR   = "bot.error"

    # ── Portfolio / metrics ─────────────────────────────────────────────────
    METRICS_UPDATED   = "metrics.updated"
    PORTFOLIO_UPDATED = "portfolio.updated"
    ALERT_GENERATED   = "alert.generated"
