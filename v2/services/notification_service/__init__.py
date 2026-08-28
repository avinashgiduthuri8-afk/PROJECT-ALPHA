"""
V2 Notification Service Package.
"""

from .service import NotificationService
from .telegram import TelegramClient
from .formatters import (
    format_signal_ai_alert,
    format_trade_approved_alert,
    format_trade_denied_alert,
    format_position_opened_alert,
    format_position_closed_alert,
    format_circuit_breaker_alert,
    format_divergence_alert,
    format_generic_alert,
)

__all__ = [
    "NotificationService",
    "TelegramClient",
    "format_signal_ai_alert",
    "format_trade_approved_alert",
    "format_trade_denied_alert",
    "format_position_opened_alert",
    "format_position_closed_alert",
    "format_circuit_breaker_alert",
    "format_divergence_alert",
    "format_generic_alert",
]
