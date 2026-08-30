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


# ── Interactive Telegram C2 Interface Formatters ──────────────────────────────

def format_telegram_menu(overview: dict[str, Any]) -> str:
    """Format the primary Mission Control interactive hub menu."""
    status_str = overview.get("status", "HEALTHY")
    uptime = overview.get("uptime", "Running")
    total_aum = overview.get("total_aum", 0.0)
    deployed = overview.get("total_deployed", 0.0)
    daily_pnl = overview.get("daily_pnl", 0.0)
    active_positions = overview.get("active_positions", 0)
    bot_count = overview.get("bot_count", 4)
    trading_mode = overview.get("trading_mode", "PAPER ACTIVE")

    sign = "+" if daily_pnl >= 0 else ""
    pnl_emoji = "🟢" if daily_pnl >= 0 else "🔴"

    return (
        f"🚀 <b>PROJECT-ALPHA V2 · Mission Control C2</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Status:</b> <code>{status_str}</code> | <b>Mode:</b> <code>{trading_mode}</code>\n"
        f"<b>AUM:</b> ₹{total_aum:,.2f} | <b>Deployed:</b> ₹{deployed:,.2f}\n"
        f"<b>Daily PnL:</b> {pnl_emoji} <code>{sign}₹{daily_pnl:,.2f}</code>\n"
        f"<b>Open Positions:</b> <code>{active_positions}</code> | <b>Bots:</b> <code>{bot_count} Production</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Tap any button below to inspect subsystems or manage trading:</i>"
    )


def format_telegram_bot_fleet(bots: list[dict[str, Any]]) -> str:
    """Format the 4 production bots telemetry card."""
    lines = [
        "🤖 <b>PRODUCTION BOT FLEET (4 Active)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for b in bots:
        name = b.get("name", "UNKNOWN")
        sub_id = b.get("subaccount_id", f"ALPHA_{name}_01")
        stage = b.get("current_stage", "IDLE").replace("_", " ").title()
        wallet = float(b.get("wallet_balance", 0.0))
        avail = float(b.get("available_balance", wallet))
        pos_count = b.get("open_positions", 0)
        pnl = float(b.get("daily_pnl", 0.0))
        win_rate = float(b.get("win_rate_pct", 0.0))
        pnl_sign = "+" if pnl >= 0 else ""

        lines.append(
            f"🔹 <b>{name}</b> (<code>{sub_id}</code>)\n"
            f"   • <b>Stage:</b> {stage}\n"
            f"   • <b>Wallet:</b> ₹{wallet:,.2f} (Avail: ₹{avail:,.2f})\n"
            f"   • <b>Positions:</b> {pos_count} | <b>Win Rate:</b> {win_rate:.1f}%\n"
            f"   • <b>24h PnL:</b> <code>{pnl_sign}₹{pnl:.2f}</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_pipeline_stages(stages: list[dict[str, Any]]) -> str:
    """Format the 11 closed-loop pipeline stages overview."""
    lines = [
        "📊 <b>11-STAGE AUTONOMOUS PIPELINE</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for s in stages:
        num = s.get("number", 0)
        name = s.get("name", "")
        status = s.get("status", "ACTIVE")
        processed = s.get("processed_count", 0)
        rejected = s.get("rejected_count", 0)
        icon = "🟢" if status == "ACTIVE" else "🟡" if status == "STANDBY" else "⚪"

        line = f"<b>{num:02d}. {name}</b> {icon}\n   └ Processed: <code>{processed}</code>"
        if rejected > 0:
            line += f" | Filtered: <code>{rejected}</code>"
        lines.append(line)

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_portfolio(snapshot: dict[str, Any]) -> str:
    """Format consolidated portfolio and capital allocation breakdown."""
    total_aum = float(snapshot.get("total_aum", 0.0))
    deployed = float(snapshot.get("total_deployed", 0.0))
    cash = float(snapshot.get("total_cash", 0.0))
    unrealized = float(snapshot.get("total_unrealised_pnl", 0.0))
    realized = float(snapshot.get("total_realised_pnl", 0.0))
    daily_pnl = float(snapshot.get("daily_pnl", 0.0))
    utilization = float(snapshot.get("capital_utilisation", 0.0))

    u_sign = "+" if unrealized >= 0 else ""
    r_sign = "+" if realized >= 0 else ""
    d_sign = "+" if daily_pnl >= 0 else ""

    return (
        f"💼 <b>PORTFOLIO & CAPITAL ALLOCATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Total AUM:</b> ₹{total_aum:,.2f}\n"
        f"<b>Deployed Capital:</b> ₹{deployed:,.2f} (<code>{utilization:.1f}%</code>)\n"
        f"<b>Cash Liquidity:</b> ₹{cash:,.2f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Unrealized PnL:</b> <code>{u_sign}₹{unrealized:,.2f}</code>\n"
        f"<b>Realized PnL:</b> <code>{r_sign}₹{realized:,.2f}</code>\n"
        f"<b>Daily 24h PnL:</b> <code>{d_sign}₹{daily_pnl:,.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def format_telegram_positions(positions: list[dict[str, Any]]) -> str:
    """Format list of live open positions."""
    if not positions:
        return (
            "📈 <b>LIVE OPEN POSITIONS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No active open positions. Capital is parked safely in cash reserve.</i>"
        )

    lines = [
        f"📈 <b>LIVE OPEN POSITIONS ({len(positions)})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for p in positions:
        coin = p.get("coin", "UNKNOWN")
        bot = p.get("bot", "STE")
        qty = p.get("qty", 0.0)
        entry = float(p.get("entry_price", 0.0))
        cur = float(p.get("current_price", entry))
        unrealized = float(p.get("unrealised_pnl", 0.0))
        sl = p.get("stop_loss")
        tp = p.get("take_profit")
        sign = "+" if unrealized >= 0 else ""
        emoji = "🟢" if unrealized >= 0 else "🔴"

        sl_str = f"₹{sl:.2f}" if sl is not None else "None"
        tp_str = f"₹{tp:.2f}" if tp is not None else "None"

        lines.append(
            f"{emoji} <b>{coin}/INR</b> (<code>{bot}</code>)\n"
            f"   • Qty: <code>{qty}</code> | Entry: ₹{entry:.2f} | Current: ₹{cur:.2f}\n"
            f"   • Unrealized: <code>{sign}₹{unrealized:.2f}</code>\n"
            f"   • TP: {tp_str} | SL: {sl_str}\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_trades(trades: list[dict[str, Any]]) -> str:
    """Format recent closed trades history."""
    if not trades:
        return (
            "📜 <b>RECENT TRADES HISTORY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No closed trades recorded in this session.</i>"
        )

    lines = [
        f"📜 <b>RECENT TRADES HISTORY (Last {min(5, len(trades))})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for t in trades[:5]:
        coin = t.get("coin", "UNKNOWN")
        bot = t.get("bot", "STE")
        pnl = float(t.get("pnl", 0.0))
        pct = float(t.get("pnl_pct", 0.0))
        reason = t.get("exit_reason", "EXIT")
        emoji = "💰" if pnl >= 0 else "🛑"
        sign = "+" if pnl >= 0 else ""

        lines.append(
            f"{emoji} <b>{coin}</b> (<code>{bot}</code>) — <b>{reason}</b>\n"
            f"   └ Net PnL: <code>{sign}₹{pnl:.2f} ({sign}{pct:.2f}%)</code>"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_signals(signals: list[dict[str, Any]]) -> str:
    """Format high-conviction live signals from the 5-layer confluence engine."""
    if not signals:
        return (
            "🎯 <b>HIGH-CONVICTION SIGNALS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No pending signals. Confluence engine filtering low-conviction market noise.</i>"
        )

    lines = [
        f"🎯 <b>HIGH-CONVICTION SIGNALS ({len(signals)})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for s in signals:
        coin = s.get("coin", "UNKNOWN")
        score = s.get("confidence_score") or s.get("confluence_score", 0)
        action = s.get("action", "BUY")
        price = float(s.get("price", 0.0))
        time_str = s.get("generated_at", "")[:19]

        lines.append(
            f"🔥 <b>{coin}</b> — <code>{action}</code>\n"
            f"   • Price: ₹{price:.2f} | Confluence: <code>{score}%</code>\n"
            f"   • Generated: <code>{time_str}</code>"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_risk(risk_state: dict[str, Any]) -> str:
    """Format risk engine state and circuit breaker metrics."""
    circuit_open = risk_state.get("circuit_breaker_open", False)
    emergency_stop = risk_state.get("emergency_stop", False)
    total_limit = float(risk_state.get("total_capital_limit", 50000.0))
    deployed = risk_state.get("per_bot_deployed", {})
    open_counts = risk_state.get("per_bot_open_count", {})

    status_icon = "🔴 TRIPPED" if circuit_open or emergency_stop else "🟢 HEALTHY / ACTIVE"

    lines = [
        "🛡️ <b>RISK ENGINE & CIRCUIT BREAKER</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Status:</b> <code>{status_icon}</code>",
        f"<b>Emergency Stop:</b> <code>{'ON' if emergency_stop else 'OFF'}</code>",
        f"<b>Total Fleet Capital Cap:</b> ₹{total_limit:,.2f}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Per-Bot Capital Allocation:</b>",
    ]
    for bot, dep in deployed.items():
        cnt = open_counts.get(bot, 0)
        lines.append(f"   • <b>{bot}:</b> ₹{float(dep):,.2f} ({cnt} open positions)")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_help() -> str:
    """Format help text listing all available bot commands."""
    return (
        "📖 <b>PROJECT-ALPHA V2 C2 Bot Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Dashboard & Telemetry:</b>\n"
        "  • /start or /menu — Mission Control Interactive Menu\n"
        "  • /status — Full system health & uptime\n"
        "  • /bots — Production Bot Fleet & Sub-Accounts\n"
        "  • /stages — 11-Stage Closed-Loop Pipeline\n"
        "  • /portfolio — AUM, Cash Reserves & PnL\n"
        "  • /positions — Live open positions\n"
        "  • /trades — Recent executed trades\n"
        "  • /signals — High-conviction scanner signals\n"
        "  • /risk — Risk limits & Circuit Breaker\n\n"
        "<b>Operational Control:</b>\n"
        "  • /emergency_stop — Trip circuit breaker & pause trading\n"
        "  • /resume — Reset circuit breaker & restore trading\n"
        "  • /help — Show this help manual\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
