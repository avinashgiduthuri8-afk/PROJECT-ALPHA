"""
V2 ShadowEngine — simulates order lifecycle, stop loss, take profit, and PnL metrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.types import BotName, ShadowTrade
from v2.core.logging import get_logger
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.shadow_repo import ShadowRepository

logger = get_logger("v2.services.shadow_service.engine")


class ShadowEngine:
    """Executes simulated paper trades in shadow mode without live order placement."""

    def __init__(
        self,
        bus: EventBus,
        shadow_repo: ShadowRepository,
        event_log_repo: EventLogRepository,
        config: V2Config,
    ) -> None:
        self._bus = bus
        self._shadow_repo = shadow_repo
        self._event_log = event_log_repo
        self._config = config

    async def record_approved_trade(
        self,
        signal_id: str,
        bot: BotName,
        coin: str,
        pair: str,
        entry_price: float,
        qty: float,
        amount: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        ai_recommendation: Optional[str] = "APPROVE",
        raw_adjustments: Optional[dict] = None,
    ) -> ShadowTrade:
        """Create and persist a new simulated shadow trade."""
        now = datetime.now(timezone.utc)
        trade = ShadowTrade(
            id=str(uuid.uuid4()),
            signal_id=signal_id,
            bot=bot,
            coin=coin.upper(),
            pair=pair,
            entry_price=entry_price,
            qty=qty,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            ai_recommendation=ai_recommendation,
            status="OPEN",
            created_at=now,
            raw_adjustments=raw_adjustments or {},
        )

        await self._shadow_repo.insert_shadow_trade(trade)

        trade_payload = {
            "shadow_trade_id": trade.id,
            "signal_id": signal_id,
            "bot": bot.value,
            "coin": coin,
            "pair": pair,
            "entry_price": entry_price,
            "qty": qty,
            "amount": amount,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "ai_recommendation": ai_recommendation,
            "created_at": now.isoformat(),
        }

        await self._bus.publish(EventType.SHADOW_TRADE_RECORDED, trade_payload)
        await self._event_log.append(
            event_type=EventType.SHADOW_TRADE_RECORDED.value,
            source_service="shadow_engine",
            entity_id=trade.id,
            payload=trade_payload,
        )
        logger.info("Shadow trade RECORDED", extra={"coin": coin, "bot": bot.value, "amount": amount})
        return trade

    async def evaluate_prices(self, price_map: dict[str, float]) -> list[ShadowTrade]:
        """Check all open shadow trades against market price map for SL/TP executions."""
        open_trades = await self._shadow_repo.get_open_shadow_trades()
        closed_trades: list[ShadowTrade] = []
        now = datetime.now(timezone.utc)

        for trade in open_trades:
            curr_price = price_map.get(trade.coin) or price_map.get(trade.pair)
            if curr_price is None or curr_price <= 0.0:
                continue

            hit_tp = trade.take_profit is not None and curr_price >= trade.take_profit
            hit_sl = trade.stop_loss is not None and curr_price <= trade.stop_loss

            if hit_tp or hit_sl:
                exit_price = trade.take_profit if hit_tp else trade.stop_loss
                if exit_price is None:
                    exit_price = curr_price

                pnl = (exit_price - trade.entry_price) * trade.qty
                pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100.0

                trade.status = "CLOSED_TP" if hit_tp else "CLOSED_SL"
                trade.exit_reason = "TAKE_PROFIT" if hit_tp else "STOP_LOSS"
                trade.simulated_exit_price = round(exit_price, 4)
                trade.simulated_pnl = round(pnl, 2)
                trade.simulated_pnl_pct = round(pnl_pct, 2)
                trade.closed_at = now

                await self._shadow_repo.update_shadow_trade(trade)
                closed_trades.append(trade)

                close_payload = {
                    "shadow_trade_id": trade.id,
                    "signal_id": trade.signal_id,
                    "bot": trade.bot.value,
                    "coin": trade.coin,
                    "exit_price": trade.simulated_exit_price,
                    "simulated_pnl": trade.simulated_pnl,
                    "simulated_pnl_pct": trade.simulated_pnl_pct,
                    "exit_reason": trade.exit_reason,
                    "closed_at": now.isoformat(),
                }

                await self._bus.publish(EventType.SHADOW_TRADE_CLOSED, close_payload)
                await self._event_log.append(
                    event_type=EventType.SHADOW_TRADE_CLOSED.value,
                    source_service="shadow_engine",
                    entity_id=trade.id,
                    payload=close_payload,
                )
                logger.info("Shadow trade CLOSED", extra={"coin": trade.coin, "pnl": trade.simulated_pnl, "reason": trade.exit_reason})

        return closed_trades
