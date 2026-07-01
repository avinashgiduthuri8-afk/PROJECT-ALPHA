"""
PROJECT-ALPHA Shared Risk Engine — configuration.

Single source of truth for capital allocation, per-bot limits,
and the global TRADING_ENABLED / EMERGENCY_STOP kill-switches.
"""

from __future__ import annotations

import logging
import os

_cfg_logger = logging.getLogger("risk_engine.config")

# ── Global kill-switches ──────────────────────────────────────────────────────
# SEC-02: Default is "false" — trading is DENIED when the env var is absent.
# Set TRADING_ENABLED=true explicitly to allow bots to trade.
TRADING_ENABLED: bool = os.getenv("TRADING_ENABLED", "false").lower() == "true"

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

# ── SEC-03: BOT_MODE validation ───────────────────────────────────────────────
# Allowed values (case-sensitive after normalisation to upper-case).
# Any value not in this set is clamped to "DISABLED" and a WARNING is emitted.
_ALLOWED_MODES: frozenset[str] = frozenset({"LIVE", "PAPER", "DISABLED", "PAUSED"})

_BOT_MODE_ENV: dict[str, str] = {
    "VGX": ("VGX_BOT_MODE", os.getenv("VGX_BOT_MODE", "PAPER")),
    "PMB": ("PMB_BOT_MODE", os.getenv("PMB_BOT_MODE", "PAPER")),
    "MTB": ("MTB_BOT_MODE", os.getenv("MTB_BOT_MODE", "PAPER")),
}

def _validate_mode(bot: str, env_var: str, raw: str) -> str:
    normalised = raw.strip().upper()
    if normalised in _ALLOWED_MODES:
        return normalised
    _cfg_logger.warning(
        "SEC-03 [%s] invalid BOT_MODE: env var %s=%r is not in %s — clamping to DISABLED.",
        bot, env_var, raw, sorted(_ALLOWED_MODES),
    )
    return "DISABLED"

# Paper-mode label for each bot (LIVE / PAPER / DISABLED / PAUSED).
BOT_MODE: dict[str, str] = {
    bot: _validate_mode(bot, env_var, raw)
    for bot, (env_var, raw) in _BOT_MODE_ENV.items()
}
