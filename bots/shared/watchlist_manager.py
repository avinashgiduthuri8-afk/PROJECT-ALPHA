"""
PROJECT-ALPHA — Shared Watchlist Manager
Handles per-bot watchlists with strict isolation.

I-11: Scanner Universe Sync
- Scanner universe is the union of all bot watchlists.
- Every add/remove syncs to the scanner's watchlist file.
- Scanner always sees the latest universe via disk-reload.
"""

import json
import os
import time
from typing import List

_BOT_DIRS = {
    "vgx": os.path.join(os.path.dirname(os.path.dirname(__file__)), "volatile_gridX", "data"),
    "pmb": os.path.join(os.path.dirname(os.path.dirname(__file__)), "pmb_bot", "data"),
    "mtb": os.path.join(os.path.dirname(os.path.dirname(__file__)), "mtb_bot", "data"),
}

_DEFAULTS = {
    "vgx": ["BTC", "ETH", "SOL"],
    "pmb": ["BTC", "XRP", "DOGE"],
    "mtb": ["ETH", "SOL", "ADA"],
}

# I-11: Single scanner universe file (union of all bot watchlists)
_SCANNER_UNIVERSE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "scanner_bot", "data", "watchlist.json"
)


def _path(bot: str) -> str:
    return os.path.join(_BOT_DIRS[bot.lower()], "watchlist.json")


_QUOTE_SUFFIXES = ("USDT", "BUSD", "INR", "BTC")


def _normalize_coin(coin: str) -> str:
    """Strip known quote suffixes so BTCINR → BTC, ETHUSDT → ETH, etc.
    Consistent with scanner WatchlistStore._load() normalization."""
    c = str(coin).upper().strip()
    for suffix in _QUOTE_SUFFIXES:
        if c.endswith(suffix) and len(c) > len(suffix):
            return c[: -len(suffix)]
    return c


def _ensure(bot: str):
    p = _path(bot)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        with open(p, "w") as f:
            json.dump({"coins": _DEFAULTS[bot], "updated_at": None}, f, indent=2)


def load_watchlist(bot: str) -> dict:
    bot = bot.lower()
    _ensure(bot)
    with open(_path(bot), "r") as f:
        return json.load(f)


def save_watchlist(bot: str, data: dict):
    bot = bot.lower()
    _ensure(bot)
    data["updated_at"] = int(time.time())
    with open(_path(bot), "w") as f:
        json.dump(data, f, indent=2)


def _scanner_universe() -> list:
    """Return the current scanner universe coins from disk."""
    if not os.path.exists(_SCANNER_UNIVERSE_FILE):
        return []
    try:
        with open(_SCANNER_UNIVERSE_FILE, "r") as f:
            return json.load(f).get("coins", [])
    except (json.JSONDecodeError, OSError):
        return []


def _write_scanner_universe(coins: list):
    """Write the scanner universe to disk."""
    os.makedirs(os.path.dirname(_SCANNER_UNIVERSE_FILE), exist_ok=True)
    with open(_SCANNER_UNIVERSE_FILE, "w") as f:
        json.dump({"coins": sorted(set(coins)), "updated_at": int(time.time())}, f, indent=2)


def _sync_scanner_universe():
    """Sync scanner universe = union of all bot watchlists (deduplicated)."""
    universe = set()
    for bot in ("vgx", "pmb", "mtb"):
        data = load_watchlist(bot)
        universe.update(c.get("coin", c) if isinstance(c, dict) else c for c in data.get("coins", []))
    _write_scanner_universe(list(universe))


def add_coin(bot: str, coin: str) -> dict:
    data = load_watchlist(bot)
    coin = _normalize_coin(coin)
    if coin not in data["coins"]:
        data["coins"].append(coin)
    save_watchlist(bot, data)
    _sync_scanner_universe()  # I-11: keep scanner universe in sync
    return data


def remove_coin(bot: str, coin: str) -> dict:
    data = load_watchlist(bot)
    coin = _normalize_coin(coin)
    if coin in data["coins"]:
        data["coins"].remove(coin)
    save_watchlist(bot, data)
    _sync_scanner_universe()  # I-11: keep scanner universe in sync
    return data


def all_watchlists() -> dict:
    return {
        "vgx": load_watchlist("vgx"),
        "pmb": load_watchlist("pmb"),
        "mtb": load_watchlist("mtb"),
    }


def get_scanner_universe() -> dict:
    """I-11: Return the unified scanner universe (single source of truth)."""
    return {"coins": _scanner_universe()}
