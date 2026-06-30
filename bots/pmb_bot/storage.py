"""
PROJECT-ALPHA PMB Bot local JSON storage.

Files: data/watchlist.json, data/positions.json, data/trades.json, data/stats.json.
All writes are atomic (tmp→replace) with .bak backups.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    DATA_DIR,
    INITIAL_CASH_BALANCE,
    BASE_BUY,
    POSITIONS_FILE,
    STATS_FILE,
    TRADES_FILE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup = path.with_suffix(path.suffix + ".bak")
        if backup.exists():
            try:
                return json.loads(backup.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return default


def _write_json(path: Path, data: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        except OSError:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not POSITIONS_FILE.exists():
        _write_json(POSITIONS_FILE, {"positions": []})
    if not TRADES_FILE.exists():
        _write_json(TRADES_FILE, {"trades": []})
    if not STATS_FILE.exists():
        _write_json(STATS_FILE, {
            "cash_balance":  INITIAL_CASH_BALANCE,
            "total_invested": 0.0,
            "total_pnl":     0.0,
            "daily_pnl":     0.0,
            "last_updated":  utc_now(),
        })


def _scanner_watchlist() -> list[str]:
    """Read the unified scanner watchlist (single source of truth)."""
    try:
        from bots.scanner_bot.scanner import get_watchlist
        wl = get_watchlist()
        coins = wl.get("coins", [])
        return [str(c).upper().strip() for c in coins if str(c).strip()]
    except Exception:
        return []


def load_positions() -> list[dict]:
    ensure_storage()
    data = _read_json(POSITIONS_FILE, {"positions": []})
    return data.get("positions", []) if isinstance(data, dict) else []


def save_positions(positions: list[dict]) -> None:
    _write_json(POSITIONS_FILE, {"positions": positions})


def load_trades() -> list[dict]:
    ensure_storage()
    data = _read_json(TRADES_FILE, {"trades": []})
    return data.get("trades", []) if isinstance(data, dict) else []


def save_trades(trades: list[dict]) -> None:
    _write_json(TRADES_FILE, {"trades": trades})


def load_stats() -> dict:
    ensure_storage()
    data = _read_json(STATS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("cash_balance",  INITIAL_CASH_BALANCE)
    data.setdefault("total_invested", 0.0)
    data.setdefault("total_pnl",     0.0)
    data.setdefault("daily_pnl",     0.0)
    data.setdefault("last_updated",  utc_now())
    return data


def save_stats(stats: dict) -> None:
    stats = dict(stats)
    stats["last_updated"] = utc_now()
    _write_json(STATS_FILE, stats)


def get_open_positions() -> list[dict]:
    return [p for p in load_positions() if str(p.get("status", "")).upper() == "OPEN"]


def get_closed_trades() -> list[dict]:
    return [t for t in load_trades() if str(t.get("status", "")).upper() == "CLOSED"]


def snapshot() -> dict:
    positions   = load_positions()
    trades      = load_trades()
    stats       = load_stats()
    open_pos    = [p for p in positions if str(p.get("status", "")).upper() == "OPEN"]
    return {
        "status":         "INTEGRATED",
        "open_positions": open_pos,
        "closed_trades":  trades[-50:],
        "daily_pnl":      round(float(stats.get("daily_pnl",     0.0)), 4),
        "total_pnl":      round(float(stats.get("total_pnl",     0.0)), 4),
        "trade_amount":   float(BASE_BUY),
        "cash_balance":   round(float(stats.get("cash_balance",  0.0)), 4),
        "watchlist":      _scanner_watchlist(),
        "last_updated":   stats.get("last_updated"),
    }


ensure_storage()
