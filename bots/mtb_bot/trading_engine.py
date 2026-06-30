"""
MTB MACD Trend Bounce paper trading engine.

Entry logic
───────────
  Scanner signal must pass:
    1. Score          >= MIN_SIGNAL_SCORE   (aggregated EMA + MACD + momentum)
    2. Confidence     >= MIN_CONFIDENCE     (scanner ranking certainty)
    3. Market state   NOT in BLOCKED_MARKET_STATES
    4. Standard filters: watchlist, max positions, signal age, price, cash

Exit logic
──────────
  run_cycle() checks all open positions against current scanner prices:
    • Price >= take_profit_price  → close full position (TAKE_PROFIT)
    • Price <= stop_loss_price    → close full position (STOP_LOSS)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from . import scanner_bridge, storage
from .config import (
    ALLOWED_MARKET_STATES,
    BLOCKED_MARKET_STATES,
    MAX_POSITIONS,
    MAX_SIGNAL_AGE_SECONDS,
    MIN_CONFIDENCE,
    MIN_SIGNAL_SCORE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TRADE_AMOUNT,
)

logger = logging.getLogger("mtb_bot.trading_engine")

# ── Concurrency lock ──────────────────────────────────────────────────────────
# Protects the full check→mutate→save sequence inside open_paper_position()
# and close_position() so that concurrent signals for the same symbol cannot
# both pass the duplicate check and both deduct the cash balance.
_TRADE_LOCK = threading.Lock()


def _send_tg(text: str) -> None:
    """Fire-and-forget Telegram notification. Never raises."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import urllib.request as _ur, json as _json
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        body = _json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req = _ur.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        _ur.urlopen(req, timeout=5)
    except Exception:
        pass


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    code: str
    reason: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _open_position_for_symbol(symbol: str, positions: list[dict]) -> bool:
    return any(
        str(p.get("symbol", "")).upper() == symbol.upper()
        and str(p.get("status", "")).upper() == "OPEN"
        for p in positions
    )


def validate_signal(signal: dict, positions: list[dict] | None = None) -> ValidationResult:
    positions    = positions if positions is not None else storage.load_positions()
    symbol       = str(signal.get("symbol", "")).upper()
    price        = float(signal.get("entry_price") or 0)
    score        = float(signal.get("score") or 0)
    confidence   = float(signal.get("confidence") or score)
    market_state = str(signal.get("market_state", "unknown")).lower()
    coin         = str(signal.get("coin", symbol.replace("USDT", ""))).upper()
    age          = scanner_bridge.signal_age_seconds(signal)

    if not symbol:
        return ValidationResult(False, "MISSING_SYMBOL", "Signal has no symbol.")
    if _open_position_for_symbol(symbol, positions):
        return ValidationResult(False, "DUPLICATE_POSITION", f"Open position already exists for {symbol}.")
    open_count = len([p for p in positions if str(p.get("status", "")).upper() == "OPEN"])
    if open_count >= MAX_POSITIONS:
        return ValidationResult(False, "MAX_POSITIONS_REACHED", "MTB max open positions reached.")
    if age is not None and age > MAX_SIGNAL_AGE_SECONDS:
        return ValidationResult(False, "SIGNAL_TOO_OLD", f"Signal is {int(age)}s old.")
    if price <= 0:
        return ValidationResult(False, "INVALID_ENTRY_PRICE", "Signal has invalid entry price.")

    # ── EMA / MACD / Momentum gates ─────────────────────────────────────────
    if score < MIN_SIGNAL_SCORE:
        return ValidationResult(
            False, "SCORE_TOO_LOW",
            f"Score {score:.0f} below MTB EMA/MACD threshold {MIN_SIGNAL_SCORE}."
        )
    if confidence < MIN_CONFIDENCE:
        return ValidationResult(
            False, "LOW_CONFIDENCE",
            f"Confidence {confidence:.0f} below MTB threshold {MIN_CONFIDENCE}."
        )
    if market_state in BLOCKED_MARKET_STATES:
        return ValidationResult(
            False, "BLOCKED_MARKET_STATE",
            f"Market state '{market_state}' blocked for MTB entry."
        )
    if ALLOWED_MARKET_STATES and market_state not in ALLOWED_MARKET_STATES:
        return ValidationResult(
            False, "UNFAVORABLE_TREND",
            f"Market state '{market_state}' not in MTB allowed states."
        )
    # ── Cash gate ────────────────────────────────────────────────────────────
    stats = storage.load_stats()
    if float(stats.get("cash_balance", 0.0)) < TRADE_AMOUNT:
        return ValidationResult(False, "INSUFFICIENT_CASH", "MTB cash balance below trade amount.")
    return ValidationResult(True, "OK", "Signal accepted — EMA/MACD/Momentum confirmed.")


def open_paper_position(signal: dict) -> dict:
    # ── Shared risk engine gate (outside lock — pure read, no mutation) ───────
    try:
        from bots.risk_engine.engine import check_trade_allowed
        decision = check_trade_allowed("MTB", float(TRADE_AMOUNT))
        if not decision.allowed:
            logger.info("MTB trade blocked by risk engine: %s — %s", decision.code, decision.reason)
            return {"ok": False, "code": decision.code, "reason": decision.reason}
    except Exception as _re:
        logger.warning("MTB risk engine check failed (%s) — proceeding with local guards", _re)

    logger.debug("open_paper_position: acquiring lock for %s", signal.get("symbol", "?"))
    with _TRADE_LOCK:
        logger.debug("open_paper_position: lock acquired for %s", signal.get("symbol", "?"))

        # ── Re-read positions inside lock (state may have changed) ────────────
        positions = storage.load_positions()
        result    = validate_signal(signal, positions)
        if not result.passed:
            logger.debug("open_paper_position: lock released (validation failed: %s)", result.code)
            return {"ok": False, "code": result.code, "reason": result.reason}

        price  = float(signal["entry_price"])
        amount = float(TRADE_AMOUNT)
        qty    = amount / price
        symbol = str(signal["symbol"]).upper()
        coin   = str(signal.get("coin", symbol.replace("USDT", ""))).upper()
        now    = utc_now()

        position = {
            "id":               f"MTB-{symbol}-{int(datetime.now(timezone.utc).timestamp())}",
            "bot":              "MTB",
            "coin":             coin,
            "symbol":           symbol,
            "status":           "OPEN",
            "entry_price":      price,
            "position_size":    qty,
            "quantity":         qty,
            "total_cost":       amount,
            "amount":           amount,
            "trade_amount":     amount,
            "entry_time":       now,
            "source":           signal.get("source", "MTB_SCANNER"),
            "score":            signal.get("score", 0),
            "confidence":       signal.get("confidence", 0),
            "market_state":     signal.get("market_state", ""),
            "take_profit_price": round(price * (1 + TAKE_PROFIT_PCT / 100), 8),
            "stop_loss_price":   round(price * (1 - STOP_LOSS_PCT   / 100), 8),
        }

        # ── Atomic: positions → stats → trades (all inside lock) ─────────────
        positions.append(position)
        storage.save_positions(positions)

        stats = storage.load_stats()
        stats["cash_balance"] = round(float(stats.get("cash_balance", 0.0)) - amount, 8)
        stats["trade_amount"] = amount
        storage.save_stats(stats)

        trades = storage.load_trades()
        trades.append({
            "id":        position["id"],
            "bot":       "MTB",
            "coin":      coin,
            "symbol":    symbol,
            "action":    "BUY",
            "status":    "OPEN",
            "price":     price,
            "amount":    amount,
            "quantity":  qty,
            "timestamp": now,
            "source":    position["source"],
        })
        storage.save_trades(trades)

    # Notifications outside the lock (I/O, never blocks state)
    logger.info("Position opened: MTB BUY %s @ %.6f  amount=%.2f  score=%.0f  conf=%.0f",
                symbol, price, amount, signal.get("score", 0), signal.get("confidence", 0))
    logger.debug("open_paper_position: lock released for %s", symbol)
    _send_tg(
        f"🟢 <b>MTB BUY</b>\n"
        f"Coin: <b>{coin}</b> ({symbol})\n"
        f"Price: {price:,.2f}  Amount: ₹{amount:.0f}\n"
        f"TP: {position['take_profit_price']:,.2f}  SL: {position['stop_loss_price']:,.2f}\n"
        f"Score: {signal.get('score', 0):.0f}  Conf: {signal.get('confidence', 0):.0f}"
    )
    return {"ok": True, "position": position}


def close_position(symbol: str, exit_price: float, reason: str = "MANUAL") -> dict:
    logger.debug("close_position: acquiring lock for %s", symbol)
    with _TRADE_LOCK:
        logger.debug("close_position: lock acquired for %s", symbol)

        positions = storage.load_positions()
        target    = None
        for p in positions:
            if (str(p.get("symbol", "")).upper() == symbol.upper()
                    and str(p.get("status", "")).upper() == "OPEN"):
                target = p
                break
        if target is None:
            logger.info("Duplicate close prevented: no open MTB position for %s (lock held)", symbol)
            return {"ok": False, "reason": f"No open MTB position for {symbol}."}

        qty        = float(target.get("quantity", target.get("position_size", 0.0)))
        cost       = float(target.get("total_cost", target.get("amount", 0.0)))
        proceeds   = qty * float(exit_price)
        pnl        = proceeds - cost
        return_pct = (pnl / cost * 100) if cost else 0.0
        now        = utc_now()

        target.update({
            "status":       "CLOSED",
            "exit_price":   float(exit_price),
            "exit_time":    now,
            "close_reason": reason,
            "pnl":          round(pnl, 8),
            "return_pct":   round(return_pct, 4),
        })
        storage.save_positions(positions)

        trades = storage.load_trades()
        trades.append({
            "id":         target["id"],
            "bot":        "MTB",
            "coin":       target.get("coin"),
            "symbol":     target.get("symbol"),
            "action":     "SELL",
            "status":     "CLOSED",
            "price":      float(exit_price),
            "amount":     round(proceeds, 8),
            "quantity":   qty,
            "pnl":        round(pnl, 8),
            "return_pct": round(return_pct, 4),
            "timestamp":  now,
            "reason":     reason,
        })
        storage.save_trades(trades)

        stats = storage.load_stats()
        stats["cash_balance"] = round(float(stats.get("cash_balance", 0.0)) + proceeds, 8)
        stats["total_pnl"]    = round(float(stats.get("total_pnl",    0.0)) + pnl, 8)
        today = datetime.now(timezone.utc).date().isoformat()
        if stats.get("daily_pnl_date") != today:
            stats["daily_pnl"]      = 0.0
            stats["daily_pnl_date"] = today
        stats["daily_pnl"] = round(float(stats.get("daily_pnl", 0.0)) + pnl, 8)
        storage.save_stats(stats)

    logger.info("Position closed: MTB %s %s @ %.6f  pnl=%.4f  return=%.2f%%",
                reason, symbol, exit_price, pnl, return_pct)
    logger.debug("close_position: lock released for %s", symbol)
    return {"ok": True, "position": target}


def process_signal(signal: dict) -> dict:
    return open_paper_position(signal)


def _get_current_prices() -> dict[str, float]:
    """Return {coin: price} from scanner's latest signals."""
    try:
        signals = scanner_bridge.get_signals()
        return {s["coin"]: float(s["entry_price"]) for s in signals if s.get("entry_price", 0) > 0}
    except Exception:
        return {}


async def run_cycle() -> dict[str, Any]:
    """
    Full MTB cycle:
      1. Check exits (TAKE_PROFIT / STOP_LOSS) on all open positions.
      2. Open new positions from scanner signals that pass EMA/MACD/Momentum gates.
    """
    current_prices = _get_current_prices()
    open_positions = storage.get_open_positions() if hasattr(storage, "get_open_positions") else [
        p for p in storage.load_positions() if str(p.get("status", "")).upper() == "OPEN"
    ]
    exits_tp = exits_sl = 0

    for pos in list(open_positions):
        coin  = pos.get("coin", "")
        price = current_prices.get(coin)
        if price is None or price <= 0:
            continue
        tp = float(pos.get("take_profit_price", 0))
        sl = float(pos.get("stop_loss_price",   0))
        if tp > 0 and price >= tp:
            close_position(pos["symbol"], price, reason="TAKE_PROFIT")
            exits_tp += 1
        elif sl > 0 and price <= sl:
            close_position(pos["symbol"], price, reason="STOP_LOSS")
            exits_sl += 1

    raw_signals = scanner_bridge.get_signals()
    positions_snap = storage.load_positions()
    accepted = rejected = opened = 0
    rejection_reasons: list[dict] = []

    for signal in raw_signals:
        validation = validate_signal(signal, positions_snap)
        if not validation.passed:
            rejected += 1
            rejection_reasons.append({
                "symbol": signal.get("symbol", ""),
                "code": validation.code,
                "reason": validation.reason,
            })
            continue
        result = open_paper_position(signal)
        if result.get("ok"):
            accepted += 1
            opened   += 1
            positions_snap.append(result["position"])
        else:
            rejected += 1
            rejection_reasons.append({
                "symbol": signal.get("symbol", ""),
                "code": result.get("code"),
                "reason": result.get("reason"),
            })

    return {
        "signals_received": len(raw_signals),
        "signals_accepted": accepted,
        "signals_rejected": rejected,
        "positions_opened": opened,
        "exits_take_profit": exits_tp,
        "exits_stop_loss":   exits_sl,
        "rejections":        rejection_reasons[-10:],
        "timestamp":         utc_now(),
    }
