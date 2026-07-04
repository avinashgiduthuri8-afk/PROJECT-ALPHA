"""
PROJECT-ALPHA Shared Risk Engine — guard logic.

All bots MUST call `check_trade_allowed(bot, amount)` before opening
any position. The engine reads live position totals directly from each
bot's storage module so no extra state is maintained here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import (
    BOT_CAPITAL_LIMIT,
    BOT_MODE,
    EMERGENCY_STOP,
    MAX_POSITIONS,
    TOTAL_CAPITAL_LIMIT,
    TRADE_CONFIG,
    TRADING_ENABLED,
)

logger = logging.getLogger("risk_engine")


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    code: str
    reason: str


def _load_bot_positions(bot: str) -> list[dict]:
    """Return current open positions for `bot` without raising on import failure."""
    try:
        if bot == "PMB":
            from bots.pmb_bot.storage import get_open_positions
            return get_open_positions()
        if bot == "MTB":
            from bots.mtb_bot.storage import get_open_positions
            return get_open_positions()
        if bot == "VGX":
            from bots.volatile_gridX.storage import get_open_positions
            return get_open_positions()
    except Exception as exc:
        logger.warning("Risk engine could not load %s positions: %s", bot, exc)
    return []


def _deployed_capital(positions: list[dict]) -> float:
    """Sum of `total_cost` / `total_invested` / `amount` across open positions."""
    total = 0.0
    for p in positions:
        for key in ("total_invested", "total_cost", "amount", "trade_amount"):
            val = p.get(key)
            if val is not None:
                try:
                    total += float(val)
                    break
                except (TypeError, ValueError):
                    pass
    return total


def check_trade_allowed(bot: str, amount: float) -> RiskDecision:
    """
    Return RiskDecision.allowed=True only when:
      1. TRADING_ENABLED is True
      2. EMERGENCY_STOP is False
      3. Bot mode is not DISABLED or PAUSED
      4. Proposed `amount` keeps bot within BOT_CAPITAL_LIMIT
      5. Total deployed capital + `amount` stays within TOTAL_CAPITAL_LIMIT
    """
    bot = bot.upper()

    if not TRADING_ENABLED:
        return RiskDecision(False, "TRADING_DISABLED",
                            "Global TRADING_ENABLED flag is False — all bots halted.")

    if EMERGENCY_STOP:
        return RiskDecision(False, "EMERGENCY_STOP",
                            "EMERGENCY_STOP is active — no new trades allowed.")

    mode = BOT_MODE.get(bot, "DISABLED")
    if mode in ("DISABLED", "PAUSED"):
        return RiskDecision(False, "BOT_INACTIVE",
                            f"{bot} is {mode}. Set {bot}_BOT_MODE=PAPER or LIVE to enable.")

    bot_positions    = _load_bot_positions(bot)
    bot_deployed     = _deployed_capital(bot_positions)
    bot_limit        = BOT_CAPITAL_LIMIT.get(bot, 0)
    if bot_deployed + amount > bot_limit:
        return RiskDecision(False, "BOT_CAPITAL_LIMIT_EXCEEDED",
                            f"{bot} deployed={bot_deployed:.0f} + {amount:.0f} "
                            f"> limit={bot_limit:.0f}")

    all_bots         = ["VGX", "PMB", "MTB"]
    total_deployed   = sum(_deployed_capital(_load_bot_positions(b)) for b in all_bots)
    if total_deployed + amount > TOTAL_CAPITAL_LIMIT:
        return RiskDecision(False, "TOTAL_CAPITAL_LIMIT_EXCEEDED",
                            f"Total deployed={total_deployed:.0f} + {amount:.0f} "
                            f"> limit={TOTAL_CAPITAL_LIMIT:.0f}")

    return RiskDecision(True, "OK",
                        f"{bot} trade of {amount:.0f} approved (mode={mode}).")


def snapshot() -> dict[str, Any]:
    """Return a dashboard-ready risk engine status snapshot."""
    bot_states: dict[str, Any] = {}
    total_deployed = 0.0
    for bot in ["VGX", "PMB", "MTB"]:
        positions = _load_bot_positions(bot)
        deployed  = _deployed_capital(positions)
        total_deployed += deployed
        bot_states[bot] = {
            "mode":              BOT_MODE.get(bot, "DISABLED"),
            "trade_amount":      TRADE_CONFIG.get(bot, 0),
            "capital_limit":     BOT_CAPITAL_LIMIT.get(bot, 0),
            "deployed_capital":  round(deployed, 2),
            "open_positions":    len(positions),
            "max_positions":     MAX_POSITIONS.get(bot, 0),
        }
    return {
        "trading_enabled":    TRADING_ENABLED,
        "emergency_stop":     EMERGENCY_STOP,
        "total_capital_limit": TOTAL_CAPITAL_LIMIT,
        "total_deployed":     round(total_deployed, 2),
        "capital_utilisation_pct": round(total_deployed / TOTAL_CAPITAL_LIMIT * 100, 1) if TOTAL_CAPITAL_LIMIT else 0,
        "bots":               bot_states,
        "last_updated":       datetime.now(timezone.utc).isoformat(),
    }
