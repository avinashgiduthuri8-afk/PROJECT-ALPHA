"""
V2 Notification Formatters — produces structured HTML/emoji messages for Telegram and logs.
"""

from __future__ import annotations

from typing import Any


def format_signal_ai_alert(payload: dict[str, Any]) -> str:
    """Format AI Intelligence confirmation or rejection alert."""
    coin = payload.get("coin", "UNKNOWN")
    rec = payload.get("recommendation", "WATCH")
    conf = payload.get("confidence_score", 0)
    trend = payload.get("trend_evaluation", "N/A")
    setup = payload.get("setup_quality", "N/A")
    factors = payload.get("supporting_factors") or []
    risks = payload.get("risk_factors") or []

    emoji = "🟢" if rec == "APPROVE" else "🟡" if rec == "SCALE_DOWN" else "🔴"

    lines = [
        f"{emoji} <b>AI Intelligence — {coin}</b>",
        f"<b>Recommendation:</b> {rec} (Confidence: <code>{conf}%</code>)",
        f"<b>Trend:</b> {trend}",
        f"<b>Setup:</b> {setup}",
    ]

    if factors:
        lines.append(f"<b>Key Strengths:</b> {', '.join(factors[:2])}")
    if risks:
        lines.append(f"<b>Risk Factors:</b> {', '.join(risks[:2])}")

    return "\n".join(lines)


def format_trade_approved_alert(payload: dict[str, Any]) -> str:
    """Format risk-approved trade alert."""
    coin = payload.get("coin", "UNKNOWN")
    bot = payload.get("bot", "MTB")
    amount = float(payload.get("approved_amount", 0.0))
    adjustments = payload.get("ai_adjustments") or {}
    multiplier = adjustments.get("size_multiplier", 1.0)

    return (
        f"⚡ <b>Trade Approved — {coin}</b>\n"
        f"<b>Bot Strategy:</b> <code>{bot}</code>\n"
        f"<b>Allocated Capital:</b> ₹{amount:.2f} (AI Scale: <code>{multiplier}x</code>)"
    )


def format_trade_denied_alert(payload: dict[str, Any]) -> str:
    """Format risk-denied trade alert."""
    coin = payload.get("coin", "UNKNOWN")
    bot = payload.get("bot", "MTB")
    code = payload.get("code", "BLOCKED")
    reason = payload.get("reason", "Capital limit reached")

    return (
        f"🛡️ <b>Trade Blocked by Risk Engine — {coin}</b>\n"
        f"<b>Bot:</b> <code>{bot}</code>\n"
        f"<b>Code:</b> <code>{code}</code>\n"
        f"<b>Reason:</b> {reason}"
    )


def format_position_opened_alert(payload: dict[str, Any]) -> str:
    """Format position opened execution alert."""
    coin = payload.get("coin", "UNKNOWN")
    bot = payload.get("bot", "MTB")
    price = float(payload.get("entry_price", 0.0))
    qty = float(payload.get("qty", 0.0))
    sl = payload.get("stop_loss")
    tp = payload.get("take_profit")

    sl_str = f"₹{sl:.2f}" if sl is not None else "None"
    tp_str = f"₹{tp:.2f}" if tp is not None else "None"

    return (
        f"🚀 <b>Position Opened — {coin}</b>\n"
        f"<b>Bot:</b> <code>{bot}</code> | <b>Qty:</b> <code>{qty}</code>\n"
        f"<b>Entry Price:</b> ₹{price:.2f}\n"
        f"<b>Take Profit:</b> {tp_str} | <b>Stop Loss:</b> {sl_str}"
    )


def format_position_closed_alert(payload: dict[str, Any]) -> str:
    """Format position closed / trade exit alert."""
    coin = payload.get("coin", "UNKNOWN")
    bot = payload.get("bot", "MTB")
    pnl = float(payload.get("pnl", 0.0))
    pnl_pct = float(payload.get("pnl_pct", 0.0))
    reason = payload.get("exit_reason", "MANUAL")
    price = float(payload.get("exit_price", 0.0))

    emoji = "💰" if pnl >= 0 else "🛑"
    sign = "+" if pnl >= 0 else ""

    return (
        f"{emoji} <b>Position Closed — {coin}</b>\n"
        f"<b>Bot:</b> <code>{bot}</code> | <b>Exit Price:</b> ₹{price:.2f}\n"
        f"<b>Realized PnL:</b> <code>{sign}₹{pnl:.2f} ({sign}{pnl_pct:.2f}%)</code>\n"
        f"<b>Exit Trigger:</b> <code>{reason}</code>"
    )


def format_circuit_breaker_alert(payload: dict[str, Any]) -> str:
    """Format emergency circuit breaker alert."""
    reason = payload.get("reason", "Threshold breached")
    return (
        f"🚨 <b>CIRCUIT BREAKER TRIGGERED</b> 🚨\n"
        f"<b>Reason:</b> {reason}\n"
        f"All automated trade entries have been suspended."
    )


def format_divergence_alert(payload: dict[str, Any]) -> str:
    """Format shadow mode alpha divergence alert."""
    coin = payload.get("coin", "UNKNOWN")
    bot = payload.get("bot", "MTB")
    div_type = payload.get("divergence_type", "AI_FILTERED")
    reason = payload.get("reason", "N/A")

    return (
        f"🧠 <b>Decision Divergence Detected — {coin}</b>\n"
        f"<b>Bot:</b> <code>{bot}</code> | <b>Type:</b> <code>{div_type}</code>\n"
        f"<b>Reason:</b> {reason}"
    )


def format_generic_alert(payload: dict[str, Any]) -> str:
    """Format generic system alert."""
    level = payload.get("level", "INFO").upper()
    title = payload.get("title", "System Notification")
    message = payload.get("message", "")

    emoji = "ℹ️" if level == "INFO" else "⚠️" if level == "WARNING" else "🚨"

    return f"{emoji} <b>{title}</b>\n{message}"
