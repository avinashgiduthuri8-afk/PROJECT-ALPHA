"""
V2 Notification Formatters — produces structured HTML/emoji messages for Telegram and logs.
"""

from __future__ import annotations

import re
from typing import Any


def format_qty(qty: float | None) -> str:
    """Format quantity dynamically preserving micro-lots without trailing zeros."""
    if qty is None:
        return "0"
    try:
        q = float(qty)
    except (ValueError, TypeError):
        return str(qty)
    if q == 0.0:
        return "0"
    s = f"{q:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


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
    """Format position opened execution alert matching C2 specification."""
    coin = payload.get("coin", "UNKNOWN")
    bot = payload.get("bot", "STE")
    price = float(payload.get("entry_price", 0.0))
    qty = float(payload.get("qty", 0.0) or 0.0)
    amount = float(payload.get("amount", 0.0) or (qty * price))
    sl = payload.get("stop_loss")
    tp = payload.get("take_profit")

    sl_str = f"₹{sl:.2f}" if sl is not None else "None"
    tp_str = f"₹{tp:.2f}" if tp is not None else "None"

    return (
        f"🟢 <b>BUY EXECUTED</b>\n"
        f"<b>Coin:</b> <code>{coin}</code> | <b>Bot:</b> <code>{bot}</code>\n"
        f"<b>Amount:</b> ₹{amount:.2f} | <b>Entry:</b> ₹{price:.2f}\n"
        f"<b>TP:</b> {tp_str} | <b>SL:</b> {sl_str}"
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


def format_telegram_bot_fleet(fleet: dict[str, Any] | list[dict[str, Any]]) -> str:
    """Format the bot fleet status card matching C2 specification."""
    if isinstance(fleet, dict):
        open_pos = fleet.get("open_positions", 0)
        today_trades = fleet.get("today_trades", 0)
        daily_pnl = float(fleet.get("daily_pnl", 0.0))
        signals_today = fleet.get("signals_today", 0)
        bot_statuses = fleet.get("bot_statuses", {})
    else:
        open_pos = sum(b.get("open_positions", 0) for b in fleet)
        today_trades = sum(b.get("today_trades", 0) for b in fleet)
        daily_pnl = sum(float(b.get("daily_pnl", 0.0)) for b in fleet)
        signals_today = sum(b.get("signals_today", 0) for b in fleet)
        bot_statuses = {b.get("name", "BOT"): b.get("status", "ACTIVE") for b in fleet}

    ste_status = bot_statuses.get("STE", "ACTIVE")
    hda_status = bot_statuses.get("HDA", "ACTIVE")
    vcp_status = bot_statuses.get("VCP", "ACTIVE")
    bbs_status = bot_statuses.get("BBS", "ACTIVE")

    def _icon(s: str) -> str:
        return "🟢 ACTIVE" if s.upper() in ("ACTIVE", "HEALTHY", "RUNNING", "IDLE") else f"🟡 {s.upper()}"

    pnl_sign = "+" if daily_pnl >= 0 else ""

    lines = [
        "🤖 <b>BOT FLEET</b>",
        f"STE   {_icon(ste_status)}",
        f"HDA   {_icon(hda_status)}",
        f"VCP   {_icon(vcp_status)}",
        f"BBS   {_icon(bbs_status)}",
        "",
        f"Open Positions: {open_pos}",
        f"Today's Trades: {today_trades}",
        f"Today's P&L: {pnl_sign}₹{daily_pnl:.2f}",
        f"Signals Today: {signals_today}",
    ]
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
            "📈 <b>ACTIVE FLEET POSITIONS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No active open positions. Capital is parked safely in cash reserve.</i>"
        )

    lines = [
        f"📈 <b>ACTIVE FLEET POSITIONS ({len(positions)})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for p in positions:
        coin = p.get("coin", "UNKNOWN")
        pair = p.get("pair") or f"{coin}/INR"
        bot = p.get("bot", "STE")
        qty = float(p.get("qty", 0.0) or 0.0)
        entry = float(p.get("entry_price", 0.0) or 0.0)
        raw_cur = p.get("current_price")
        cur = float(raw_cur) if (raw_cur is not None and float(raw_cur) > 0) else None
        status = p.get("status", "OPEN")
        sl = p.get("stop_loss")
        tp = p.get("take_profit")
        
        is_usdt = "USDT" in pair or p.get("quote") == "USDT"
        sym = "$" if is_usdt else "₹"
        deployed = float(p.get("amount", 0.0) or (qty * entry))

        sl_str = f"{sym}{float(sl):.2f}" if sl is not None else "None"
        tp_str = f"{sym}{float(tp):.2f}" if tp is not None else "None"

        if cur is None:
            lines.append(
                f"⚪ <b>{pair}</b> [{status}]\n"
                f"   • Entry: {sym}{entry:.2f} | Capital: {sym}{deployed:.2f}\n"
                f"   • Unrealized P&L: <code>UNAVAILABLE</code>\n"
                f"   • TP: {tp_str} | SL: {sl_str}\n"
                f"   • Status: <code>{status}</code>"
            )
        else:
            unrealized = float(p.get("unrealised_pnl", 0.0) if p.get("unrealised_pnl") is not None else (cur - entry) * qty)
            unrealized_pct = (unrealized / deployed * 100.0) if deployed > 0 else (((cur - entry) / entry) * 100.0 if entry > 0 else 0.0)
            sign = "+" if unrealized >= 0 else ""
            pct_sign = "+" if unrealized_pct >= 0 else ""
            emoji = "🟢" if unrealized >= 0 else "🔴"
            lines.append(
                f"{emoji} <b>{pair}</b> [{status}]\n"
                f"   • Entry: {sym}{entry:.2f} | Capital: {sym}{deployed:.2f}\n"
                f"   • Unrealized P&L: <code>{sign}{sym}{unrealized:.2f} ({pct_sign}{unrealized_pct:.2f}%)</code>\n"
                f"   • TP: {tp_str} | SL: {sl_str}\n"
                f"   • Status: <code>{status}</code>"
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
        pnl_sign = "+" if pnl >= 0 else ""
        pct_sign = "+" if pct >= 0 else ""

        lines.append(
            f"{emoji} <b>{coin}</b> (<code>{bot}</code>) — <b>{reason}</b>\n"
            f"   • PnL: <code>{pnl_sign}₹{pnl:.2f} ({pct_sign}{pct:.2f}%)</code>\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_signals(signals: list[dict[str, Any]]) -> str:
    """Format high-conviction live signals from confluence engine."""
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
        bot = s.get("bot", "STE")
        score = s.get("confluence_score", s.get("score", 0))
        ai_conf = s.get("ai_confidence", s.get("confidence_score", 0))
        risk_verdict = s.get("risk_verdict", "APPROVED")
        lines.append(f"• <b>{coin}</b> | <code>{bot}</code> | C2: <code>{score}</code> | AI: <code>{ai_conf}%</code> | Risk: <code>{risk_verdict}</code>")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("<i>Use /signal &lt;symbol&gt; for technical breakdown</i>")
    return "\n".join(lines)


def format_telegram_risk(risk_state: dict[str, Any]) -> str:
    """Format risk engine state and circuit breaker metrics."""
    circuit_open = risk_state.get("circuit_breaker_open", False)
    emergency_stop = risk_state.get("emergency_stop", False)
    tot_raw = risk_state.get("total_capital_limit")
    total_cap_str = f"₹{float(tot_raw):,.2f}" if tot_raw is not None else "Dynamic (Unconstrained)"
    deployed = risk_state.get("per_bot_deployed", {})
    open_counts = risk_state.get("per_bot_open_count", {})

    status_icon = "🔴 TRIPPED" if circuit_open or emergency_stop else "🟢 HEALTHY / ACTIVE"

    lines = [
        "🛡️ <b>RISK ENGINE & CIRCUIT BREAKER</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Status:</b> <code>{status_icon}</code>",
        f"<b>Emergency Stop:</b> <code>{'ON' if emergency_stop else 'OFF'}</code>",
        f"<b>Total Fleet Capital Cap:</b> <code>{total_cap_str}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Per-Bot Capital Allocation:</b>",
    ]
    for bot, dep in deployed.items():
        cnt = open_counts.get(bot, 0)
        lines.append(f"   • <b>{bot}:</b> ₹{float(dep):,.2f} ({cnt} open positions)")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def mask_sensitive_data(text: str) -> str:
    """Mask credentials, tokens, and API secrets from output strings."""
    if not isinstance(text, str):
        text = str(text)
    # Redact common key/secret patterns
    text = re.sub(r'((?:api[_-]?)?key["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)', r'\1***REDACTED***', text, flags=re.IGNORECASE)
    text = re.sub(r'((?:api[_-]?)?secret(?:[_-]?(?:key|token))?["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)', r'\1***REDACTED***', text, flags=re.IGNORECASE)
    text = re.sub(r'((?:auth[_-]?)?token["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)', r'\1***REDACTED***', text, flags=re.IGNORECASE)
    text = re.sub(r'(password["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)', r'\1***REDACTED***', text, flags=re.IGNORECASE)
    text = re.sub(r'(bot[0-9]{8,12}:[a-zA-Z0-9_-]{35})', r'***REDACTED_TELEGRAM_TOKEN***', text)
    return text


def format_telegram_status(d: dict[str, Any]) -> str:
    """Format comprehensive /status operator response."""
    mode = d.get("mode", "SHADOW")
    cap_str = f"₹{d['available_capital']:,.2f}" if d.get("available_capital") is not None else "CAPITAL UNKNOWN"
    amt_str = f"₹{d.get('order_amount_inr', 200.0):,.2f}"

    lines = [
        "📊 <b>PROJECT-ALPHA V2 SYSTEM STATUS</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>System Status:</b> <code>{d.get('system_status', 'HEALTHY')}</code>",
        f"• <b>Trading Mode:</b> <code>{mode}</code>",
        f"• <b>Scanner Status:</b> <code>{d.get('scanner_status', 'ACTIVE')}</code> (Polls: {d.get('poll_count', 0)})",
        f"• <b>Execution Status:</b> <code>{d.get('execution_status', 'ACTIVE')}</code>",
        f"• <b>Risk Status:</b> <code>{d.get('risk_status', 'HEALTHY')}</code>",
        f"• <b>EventBus Status:</b> <code>{d.get('event_bus_status', 'OPERATIONAL')}</code>",
        f"• <b>Database Status:</b> <code>{d.get('database_status', 'CONNECTED')}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Configured Order Amount:</b> <code>{amt_str}</code>",
        f"• <b>Available Capital:</b> <code>{cap_str}</code>",
        f"• <b>Open Positions:</b> <code>{d.get('open_positions_count', 0)}</code>",
        f"• <b>Last Scanner Cycle:</b> <code>{d.get('last_scan_at', 'N/A')}</code>",
        f"• <b>Last Execution Event:</b> <code>{d.get('last_execution_at', 'N/A')}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_telegram_health(h: dict[str, Any]) -> str:
    """Format component-level /health status."""
    mode = h.get("mode", "SHADOW")
    components = h.get("components", {})

    def icon(ok: bool) -> str:
        return "🟢" if ok else "🔴"

    lines = [
        "🩺 <b>PROJECT-ALPHA V2 COMPONENT HEALTH</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Scanner       {icon(components.get('scanner', False))}",
        f"AI            {icon(components.get('ai', False))}",
        f"Risk Engine   {icon(components.get('risk', False))}",
        f"Execution     {icon(components.get('execution', False))}",
        f"Database      {icon(components.get('database', False))}",
        f"EventBus      {icon(components.get('event_bus', False))}",
        f"CoinDCX       {icon(components.get('coindcx', False))}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>Overall Status:</b> <code>{h.get('overall', 'UNKNOWN').upper()}</code>",
        f"<b>Checked At:</b> <code>{h.get('checked_at', 'N/A')}</code>",
    ]
    return "\n".join(lines)


def format_telegram_mode(m: dict[str, Any]) -> str:
    """Format /mode response."""
    mode = m.get("mode", "PAPER").upper()
    trading_enabled = m.get("trading_enabled", True)

    if mode in ("LIVE", "LIVE_MICROCASH"):
        badge = "🔴 LIVE TRADING (REAL MONEY)"
        desc = "Real orders are routed to CoinDCX exchange with live funds (₹200.00 micro-orders)."
    else:
        badge = "🟡 PAPER TRADING (SIMULATION ACTIVE)"
        desc = "Real signals execute virtual positions with live prices, SL/TP exits, and 1.572% friction."

    return (
        f"⚙️ <b>MODE: {mode}</b> — {badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Active Mode:</b> <code>{mode}</code>\n"
        f"• <b>Trading Status:</b> <code>{'YES (ACTIVE)' if trading_enabled else 'NO (HALTED)'}</code>\n"
        f"• <b>Micro-Order Size:</b> <code>₹200.00</code>\n"
        f"• <b>Description:</b> {desc}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>To change mode, send:</i>\n"
        f"• <code>/mode paper</code> — activate virtual paper trading\n"
        f"• <code>/mode live confirm</code> — activate live real-capital trading"
    )



def format_telegram_uptime(u: dict[str, Any]) -> str:
    """Format /uptime response."""
    mode = u.get("mode", "SHADOW")
    return (
        f"⏱️ <b>SYSTEM UPTIME & TELEMETRY</b>\n"
        f"<b>MODE: {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Server Started:</b> <code>{u.get('started_at', 'N/A')}</code>\n"
        f"• <b>Elapsed Uptime:</b> <code>{u.get('uptime_str', 'N/A')}</code>\n"
        f"• <b>Total Scanner Cycles:</b> <code>{u.get('poll_count', 0)}</code>\n"
        f"• <b>Active Tasks:</b> <code>{u.get('tasks_count', 1)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def format_telegram_scan(s: dict[str, Any]) -> str:
    """Format /scan summary showing latest cycle and strongest signals."""
    mode = s.get("mode", "SHADOW")
    signals = s.get("signals", [])

    lines = [
        "📡 <b>LATEST SCANNER CYCLE</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Cycle Completed:</b> <code>{s.get('last_scan_at', 'N/A')}</code>",
        f"• <b>Coins Evaluated:</b> <code>{s.get('evaluated_count', 0)}</code>",
        f"• <b>Candidates Generated:</b> <code>{s.get('candidate_count', 0)}</code>",
        f"• <b>Confluence Passed:</b> <code>{len(signals)}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Strongest Signals:</b>",
    ]
    if not signals:
        lines.append("<i>No high-conviction signals currently active.</i>")
    else:
        for sig in signals[:5]:
            coin = sig.get("coin", "UNKNOWN")
            score = sig.get("confluence_score", sig.get("score", 0))
            price = float(sig.get("price", 0.0))
            direction = sig.get("direction", sig.get("action", "BUY"))
            lines.append(f"  • <b>{coin}</b> ({direction}) — Score: <code>{score}%</code> @ ₹{price:,.2f}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_signal_detail(c: dict[str, Any], symbol: str, mode: str = "SHADOW") -> str:
    """Format /signal <symbol> deep-dive inspector with 4-pillar scores & AI conviction."""
    pair = c.get("pair") or symbol.upper()
    price = float(c.get("price", 0.0))
    c2_score = c.get("confluence_score", c.get("score", 0))
    bot = c.get("bot", "STE")
    status = c.get("status", "EVALUATED")
    rsi = float(c.get("rsi", 50.0))
    vol_24h = float(c.get("volume_24h", 0.0))
    vol_ratio = float(c.get("volume_ratio", 1.0))
    ema_trend = c.get("ema_trend", "N/A")
    mtf = c.get("mtf_alignment", "none")

    # 4 Pillar Breakdown
    eval_b = c.get("eval_breakdown", {})
    chart_score = eval_b.get("chart", {}).get("score", c.get("chart_score", 80))
    indicator_score = eval_b.get("indicator", {}).get("score", c.get("indicator_score", int(c2_score)))
    sentiment_score = eval_b.get("sentiment", {}).get("score", c.get("sentiment_score", 85))
    news_score = eval_b.get("news", {}).get("score", c.get("news_score", 90))

    # AI Conviction bullets
    ai_rec = c.get("ai_recommendation") or c.get("recommendation", "WATCH")
    ai_conf = c.get("ai_confidence") or c.get("confidence", 0)
    ai_strengths = c.get("ai_strengths") or c.get("supporting_factors") or []
    ai_risks = c.get("ai_risks") or c.get("risk_factors") or []

    lines = [
        f"🔍 <b>SIGNAL INSPECTOR — {pair}</b>",
        f"<b>MODE: {mode}</b> | <b>Bot:</b> <code>{bot}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Price:</b> ₹{price:,.4f}" if price < 10 else f"• <b>Price:</b> ₹{price:,.2f}",
        f"• <b>C2 Confluence Score:</b> <code>{c2_score}/100</code> (Status: <code>{status}</code>)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🏛️ <b>4-Pillar Breakdown:</b>",
        f"  • Technical Setup: <code>{indicator_score}/100</code> (EMA: {ema_trend}, RSI: {rsi:.1f})",
        f"  • Chart Structure: <code>{chart_score}/100</code>",
        f"  • Volume & Liquidity: <code>{vol_ratio:.2f}x vol</code> (24h: ₹{vol_24h:,.0f})",
        f"  • Market Regime & News: <code>{sentiment_score}/100</code> (News: <code>{news_score}/100</code>)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🧠 <b>AI Conviction:</b> <code>{ai_rec}</code> (<code>{ai_conf}%</code>)",
    ]
    if ai_strengths:
        lines.append(f"  • <b>Strengths:</b> {', '.join(str(s) for s in ai_strengths[:2])}")
    if ai_risks:
        lines.append(f"  • <b>Risks:</b> {', '.join(str(r) for r in ai_risks[:2])}")

    reasons = c.get("rejection_reasons") or []
    if reasons:
        lines.append(f"• <b>Gate Remarks:</b> <i>{'; '.join(reasons[:2])}</i>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_watchlist(watchlist: list[str], mode: str = "SHADOW") -> str:
    """Format /watchlist response."""
    lines = [
        f"📋 <b>ACTIVE SCANNER WATCHLIST ({len(watchlist)})</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if not watchlist:
        lines.append("<i>Watchlist is empty.</i>")
    else:
        chunks = [watchlist[i:i+4] for i in range(0, len(watchlist), 4)]
        for chunk in chunks:
            lines.append("  • " + " | ".join(f"<b>{c}</b>" for c in chunk))
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"<i>Total Monitored Assets: {len(watchlist)}</i>")
    return "\n".join(lines)


def format_telegram_funnel(f: dict[str, Any], mode: str = "SHADOW") -> str:
    """Format /funnel conversion metrics."""
    raw = f.get("raw_signals_count", 0)
    pre = f.get("pre_filtered_count", 0)
    c2 = f.get("confluence_passed_count", 0)
    ai = f.get("ai_approved_count", 0)
    exec_cnt = f.get("executed_count", 0)

    return (
        f"🌪️ <b>5-LAYER SCANNER CONVERSION FUNNEL</b>\n"
        f"<b>MODE: {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"1. <b>Raw Ingestion:</b> <code>{raw}</code> (100%)\n"
        f"2. <b>Pre-Filtered:</b> <code>{pre}</code> ({f.get('pre_filter_conversion_pct', 0):.1f}%)\n"
        f"3. <b>C2 Confluence Passed:</b> <code>{c2}</code> ({f.get('confluence_conversion_pct', 0):.1f}%)\n"
        f"4. <b>AI Confirmed:</b> <code>{ai}</code> ({f.get('ai_conversion_pct', 0):.1f}%)\n"
        f"5. <b>Risk & Executed:</b> <code>{exec_cnt}</code> ({f.get('execution_conversion_pct', 0):.1f}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Strict Gate: Signals rejected unless all 5 layers demonstrate strong evidence.</i>"
    )


def format_telegram_pnl(p: dict[str, Any]) -> str:
    """Format /pnl summary."""
    mode = p.get("mode", "SHADOW")
    realized = float(p.get("realized_pnl", 0.0))
    unrealized = float(p.get("unrealized_pnl", 0.0))
    total = realized + unrealized
    trades_cnt = p.get("trades_count", 0)
    win_rate = float(p.get("win_rate_pct", 0.0))

    real_icon = "🟢" if realized >= 0 else "🔴"
    unreal_icon = "🟢" if unrealized >= 0 else "🔴"
    tot_icon = "🟢" if total >= 0 else "🔴"

    return (
        f"💰 <b>PORTFOLIO PROFIT & LOSS</b>\n"
        f"<b>MODE: {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Realized P&L:</b> {real_icon} ₹{realized:,.2f} (post-statutory friction)\n"
        f"• <b>Unrealized P&L:</b> {unreal_icon} ₹{unrealized:,.2f}\n"
        f"• <b>Total P&L:</b> {tot_icon} <b>₹{total:,.2f}</b>\n"
        f"• <b>Total Closed Trades:</b> <code>{trades_cnt}</code>\n"
        f"• <b>Win Rate:</b> <code>{win_rate:.1f}%</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def format_telegram_orders(orders: list[dict[str, Any]], mode: str = "SHADOW") -> str:
    """Format /orders feed."""
    lines = [
        f"📜 <b>RECENT ORDERS LEDGER ({len(orders)})</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if not orders:
        lines.append("<i>No recent orders recorded.</i>")
    else:
        for ord_item in orders[:10]:
            coin = ord_item.get("coin", "UNKNOWN")
            side = ord_item.get("side", "BUY")
            qty = ord_item.get("qty", 0.0)
            price = float(ord_item.get("price", 0.0))
            ord_mode = ord_item.get("mode", mode)
            status = ord_item.get("status", "FILLED")
            ex_id = ord_item.get("exchange_order_id") or "N/A"

            lines.append(
                f"• <b>{coin}</b> [{ord_mode}] — <code>{side}</code> {format_qty(qty)} @ ₹{price:,.2f}\n"
                f"   Status: <code>{status}</code> | ID: <code>{ex_id}</code>"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_capital(c: dict[str, Any]) -> str:
    """Format /capital response strictly obeying capital reality and C2 specification."""
    mode = c.get("mode", "SHADOW")
    avail = c.get("available_capital")
    deployed = float(c.get("deployed_capital", 0.0))
    min_order = float(c.get("min_order_size", 200.0))
    order_amt = max(min_order, float(c.get("order_amount_inr", 200.0)))
    
    if avail is not None:
        avail_str = f"₹{avail:,.2f}"
        headroom = max(0.0, float(avail) - deployed)
        headroom_str = f"₹{headroom:,.2f}"
    else:
        avail_str = "CAPITAL UNKNOWN" if mode == "LIVE_MICROCASH" else "DYNAMIC (UNCONSTRAINED)"
        headroom_str = "CAPITAL UNKNOWN" if mode == "LIVE_MICROCASH" else "DYNAMIC (UNCONSTRAINED)"

    open_pos_count = int(c.get("open_positions_count", 0))
    per_bot = c.get("per_bot_allocation", {})

    lines = [
        "💼 <b>CAPITAL ALLOCATION & BROKER STATUS</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Available Capital:</b> <code>{avail_str}</code>",
        f"• <b>Deployed Capital:</b> <code>₹{deployed:,.2f}</code>",
        f"• <b>Available Headroom:</b> <code>{headroom_str}</code>",
        f"• <b>Min Order Size:</b> <code>₹{min_order:,.2f}</code> (Configured: <code>₹{order_amt:,.2f}</code>)",
        f"• <b>Open Positions:</b> <code>{open_pos_count}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Per-Bot Allocation:</b>",
    ]
    if per_bot and any(v > 0 for v in per_bot.values()):
        for bot, alloc in per_bot.items():
            lines.append(f"  • <b>{bot}:</b> ₹{float(alloc):,.2f}")
    else:
        lines.append("  • <i>Unified Dynamic Fleet Allocation</i>")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"• <b>Capital Source:</b> <code>{c.get('source', 'COINDCX_EXCHANGE' if mode == 'LIVE_MICROCASH' else 'SIMULATION')}</code>")
    return "\n".join(lines)


def format_telegram_config(cfg: dict[str, Any]) -> str:
    """Format /config response."""
    mode = cfg.get("mode", "SHADOW")
    order_amt = float(cfg.get("order_amount_inr", 200.0))
    limit = cfg.get("total_capital_limit")
    limit_str = f"₹{limit:,.2f}" if limit is not None else "DYNAMIC"

    return (
        f"⚙️ <b>TRADING CONFIGURATION</b>\n"
        f"<b>MODE: {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Deployment Mode:</b> <code>{mode}</code>\n"
        f"• <b>Trading Enabled:</b> <code>{'YES' if cfg.get('trading_enabled') else 'NO'}</code>\n"
        f"• <b>Configured Order Amount:</b> <code>₹{order_amt:,.2f}</code>\n"
        f"• <b>Capital Budget Limit:</b> <code>{limit_str}</code>\n"
        f"• <b>Max Concurrent Positions:</b> <code>{cfg.get('max_concurrent_positions', 10)}</code>\n"
        f"• <b>Single Coin Lock:</b> <code>{'ENABLED' if cfg.get('enforce_single_coin_lock') else 'DISABLED'}</code>\n"
        f"• <b>AI Model:</b> <code>{cfg.get('ai_model', 'gemini-2.5-flash')}</code>\n"
        f"• <b>Scanner Poll Interval:</b> <code>{cfg.get('scanner_poll_interval', 60)}s</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def format_telegram_reconciliation(r: dict[str, Any], mode: str = "SHADOW") -> str:
    """Format /reconcile report."""
    status = r.get("status", "IN_SYNC")
    icon = "🟢" if status == "IN_SYNC" else "⚠️"
    discs = r.get("discrepancies", [])

    lines = [
        f"🔄 <b>EXCHANGE ORDER RECONCILIATION</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• <b>Reconciliation Status:</b> {icon} <code>{status}</code>",
        f"• <b>Local Positions Checked:</b> <code>{r.get('positions_checked', 0)}</code>",
        f"• <b>Exchange Orders Checked:</b> <code>{r.get('orders_checked', 0)}</code>",
        f"• <b>Mismatches Detected:</b> <code>{r.get('mismatches', 0)}</code>",
        f"• <b>Balance Drift:</b> <code>₹{float(r.get('balance_diff', 0.0)):,.2f}</code>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if not discs:
        lines.append("<i>Zero discrepancy detected between local ledger and exchange.</i>")
    else:
        lines.append("<b>Discrepancies:</b>")
        for d in discs[:3]:
            lines.append(f"  • {d.get('coin', 'ASSET')}: {d.get('exchange_status', 'UNKNOWN')} — {d.get('action', 'FLAGGED')}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_limits(l: dict[str, Any], mode: str = "SHADOW") -> str:
    """Format /limits response."""
    return (
        f"🛡️ <b>RISK ENGINE CONFIGURED LIMITS</b>\n"
        f"<b>MODE: {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Max Daily Drawdown:</b> <code>{l.get('max_drawdown_pct', 10.0)}%</code>\n"
        f"• <b>Max Consecutive Losses (Per Bot):</b> <code>{l.get('max_consecutive_losses', 5)}</code>\n"
        f"• <b>Max Fleet Concurrent Positions:</b> <code>{l.get('max_concurrent_positions', 10)}</code>\n"
        f"• <b>Single Coin Asset Lock:</b> <code>ENABLED</code>\n"
        f"• <b>Statutory Friction Multiplier:</b> <code>1.01572x</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Risk formulas are immutable and enforced before every order dispatch.</i>"
    )


def format_telegram_alerts(alerts: list[dict[str, Any]], mode: str = "SHADOW") -> str:
    """Format /alerts feed."""
    lines = [
        f"🚨 <b>ACTIVE ALERTS & SYSTEM WARNINGS ({len(alerts)})</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if not alerts:
        lines.append("<i>No active alerts. All systems operational.</i>")
    else:
        for a in alerts[:8]:
            ts = a.get("logged_at", "")[:19]
            ev = a.get("event_type", "ALERT")
            src = a.get("source_service", "SYSTEM")
            lines.append(f"• [<code>{ts}</code>] <b>{ev}</b> ({src})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_logs(logs: list[dict[str, Any]], mode: str = "SHADOW") -> str:
    """Format /logs feed with strict secret masking."""
    lines = [
        f"📜 <b>OPERATIONAL EVENT LOGS (LAST {len(logs)})</b>",
        f"<b>MODE: {mode}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if not logs:
        lines.append("<i>No operational logs recorded.</i>")
    else:
        for entry in logs[:10]:
            ts = str(entry.get("logged_at", ""))[:19]
            ev = entry.get("event_type", "EVENT")
            src = entry.get("source_service", "core")
            payload = entry.get("payload", {})
            snippet = str(payload)[:60]
            masked_snippet = mask_sensitive_data(snippet)
            lines.append(f"• <code>{ts}</code> <b>{ev}</b> ({src})\n   <i>{masked_snippet}</i>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_telegram_help() -> str:
    """Format comprehensive help manual listing all 24 operator commands."""
    return (
        "📖 <b>PROJECT-ALPHA V2 OPERATOR COMMANDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>1. System Commands:</b>\n"
        "  • /start — Welcome & Operator Overview\n"
        "  • /help — Show this complete manual\n"
        "  • /status — Comprehensive system health & telemetry\n"
        "  • /health — Component-level diagnostic probes\n"
        "  • /mode — Current execution mode & parameters\n"
        "  • /uptime — Server start time & cycle statistics\n"
        "  • /bots — Active bot fleet status\n\n"
        "<b>2. Scanner Commands:</b>\n"
        "  • /scan — Latest scanner cycle & top candidates\n"
        "  • /signals — High-quality active signals\n"
        "  • /signal &lt;symbol&gt; — Detailed technical breakdown\n"
        "  • /watchlist — Active monitored coins\n"
        "  • /funnel — 5-Layer conversion funnel metrics\n\n"
        "<b>3. Trading Commands:</b>\n"
        "  • /positions — Active open positions & SL/TP\n"
        "  • /trades — Recent executed/closed trades\n"
        "  • /pnl — Realized, unrealized & total P&L\n"
        "  • /orders — Unified orders ledger (PAPER/SHADOW/LIVE)\n"
        "  • /capital — Dynamic capital & CoinDCX live balance\n"
        "  • /config — Current trading configuration\n\n"
        "<b>4. Order Amount Control:</b>\n"
        "  • /setamount &lt;value&gt; — Edit configured order amount (e.g. /setamount 500)\n\n"
        "<b>5. Trading Control:</b>\n"
        "  • /pause — Pause new entries (positions remain open)\n"
        "  • /resume — Resume normal trading operations\n"
        "  • /emergency_stop — Trip circuit breaker & freeze trading\n"
        "  • /reconcile — Run exchange order reconciliation\n\n"
        "<b>6. Risk & Monitoring:</b>\n"
        "  • /risk — Circuit breaker & exposure state\n"
        "  • /limits — Configured loss limits & fleet ceilings\n"
        "  • /alerts — Active alerts & system warnings\n"
        "  • /logs — Recent operational events (secrets scrubbed)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
