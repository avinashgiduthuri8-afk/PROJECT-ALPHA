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
        active_positions: Optional[list] = None,
        current_coin: Optional[str] = None,
    ) -> RiskDecision:
        t0 = time.perf_counter()

        # 1. Single-Coin Asset Deduplication & Fleet Lock Check
        if self._config.enforce_single_coin_lock and current_coin and active_positions:
            coin_clean = current_coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
            for pos in active_positions:
                pos_coin = getattr(pos, "coin", "") or ""
                pos_pair = getattr(pos, "pair", "") or ""
                pos_clean = pos_coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
                if pos_clean == coin_clean or coin_clean in pos_pair.upper():
                    ms = (time.perf_counter() - t0) * 1000.0
                    return RiskDecision(
                        allowed=False,
                        code="OPPORTUNITY_LOCKED_ACTIVE_PAIR",
                        reason=f"Asset {coin_clean} already has an active open position in the fleet ({getattr(pos, 'bot', 'BOT')}).",
                        bot=bot,
                        amount=requested_amount,
                        adjusted_amount=0.0,
                        check_ms=round(ms, 2),
                    )

        # 2. Max Fleet-Wide Concurrency Cap Check
        if active_positions is not None and len(active_positions) >= self._config.max_concurrent_positions:
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_MAX_FLEET_POSITIONS",
                reason=f"Max fleet-wide concurrent positions reached ({len(active_positions)}/{self._config.max_concurrent_positions}).",
                bot=bot,
                amount=requested_amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        # 3. Check Max Open Positions (Per Strategy)
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

        # 4. Check Per-Bot Capital Limit (if discrete allocation configured)
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

        # 5. Check Unified Global Capital Pool Limit (Shared Ceiling, None = dynamic)
        total_limit = self._config.total_capital_limit
        if total_limit is not None and total_limit > 0 and (total_deployed + requested_amount) > total_limit:
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
