"""
PROJECT-ALPHA Shared Risk Engine — configuration.

Single source of truth for capital allocation, per-bot limits,
and the global TRADING_ENABLED / EMERGENCY_STOP kill-switches.
"""

from __future__ import annotations

import os
import threading

# ── Global kill-switches ──────────────────────────────────────────────────────
# Set TRADING_ENABLED=false to halt ALL bots (VGX, PMB, MTB).
TRADING_ENABLED: bool = os.getenv("TRADING_ENABLED", "false").lower() == "true"

# ── In-memory runtime toggle ──────────────────────────────────────────────────
# Initialised from the env-var default above; updated at runtime by the
# dashboard toggle (POST /api/v1/trading/toggle).  Intentionally NOT persisted
# to disk — the flag resets to the env-var default on every process restart.
_trading_lock: threading.Lock = threading.Lock()
_trading_enabled: bool = TRADING_ENABLED


def get_trading_enabled() -> bool:
    """Return the live in-memory TRADING_ENABLED flag."""
    with _trading_lock:
        return _trading_enabled


def set_trading_enabled(value: bool) -> bool:
    """Set the live in-memory TRADING_ENABLED flag and return its new value."""
    global _trading_enabled
    with _trading_lock:
        _trading_enabled = bool(value)
        return _trading_enabled

# Set EMERGENCY_STOP=true to immediately block any new trade across all bots.
EMERGENCY_STOP: bool = os.getenv("EMERGENCY_STOP", "false").lower() == "true"

# ── Capital allocation per bot (INR paper units) ──────────────────────────────
TRADE_CONFIG: dict[str, float] = {
    "VGX": float(os.getenv("VGX_TRADE_AMOUNT",  "500")),
    "PMB": float(os.getenv("PMB_TRADE_AMOUNT",  "100")),
    "MTB": float(os.getenv("MTB_TRADE_AMOUNT",  "200")),
}

# Aggregate limit: total deployed capital across ALL bots at any moment.
TOTAL_CAPITAL_LIMIT: float = float(os.getenv("TOTAL_CAPITAL_LIMIT", "10000"))

# Per-bot limit: max capital a single bot may have deployed simultaneously.
BOT_CAPITAL_LIMIT: dict[str, float] = {
    "VGX": float(os.getenv("VGX_CAPITAL_LIMIT", "5000")),
    "PMB": float(os.getenv("PMB_CAPITAL_LIMIT", "3000")),
    "MTB": float(os.getenv("MTB_CAPITAL_LIMIT", "2000")),
}

# Max open positions per bot.
MAX_POSITIONS: dict[str, int] = {
    "VGX": int(os.getenv("VGX_MAX_POSITIONS", "5")),
    "PMB": int(os.getenv("PMB_MAX_POSITIONS", "5")),
    "MTB": int(os.getenv("MTB_MAX_POSITIONS", "3")),
}

# Paper-mode label for each bot (LIVE / PAPER / DISABLED / PAUSED).
BOT_MODE: dict[str, str] = {
    "VGX": os.getenv("VGX_BOT_MODE", "PAPER"),
    "PMB": os.getenv("PMB_BOT_MODE", "PAPER"),
    "MTB": os.getenv("MTB_BOT_MODE", "PAPER"),
}
