"""
V2 CapitalGuard — deterministic capital limit and max-position gating.
"""

from __future__ import annotations

import time
from typing import Optional

from v2.core.config import V2Config
from v2.core.types import BotName, RiskDecision
from v2.core.logging import get_logger

logger = get_logger("v2.services.risk_service.capital_guard")


class CapitalGuard:
    """Enforces per-bot and cross-bot capital limits and maximum open position caps."""

    def __init__(self, config: V2Config) -> None:
        self._config = config

    def check_trade(
        self,
        bot: BotName,
        requested_amount: float,
        current_bot_deployed: float,
        total_deployed: float,
        current_bot_positions: int,
    ) -> RiskDecision:
        t0 = time.perf_counter()
        
        # 1. Check Max Open Positions
        max_pos = self._get_max_positions(bot)
        if current_bot_positions >= max_pos:
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_MAX_POSITIONS",
                reason=f"Max position limit reached for {bot.value} ({current_bot_positions}/{max_pos}).",
                bot=bot,
                amount=requested_amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        # 2. Check Per-Bot Capital Limit
        bot_limit = self._get_bot_capital_limit(bot)
        if bot_limit > 0 and (current_bot_deployed + requested_amount) > bot_limit:
            available = max(0.0, bot_limit - current_bot_deployed)
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_BOT_CAPITAL",
                reason=f"{bot.value} capital limit exceeded: requested ₹{requested_amount:.2f}, available ₹{available:.2f} (limit ₹{bot_limit:.2f}).",
                bot=bot,
                amount=requested_amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        # 3. Check Total Global Portfolio Capital Limit
        total_limit = self._config.total_capital_limit
        if total_limit > 0 and (total_deployed + requested_amount) > total_limit:
            available = max(0.0, total_limit - total_deployed)
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_TOTAL_CAPITAL",
                reason=f"Total portfolio capital limit exceeded: requested ₹{requested_amount:.2f}, available ₹{available:.2f} (limit ₹{total_limit:.2f}).",
                bot=bot,
                amount=requested_amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        ms = (time.perf_counter() - t0) * 1000.0
        return RiskDecision(
            allowed=True,
            code="ALLOWED",
            reason=f"Capital checks passed for {bot.value}.",
            bot=bot,
            amount=requested_amount,
            adjusted_amount=requested_amount,
            check_ms=round(ms, 2),
        )

    def _get_bot_capital_limit(self, bot: BotName) -> float:
        if bot == BotName.STE:
            return self._config.ste_capital_limit
        if bot == BotName.HDA:
            return self._config.hda_capital_limit
        if bot == BotName.VCP:
            return self._config.vcp_capital_limit
        if bot == BotName.BBS:
            return self._config.bbs_capital_limit
        return 0.0

    def _get_max_positions(self, bot: BotName) -> int:
        if bot == BotName.STE:
            return self._config.v2_max_positions_ste
        if bot == BotName.HDA:
            return self._config.v2_max_positions_hda
        if bot == BotName.VCP:
            return self._config.v2_max_positions_vcp
        if bot == BotName.BBS:
            return self._config.v2_max_positions_bbs
        return 5
