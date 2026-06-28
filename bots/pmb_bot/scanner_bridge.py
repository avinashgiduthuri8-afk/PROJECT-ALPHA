"""
PMB scanner bridge.

Reads from in-process LATEST_MTB_SIGNALS (scanner_bot.main) first,
falls back to the dashboard REST API /api/v1/state.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import SCANNER_API_URL, SCANNER_TIMEOUT_SECONDS

logger = logging.getLogger("pmb_bot.scanner_bridge")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_signal(signal: dict) -> dict | None:
    coin = str(signal.get("coin") or signal.get("symbol") or "").upper().strip()
    if not coin:
        return None
    coin = coin.replace("USDT", "")
    symbol = f"{coin}USDT"
    price = signal.get("signal_price", signal.get("price", signal.get("entry_price", 0)))
    try:
        entry_price = float(price or 0)
    except (TypeError, ValueError):
        entry_price = 0.0
    score = signal.get("score", signal.get("confidence", 0))
    try:
        score_value = float(score or 0)
    except (TypeError, ValueError):
        score_value = 0.0
    timestamp = signal.get("timestamp") or datetime.now(timezone.utc).isoformat()
    return {
        "coin":         coin,
        "symbol":       symbol,
        "action":       "BUY",
        "entry_price":  entry_price,
        "score":        score_value,
        "priority":     signal.get("priority") or signal.get("category") or signal.get("tier") or "",
        "market_state": signal.get("market_state", ""),
        "confidence":   signal.get("confidence", score_value),
        "coin_class":   signal.get("coin_class", "C"),
        "source":       "PMB_SCANNER",
        "timestamp":    timestamp,
        "raw":          signal,
    }


def _signals_from_module() -> list[dict]:
    try:
        from bots.scanner_bot import main as scanner_main
    except Exception:
        return []
    signals = getattr(scanner_main, "LATEST_MTB_SIGNALS", []) or []
    normalized = [_normalize_signal(s) for s in signals if isinstance(s, dict)]
    return [s for s in normalized if s is not None]


def _signals_from_dashboard_api() -> list[dict]:
    url = f"{SCANNER_API_URL}/api/v1/state"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=SCANNER_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.warning("PMB scanner API fetch failed: %s", exc)
        return []
    recent = payload.get("recent_signals", []) if isinstance(payload, dict) else []
    normalized = [_normalize_signal(s) for s in recent if isinstance(s, dict)]
    return [s for s in normalized if s is not None]


def get_signals() -> list[dict]:
    module_signals = _signals_from_module()
    if module_signals:
        return module_signals
    return _signals_from_dashboard_api()


def get_current_prices() -> dict[str, float]:
    """Return {coin: current_price} from latest scanner signals."""
    signals = get_signals()
    return {s["coin"]: float(s["entry_price"]) for s in signals if s.get("entry_price", 0) > 0}


def get_market_state() -> str:
    try:
        from bots.scanner_bot import main as scanner_main
        state = getattr(scanner_main, "LATEST_MARKET_STATE", {})
        return state.get("market_state", "unknown")
    except Exception:
        return "unknown"


def signal_age_seconds(signal: dict) -> float | None:
    parsed = _parse_time(signal.get("timestamp"))
    if parsed is None:
        return None
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def check_scanner_health() -> bool:
    return bool(get_signals())
