"""
PROJECT-ALPHA — Unified Scanner Watchlist Manager

V1 Architecture: Scanner is the single source of truth.
All bots read scanner watchlist directly — no per-bot watchlists.
"""

import json
import os
import time
from typing import List

# Scanner watchlist is the single source of truth
_SCANNER_WATCHLIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "scanner_bot", "data", "watchlist.json"
)

# Old bot watchlist files for one-time migration
_OLD_BOT_FILES = {
    "vgx": os.path.join(os.path.dirname(os.path.dirname(__file__)), "volatile_gridX", "data", "watchlist.json"),
    "pmb": os.path.join(os.path.dirname(os.path.dirname(__file__)), "pmb_bot", "data", "watchlist.json"),
    "mtb": os.path.join(os.path.dirname(os.path.dirname(__file__)), "mtb_bot", "data", "watchlist.json"),
}

_QUOTE_SUFFIXES = ("USDT", "BUSD", "INR", "BTC")


def _normalize_coin(coin: str) -> str:
    """Strip known quote suffixes so BTCINR -> BTC, ETHUSDT -> ETH, etc."""
    c = str(coin).upper().strip()
    for suffix in _QUOTE_SUFFIXES:
        if c.endswith(suffix) and len(c) > len(suffix):
            return c[:-len(suffix)]
    return c


def _read_scanner_watchlist() -> list:
    """Read the scanner watchlist from disk."""
    if not os.path.exists(_SCANNER_WATCHLIST_FILE):
        return []
    try:
        with open(_SCANNER_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("coins", [])
    except (json.JSONDecodeError, OSError):
        return []


def _write_scanner_watchlist(coins: list) -> None:
    """Write the scanner watchlist to disk."""
    os.makedirs(os.path.dirname(_SCANNER_WATCHLIST_FILE), exist_ok=True)
    with open(_SCANNER_WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump({"coins": sorted(set(coins)), "updated_at": int(time.time())}, f, indent=2)


def _migrate_old_bot_watchlists() -> list:
    """
    One-time migration: if old bot watchlist files exist, merge their unique
    coins into the scanner watchlist, then log the migration.
    """
    migrated_coins = set()
    sources = []
    for bot, path in _OLD_BOT_FILES.items():
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                coins = data.get("coins", [])
                for c in coins:
                    coin = _normalize_coin(c) if isinstance(c, str) else _normalize_coin(str(c))
                    if coin:
                        migrated_coins.add(coin)
                sources.append(bot)
            except (json.JSONDecodeError, OSError):
                pass

    if not migrated_coins:
        return []

    # Merge with existing scanner watchlist
    existing = set(_read_scanner_watchlist())
    new_coins = migrated_coins - existing
    if new_coins:
        _write_scanner_watchlist(list(existing | migrated_coins))

    return sorted(new_coins)


# Run migration on first import (only when old files exist)
_MIGRATION_RESULT = None


def ensure_migration():
    """Run one-time migration of old bot watchlists into scanner watchlist."""
    global _MIGRATION_RESULT
    if _MIGRATION_RESULT is not None:
        return _MIGRATION_RESULT
    _MIGRATION_RESULT = _migrate_old_bot_watchlists()
    return _MIGRATION_RESULT


def get_scanner_universe() -> dict:
    """Return the unified scanner universe (single source of truth)."""
    ensure_migration()
    return {"coins": _read_scanner_watchlist()}


def add_coin(coin: str) -> dict:
    """Add a coin to the scanner watchlist."""
    ensure_migration()
    coin = _normalize_coin(coin)
    coins = set(_read_scanner_watchlist())
    if coin not in coins:
        coins.add(coin)
        _write_scanner_watchlist(list(coins))
    return {"coins": sorted(coins)}


def remove_coin(coin: str) -> dict:
    """Remove a coin from the scanner watchlist."""
    ensure_migration()
    coin = _normalize_coin(coin)
    coins = set(_read_scanner_watchlist())
    if coin in coins:
        coins.remove(coin)
        _write_scanner_watchlist(list(coins))
    return {"coins": sorted(coins)}
