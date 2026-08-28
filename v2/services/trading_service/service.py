"""
V2 Trading Execution Service.

Translates approved trade candidates into concrete positions, routes to shadow simulation
or active execution, and manages position exit checks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.types import (
    BotMode,
    BotName,
    ExitReason,
    Position,
    PositionStatus,
    Trade,
)
from v2.core.logging import get_logger
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository

from .adapters import BaseBotAdapter, MTBAdapter, PMBAdapter, VGXAdapter

logger = get_logger("v2.services.trading_service")


class TradingService:
    """Manages order construction, execution gating, and position exit lifecycle."""

    def __init__(
        self,
        bus: EventBus,
        position_repo: PositionRepository,
        trade_repo: TradeRepository,
        event_log_repo: EventLogRepository,
        config: V2Config,
        shadow_engine: Optional[object] = None,
    ) -> None:
        self._bus = bus
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._event_log = event_log_repo
        self._config = config
        self._shadow_engine = shadow_engine

        self._adapters: dict[BotName, BaseBotAdapter] = {
            BotName.MTB: MTBAdapter(),
            BotName.PMB: PMBAdapter(),
            BotName.VGX: VGXAdapter(),
        }

        self._total_executed = 0
        self._started = False

    def set_shadow_engine(self, shadow_engine: object) -> None:
        self._shadow_engine = shadow_engine

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._bus.subscribe(EventType.TRADE_APPROVED, self.on_trade_approved)
        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "trading_service"})
        logger.info("TradingService started", extra={"shadow_mode": self._config.v2_shadow_mode, "trading_enabled": self._config.v2_trading_enabled})

    async def stop(self) -> None:
        self._started = False
        self._bus.unsubscribe(EventType.TRADE_APPROVED, self.on_trade_approved)
        logger.info("TradingService stopped")

    # ── Order Execution ───────────────────────────────────────────────────────

    async def on_trade_approved(self, event_type: EventType, payload: dict) -> None:
        """Handle TRADE_APPROVED event by routing to shadow engine or execution adapter."""
        try:
            signal_id = payload.get("signal_id") or str(uuid.uuid4())
            coin = payload.get("coin", "UNKNOWN")
            pair = payload.get("pair") or f"B-{coin}_USDT"
            bot_str = payload.get("bot", "MTB")
            approved_amount = float(payload.get("approved_amount", 100.0))
            ai_adjustments = payload.get("ai_adjustments") or {}
            price = float(payload.get("price") or payload.get("current_price") or 100.0)

            try:
                bot = BotName(bot_str)
            except ValueError:
                bot = BotName.MTB

            adapter = self._adapters.get(bot, self._adapters[BotName.MTB])
            order_data = adapter.calculate_order(
                coin=coin,
                pair=pair,
                approved_amount=approved_amount,
                current_price=price,
                ai_adjustments=ai_adjustments,
            )

            # 1. Shadow Simulation Routing
            if self._config.v2_shadow_mode and self._shadow_engine is not None:
                await self._shadow_engine.record_approved_trade(
                    signal_id=signal_id,
                    bot=bot,
                    coin=coin,
                    pair=pair,
                    entry_price=order_data["entry_price"],
                    qty=order_data["qty"],
                    amount=order_data["amount"],
                    stop_loss=order_data["stop_loss"],
                    take_profit=order_data["take_profit"],
                    ai_recommendation=payload.get("recommendation", "APPROVE"),
                    raw_adjustments=ai_adjustments,
                )

            # 2. Active Execution (if enabled)
            if self._config.v2_trading_enabled:
                now = datetime.now(timezone.utc)
                pos = Position(
                    id=str(uuid.uuid4()),
                    bot=bot,
                    coin=coin,
                    pair=pair,
                    qty=order_data["qty"],
                    entry_price=order_data["entry_price"],
                    entry_time=now,
                    mode=BotMode.PAPER,  # Paper mode by default for safety
                    status=PositionStatus.OPEN,
                    current_price=order_data["entry_price"],
                    unrealised_pnl=0.0,
                    stop_loss=order_data["stop_loss"],
                    take_profit=order_data["take_profit"],
                    signal_id=signal_id,
                )

                await self._position_repo.insert(pos)
                self._total_executed += 1

                pos_payload = {
                    "position_id": pos.id,
                    "bot": bot.value,
                    "coin": coin,
                    "pair": pair,
                    "qty": pos.qty,
                    "entry_price": pos.entry_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "signal_id": signal_id,
                    "opened_at": now.isoformat(),
                }

                await self._bus.publish(EventType.TRADE_EXECUTED, pos_payload)
                await self._bus.publish(EventType.POSITION_OPENED, pos_payload)
                await self._event_log.append(
                    event_type=EventType.TRADE_EXECUTED.value,
                    source_service="trading_service",
                    entity_id=pos.id,
                    payload=pos_payload,
                )
                logger.info("Trade EXECUTED and Position OPENED", extra={"coin": coin, "bot": bot.value, "qty": pos.qty})

        except Exception as exc:
            logger.error("Error executing trade in TradingService", exc_info=True)

    # ── Position Exit Monitoring ──────────────────────────────────────────────

    async def check_open_position_exits(self, current_prices: dict[str, float]) -> list[Trade]:
        """Check all live open positions against current market prices for SL/TP exit triggers."""
        closed_trades: list[Trade] = []
        open_positions = await self._position_repo.get_open()

        for pos in open_positions:
            price = current_prices.get(pos.coin) or current_prices.get(pos.pair)
            if price is None or price <= 0.0:
                continue

            adapter = self._adapters.get(pos.bot, self._adapters[BotName.MTB])
            exit_trigger = adapter.check_exit(
                entry_price=pos.entry_price,
                current_price=price,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
            )

            if exit_trigger is not None:
                exit_reason, exit_price = exit_trigger
                pnl = (exit_price - pos.entry_price) * pos.qty
                pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100.0
                now = datetime.now(timezone.utc)

                trade = Trade(
                    id=str(uuid.uuid4()),
                    position_id=pos.id,
                    bot=pos.bot,
                    coin=pos.coin,
                    pair=pos.pair,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    qty=pos.qty,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    entry_time=pos.entry_time,
                    exit_time=now,
                    exit_reason=exit_reason,
                    mode=pos.mode,
                    signal_id=pos.signal_id,
                )

                # 1. Insert trade history
                await self._trade_repo.insert(trade)

                # 2. Close position record
                await self._position_repo.close_position(
                    position_id=pos.id,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                )

                closed_trades.append(trade)

                trade_payload = {
                    "trade_id": trade.id,
                    "position_id": pos.id,
                    "bot": pos.bot.value,
                    "coin": pos.coin,
                    "pair": pos.pair,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "exit_reason": exit_reason.value,
                    "exit_price": exit_price,
                    "closed_at": now.isoformat(),
                }

                await self._bus.publish(EventType.TRADE_CLOSED, trade_payload)
                await self._bus.publish(EventType.POSITION_CLOSED, trade_payload)
                await self._event_log.append(
                    event_type=EventType.TRADE_CLOSED.value,
                    source_service="trading_service",
                    entity_id=trade.id,
                    payload=trade_payload,
                )
                logger.info("Position CLOSED", extra={"coin": pos.coin, "bot": pos.bot.value, "pnl": trade.pnl, "reason": exit_reason.value})

        return closed_trades

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "shadow_mode": self._config.v2_shadow_mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "total_executed": self._total_executed,
        }
