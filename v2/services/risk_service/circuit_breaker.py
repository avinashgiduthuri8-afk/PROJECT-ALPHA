"""
V2 CircuitBreaker — emergency halts, consecutive loss tracking, and drawdown gates.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from v2.core.config import V2Config
from v2.core.types import BotName, RiskDecision
from v2.core.logging import get_logger

logger = get_logger("v2.services.risk_service.circuit_breaker")


class CircuitBreaker:
    """Monitors strategy degradation, drawdown spikes, and loss streaks."""

    def __init__(self, config: V2Config) -> None:
        self._config = config
        self._is_open = False
        self._emergency_stop = False
        self._reason: Optional[str] = None
        self._tripped_at: Optional[datetime] = None
        self._consecutive_losses: dict[str, int] = {
            BotName.STE.value: 0,
            BotName.HDA.value: 0,
            BotName.VCP.value: 0,
            BotName.BBS.value: 0,
        }

    @property
    def is_open(self) -> bool:
        return self._is_open or self._emergency_stop

    @property
    def emergency_stop(self) -> bool:
        return self._emergency_stop

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    @property
    def tripped_at(self) -> Optional[datetime]:
        return self._tripped_at

    def trip(self, reason: str) -> None:
        self._is_open = True
        self._reason = reason
        self._tripped_at = datetime.now(timezone.utc)
        logger.critical("Circuit breaker TRIPPED", extra={"reason": reason})

    def set_emergency_stop(self, enabled: bool, reason: str = "Manual Emergency Stop") -> None:
        self._emergency_stop = enabled
        if enabled:
            self._reason = reason
            self._tripped_at = datetime.now(timezone.utc)
            logger.critical("Emergency stop ACTIVATED", extra={"reason": reason})
        else:
            self._reason = None
            logger.info("Emergency stop DEACTIVATED")

    def reset(self) -> None:
        self._is_open = False
        self._emergency_stop = False
        self._reason = None
        self._tripped_at = None
        for b in self._consecutive_losses:
            self._consecutive_losses[b] = 0
        logger.info("Circuit breaker RESET to normal operation")

    def check_breaker(self, bot: BotName, amount: float = 0.0) -> RiskDecision:
        t0 = time.perf_counter()
        if self._emergency_stop:
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_EMERGENCY_STOP",
                reason=f"Emergency stop active: {self._reason or 'Manual kill switch'}.",
                bot=bot,
                amount=amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        if self._is_open:
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_CIRCUIT_BREAKER",
                reason=f"Circuit breaker is OPEN: {self._reason or 'Threshold exceeded'}.",
                bot=bot,
                amount=amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        losses = self._consecutive_losses.get(bot.value, 0)
        if losses >= self._config.v2_max_consecutive_losses:
            self.trip(f"{bot.value} exceeded max consecutive losses ({losses}/{self._config.v2_max_consecutive_losses})")
            ms = (time.perf_counter() - t0) * 1000.0
            return RiskDecision(
                allowed=False,
                code="BLOCKED_CIRCUIT_BREAKER",
                reason=f"{bot.value} exceeded max consecutive losses ({losses}).",
                bot=bot,
                amount=amount,
                adjusted_amount=0.0,
                check_ms=round(ms, 2),
            )

        ms = (time.perf_counter() - t0) * 1000.0
        return RiskDecision(
            allowed=True,
            code="ALLOWED",
            reason="Circuit breaker normal.",
            bot=bot,
            amount=amount,
            adjusted_amount=amount,
            check_ms=round(ms, 2),
        )

    def record_trade_result(self, bot: BotName, pnl: float) -> None:
        key = bot.value
        if pnl < 0:
            self._consecutive_losses[key] = self._consecutive_losses.get(key, 0) + 1
            losses = self._consecutive_losses[key]
            if losses >= self._config.v2_max_consecutive_losses:
                self.trip(f"{key} hit {losses} consecutive loss trades.")
        else:
            self._consecutive_losses[key] = 0
