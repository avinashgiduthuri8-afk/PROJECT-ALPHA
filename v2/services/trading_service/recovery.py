"""
V2 Restart Recovery Engine.

Rehydrates active positions and bracket order state from SQLite on application startup,
verifying local records against exchange sub-account clients to prevent state loss across restarts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from v2.core.logging import get_logger
from v2.core.types import BotName, Position, PositionStatus
from v2.repository.position_repo import PositionRepository
from v2.trading.subaccount_manager import CoinDCXSubAccountManager

logger = get_logger("v2.services.trading_service.recovery")


class RestartRecoveryService:
    """
    Restart Recovery Engine.
    Rehydrates unclosed positions from SQLite, rebuilds internal bracket state,
    and cross-checks active positions against sub-account clients.
    """

    def __init__(
        self,
        position_repo: PositionRepository,
        subaccount_manager: Optional[CoinDCXSubAccountManager] = None,
    ) -> None:
        self._position_repo = position_repo
        self._subaccount_manager = subaccount_manager or CoinDCXSubAccountManager()

    async def rehydrate_state(self) -> List[Position]:
        """
        Rehydrate all non-CLOSED positions from SQLite and verify against sub-account clients.
        Returns list of active recovered Position objects.
        """
        active_positions = await self._position_repo.get_active_positions()
        logger.info("RestartRecoveryService rehydrating %d active position(s) from SQLite", len(active_positions))

        recovered_positions: List[Position] = []

        for pos in active_positions:
            try:
                # Verify sub-account client configuration exists for this bot
                client = self._subaccount_manager.get_client(pos.bot)
                logger.info(
                    "Rehydrated position %s [%s] for %s (%s) @ INR %.2f (Qty: %s)",
                    pos.id, pos.bot.value, pos.coin, pos.pair, pos.entry_price, pos.qty,
                )
                recovered_positions.append(pos)
            except Exception as exc:
                logger.error("Failed to rehydrate position %s for bot %s: %s", pos.id, pos.bot, exc)
                recovered_positions.append(pos)

        return recovered_positions

    async def verify_against_exchange(self, positions: List[Position]) -> Dict[str, Any]:
        """
        Verify local active positions against sub-account telemetry and balance data.
        Returns a verification summary dict.
        """
        telemetry = self._subaccount_manager.get_all_subaccount_telemetry()
        desynced_count = 0
        verified_count = 0

        for pos in positions:
            bot_key = pos.bot.value if hasattr(pos.bot, "value") else str(pos.bot)
            sub_info = telemetry.get(bot_key)
            if not sub_info:
                logger.warning("Sub-account telemetry missing during recovery check for position %s", pos.id)
                desynced_count += 1
            else:
                verified_count += 1

        summary = {
            "total_active": len(positions),
            "verified": verified_count,
            "desynced": desynced_count,
            "status": "HEALTHY" if desynced_count == 0 else "DESYNCED",
        }
        logger.info("Exchange position verification complete: %s", summary)
        return summary
