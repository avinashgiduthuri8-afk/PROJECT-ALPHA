"""
V2 Trading Execution Service (Production Fleet & CoinDCX Sub-Account Edition).

Translates approved trade candidates into concrete positions, routes to shadow simulation
or active execution via isolated CoinDCX Sub-Account clients, and manages position exit checks.
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
from v2.trading.subaccount_manager import CoinDCXSubAccountManager
from .adapters import BaseBotAdapter, StrategyAdapterFactory

logger = get_logger("v2.services.trading_service")


class TradingService:
    """Manages order construction, sub-account execution routing, and position exit lifecycle."""

    def __init__(
        self,
        bus: EventBus,
        position_repo: PositionRepository,
        trade_repo: TradeRepository,
        event_log_repo: EventLogRepository,
        config: V2Config,
        shadow_engine: Optional[object] = None,
        subaccount_manager: Optional[CoinDCXSubAccountManager] = None,
    ) -> None:
        self._bus = bus
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._event_log = event_log_repo
        self._config = config
        self._shadow_engine = shadow_engine
        self._subaccount_manager = subaccount_manager or CoinDCXSubAccountManager()

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
        logger.info(
            "TradingService started with CoinDCX Sub-Account Multi-Client router",
            extra={"shadow_mode": self._config.v2_shadow_mode, "trading_enabled": self._config.v2_trading_enabled},
        )

    async def stop(self) -> None:
        self._started = False
        self._bus.unsubscribe(EventType.TRADE_APPROVED, self.on_trade_approved)
        logger.info("TradingService stopped")

    # ── Order Execution ───────────────────────────────────────────────────────

    async def on_trade_approved(self, event_type: EventType, payload: dict) -> None:
        """Handle TRADE_APPROVED event by routing to shadow engine or isolated sub-account client."""
        try:
            signal_id = payload.get("signal_id") or str(uuid.uuid4())
            coin = payload.get("coin", "UNKNOWN")
            pair = payload.get("pair") or f"{coin}/INR"
            bot_str = payload.get("bot", "STE")
            approved_amount = float(payload.get("approved_amount", 500.0))
            ai_adjustments = payload.get("ai_adjustments") or {}
            price = float(payload.get("price") or payload.get("current_price") or 100.0)

            try:
                bot = BotName(bot_str)
            except ValueError:
                bot = BotName.STE

            adapter = StrategyAdapterFactory.get_adapter(bot)
            order_data = adapter.calculate_order(
                coin=coin,
                pair=pair,
                approved_amount=approved_amount,
                current_price=price,
                ai_adjustments=ai_adjustments,
            )

            # Strict Single-Position Asset Deduplication Check (Fleet-wide single coin lock)
            if self._config.enforce_single_coin_lock:
                open_positions = await self._position_repo.get_open()
                coin_clean = coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
                for op in open_positions:
                    op_clean = op.coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
                    if op_clean == coin_clean or coin_clean in op.pair.upper():
                        logger.warning(
                            "Order skipped by Single-Coin Lock: %s already has active position in %s",
                            coin_clean, op.bot.value,
                        )
                        return

            deployment_mode = getattr(self._config, "v2_deployment_mode", "SHADOW").upper()
            is_live = (deployment_mode == "LIVE_MICROCASH" or self._config.v2_trading_enabled)

            # 1. Shadow Simulation Routing
            if not is_live:
                if self._shadow_engine is not None:
                    try:
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
                    except Exception as e:
                        logger.debug("Shadow engine record warning: %s", e)

                # Persist paper position for asset lock & lifecycle reconciliation
                now = datetime.now(timezone.utc)
                pos = Position(
                    id=str(uuid.uuid4()),
                    bot=bot,
                    coin=coin,
                    pair=pair,
                    qty=order_data["qty"],
                    entry_price=order_data["entry_price"],
                    entry_time=now,
                    mode=BotMode.PAPER,
                    status=PositionStatus.OPEN,
                    current_price=order_data["entry_price"],
                    unrealised_pnl=0.0,
                    stop_loss=order_data["stop_loss"],
                    take_profit=order_data["take_profit"],
                    signal_id=signal_id,
                )
                await self._position_repo.insert(pos)
                self._total_executed += 1

                # Update subaccount manager headroom
                sub_client = self._subaccount_manager.get_client(bot)
                sub_client._shared_state["deployed_capital_inr"] += order_data["amount"]

                pos_payload = {
                    "position_id": pos.id,
                    "subaccount_id": sub_client.subaccount_id,
                    "bot": bot.value,
                    "coin": coin,
                    "pair": pair,
                    "qty": pos.qty,
                    "entry_price": pos.entry_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "signal_id": signal_id,
                    "mode": "PAPER",
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
                logger.info(
                    "[SHADOW] Paper trade EXECUTED and Position OPENED for %s (Qty: %s @ INR %.2f)",
                    coin, pos.qty, pos.entry_price,
                )
                return

            # 2. Live Microcash Execution with HMAC signing and precision validation
            if is_live:
                sub_client = self._subaccount_manager.get_client(bot)
                order_result = sub_client.place_order(
                    pair=pair,
                    side="BUY",
                    price=order_data["entry_price"],
                    qty=order_data["qty"],
                )

                if not order_result.get("success"):
                    logger.warning("Live sub-account order failed: %s", order_result.get("message"))
                    return

                now = datetime.now(timezone.utc)
                pos = Position(
                    id=str(uuid.uuid4()),
                    bot=bot,
                    coin=coin,
                    pair=pair,
                    qty=order_data["qty"],
                    entry_price=order_data["entry_price"],
                    entry_time=now,
                    mode=BotMode.LIVE,
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
                    "subaccount_id": sub_client.subaccount_id,
                    "bot": bot.value,
                    "coin": coin,
                    "pair": pair,
                    "qty": pos.qty,
                    "entry_price": pos.entry_price,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "signal_id": signal_id,
                    "mode": "LIVE",
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
                logger.info(
                    "[%s] Live trade EXECUTED and Position OPENED for %s (Qty: %s @ INR %.2f)",
                    sub_client.subaccount_id, coin, pos.qty, pos.entry_price,
                )

        except Exception as exc:
            logger.error("Error executing trade in TradingService", exc_info=True)

    # ── Position Exit Monitoring ──────────────────────────────────────────────

    async def check_open_position_exits(self, current_prices: dict[str, float]) -> list[Trade]:
        """Check all live/shadow open positions against current market prices for SL/TP exit triggers with 1.572% statutory friction."""
        from v2.backtest.friction import CoinDCXFrictionModel
        friction_model = CoinDCXFrictionModel()
        closed_trades: list[Trade] = []
        open_positions = await self._position_repo.get_open()

        for pos in open_positions:
            price = current_prices.get(pos.coin) or current_prices.get(pos.pair)
            if price is None or price <= 0.0:
                continue

            adapter = StrategyAdapterFactory.get_adapter(pos.bot)
            exit_trigger = adapter.check_exit(
                entry_price=pos.entry_price,
                current_price=price,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
            )

            if exit_trigger is not None:
                exit_reason, exit_price = exit_trigger

                # Apply exact 1.572% round-trip statutory friction model
                pnl_data = friction_model.calculate_trade_net_pnl(
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    position_size_qty=pos.qty,
                )
                net_pnl = pnl_data["net_pnl"]
                net_pnl_pct = pnl_data["net_pnl_pct"]
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
                    pnl=round(net_pnl, 2),
                    pnl_pct=round(net_pnl_pct, 2),
                    entry_time=pos.entry_time,
                    exit_time=now,
                    exit_reason=exit_reason,
                    mode=pos.mode,
                    signal_id=pos.signal_id,
                )

                # 1. If live position, dispatch sell order
                if pos.mode == BotMode.LIVE and self._config.v2_trading_enabled:
                    try:
                        sub_client = self._subaccount_manager.get_client(pos.bot)
                        sub_client.place_order(
                            pair=pos.pair,
                            side="SELL",
                            price=exit_price,
                            qty=pos.qty,
                        )
                    except Exception as e:
                        logger.warning("Error dispatching exit order to CoinDCX: %s", e)

                # 2. Insert trade history
                await self._trade_repo.insert(trade)

                # 3. Close position record (releases single-coin lock)
                await self._position_repo.close(
                    position_id=pos.id,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                )

                # 4. Inform sub-account client of balance restoration
                try:
                    sub_client = self._subaccount_manager.get_client(pos.bot)
                    sub_client.close_position_fill(
                        notional_returned=pos.entry_price * pos.qty,
                        realized_pnl=net_pnl,
                    )
                except Exception:
                    pass

                closed_trades.append(trade)

                trade_payload = {
                    "trade_id": trade.id,
                    "position_id": pos.id,
                    "bot": pos.bot.value,
                    "coin": pos.coin,
                    "pair": pos.pair,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "friction_cost": pnl_data.get("total_friction_cost", 0.0),
                    "exit_reason": exit_reason.value,
                    "exit_price": exit_price,
                    "mode": pos.mode.value if hasattr(pos.mode, "value") else str(pos.mode),
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
                logger.info(
                    "Position CLOSED (%s): %s %s PnL=INR %.2f (%.2f%%) [Friction=INR %.2f, Reason=%s]",
                    trade_payload["mode"], pos.bot.value, pos.coin, trade.pnl, trade.pnl_pct, pnl_data.get("total_friction_cost", 0.0), exit_reason.value,
                )

        return closed_trades

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "shadow_mode": self._config.v2_shadow_mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "total_executed": self._total_executed,
            "subaccounts": self._subaccount_manager.get_all_subaccount_telemetry(),
        }
