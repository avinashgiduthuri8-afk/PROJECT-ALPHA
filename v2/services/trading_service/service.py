"""
V2 Trading Execution Service (Production Fleet & CoinDCX Sub-Account Edition).

Translates approved trade candidates into concrete positions, routes to shadow simulation
or active execution via isolated CoinDCX Sub-Account clients, and manages position exit checks.
"""

from __future__ import annotations

import inspect
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
    Order,
    OrderState,
    OrderStateTransition,
    Position,
    PositionStatus,
    Trade,
)
from v2.core.logging import get_logger
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.repository.order_repo import OrderRepository
from v2.trading.order_state_machine import OrderStateMachine
from v2.trading.subaccount_manager import CoinDCXSubAccountManager
from v2.trading.precision_rules import (
    extract_base_coin,
    get_pair_spec,
    normalize_price,
    normalize_qty,
    round_price,
    round_qty,
    round_qty_up,
    validate_order_notional,
    validate_trade_parameters,
)
from .adapters import BaseBotAdapter, StrategyAdapterFactory
from .auto_trader import AutoTradeRouter
from .position_manager import PositionManager
from .reconciliation import ReconciliationService
from .recovery import RestartRecoveryService

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
        order_repo: Optional[OrderRepository] = None,
    ) -> None:
        self._bus = bus
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._event_log = event_log_repo
        self._config = config
        self._shadow_engine = shadow_engine
        self._subaccount_manager = subaccount_manager or CoinDCXSubAccountManager()
        self._order_repo = order_repo

        # Phase 2 Execution Components
        self.auto_trader = AutoTradeRouter(
            bus=self._bus,
            subaccount_manager=self._subaccount_manager,
            dry_run=not self._config.v2_trading_enabled,
            position_repo=self._position_repo,
        )
        self.position_manager = PositionManager(
            position_repo=self._position_repo,
            trade_repo=self._trade_repo,
            bus=self._bus,
        )
        self.recovery_service = RestartRecoveryService(
            position_repo=self._position_repo,
            subaccount_manager=self._subaccount_manager,
            order_repo=self._order_repo,
        )
        self.reconciliation_service = ReconciliationService(
            position_repo=self._position_repo,
            subaccount_manager=self._subaccount_manager,
        )

        self._total_executed = 0
        self._started = False
        self._pending_exits: set[str] = set()
        self._last_reconciliation_report: dict[str, Any] = {
            "timestamp": None,
            "orders_checked": 0,
            "positions_checked": 0,
            "mismatches": 0,
            "unknown_orders": 0,
            "balance_diff": 0.0,
            "status": "INITIALIZED",
        }

    @property
    def subaccount_manager(self) -> CoinDCXSubAccountManager:
        return self._subaccount_manager

    def set_shadow_engine(self, shadow_engine: object) -> None:
        self._shadow_engine = shadow_engine

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        # Rehydrate positions from SQLite on startup
        # Rehydrate positions and active live orders from SQLite on startup
        await self.recovery_service.rehydrate_state()
        await self.recovery_service.rehydrate_orders()

        # Subscribe handlers
        self._bus.subscribe(EventType.TRADE_APPROVED, self.on_trade_approved)

        # Start reconciliation worker
        await self.reconciliation_service.start()

        await self._bus.publish(EventType.SYSTEM_STARTUP, {"service": "trading_service"})
        logger.info(
            "TradingService started with AutoTradeRouter, PositionManager, Recovery & Reconciliation",
            extra={"shadow_mode": self._config.v2_shadow_mode, "trading_enabled": self._config.v2_trading_enabled},
        )

    async def stop(self) -> None:
        self._started = False
        self._bus.unsubscribe(EventType.TRADE_APPROVED, self.on_trade_approved)
        await self.reconciliation_service.stop()
        logger.info("TradingService stopped")

    # ── Order Execution ───────────────────────────────────────────────────────

    async def on_trade_approved(self, event_type: EventType, payload: dict) -> None:
        """Handle TRADE_APPROVED event by routing to shadow engine or isolated sub-account client."""
        try:
            signal_id = payload.get("signal_id") or str(uuid.uuid4())
            coin = payload.get("coin", "UNKNOWN")
            pair = payload.get("pair") or f"{coin}/INR"
            bot_str = payload.get("bot", "STE")
            approved_amount = float(payload.get("approved_amount") or self._config.order_size_inr)
            if approved_amount < 200.0:
                logger.warning(
                    "Trade approval below mandatory minimum rejected before construction: %.2f",
                    approved_amount,
                )
                return
            ai_adjustments = payload.get("ai_adjustments") or {}

            raw_price = payload.get("price") or payload.get("current_price")
            try:
                price = normalize_price(raw_price)
            except ValueError as exc:
                logger.warning(
                    "Final execution validation rejected order: pair=%s raw_price=%s reason=%s",
                    pair, raw_price, exc,
                )
                return

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

            # Mandatory defense: enforce minimum ₹200.00 position amount in all modes (Paper & Live)
            entry_px = float(order_data.get("entry_price") or price)
            if order_data.get("amount", 0.0) < 200.0 and entry_px > 0:
                order_data["qty"] = round_qty_up(pair, 200.0 / entry_px)
                order_data["amount"] = round(entry_px * order_data["qty"], 2)

            valid, err_reason = validate_trade_parameters(
                pair=pair,
                price=entry_px,
                qty=float(order_data.get("qty", 0.0) or 0.0),
                stop_loss=order_data.get("stop_loss"),
                take_profit=order_data.get("take_profit"),
                is_long=True,
                min_notional=200.0,
            )

            if not valid:
                logger.warning(
                    "Final execution validation rejected order: pair=%s raw_price=%s normalized_price=%.8f qty=%s notional=%.2f entry=%.8f TP=%s SL=%s reason=%s",
                    pair,
                    raw_price,
                    entry_px,
                    order_data.get("qty"),
                    float(order_data.get("amount", 0.0) or 0.0),
                    entry_px,
                    order_data.get("take_profit"),
                    order_data.get("stop_loss"),
                    err_reason,
                )
                return

            # Strict Single-Position Asset Deduplication Check (Fleet-wide cross-strategy single coin lock)
            if self._config.enforce_single_coin_lock:
                open_positions = await self._position_repo.get_open()
                candidate_base = extract_base_coin(coin) or extract_base_coin(pair)
                for op in open_positions:
                    op_base = extract_base_coin(op.coin) or extract_base_coin(op.pair)
                    if candidate_base and op_base and candidate_base == op_base:
                        op_bot_name = op.bot.value if hasattr(op.bot, "value") else str(op.bot)
                        logger.warning(
                            "Order skipped by Cross-Strategy Single-Coin Lock: %s already has active position in strategy %s (attempted: %s)",
                            candidate_base, op_bot_name, bot.value,
                        )
                        return

            deployment_mode = getattr(self._config, "v2_deployment_mode", "SHADOW").upper()
            is_live = (deployment_mode == "LIVE_MICROCASH" and self._config.v2_trading_enabled)

            # Construct and persist Order entity in CREATED -> SUBMITTED states
            client_order_id = f"ORD-{uuid.uuid4().hex[:12]}"
            order = Order(
                id=str(uuid.uuid4()),
                client_order_id=client_order_id,
                bot=bot,
                coin=coin,
                pair=pair,
                side="BUY",
                order_type="LIMIT",
                req_qty=order_data["qty"],
                price=order_data["entry_price"],
                state=OrderState.CREATED,
                signal_id=signal_id,
                mode=BotMode.LIVE if is_live else BotMode.PAPER,
            )

            if self._order_repo:
                await self._order_repo.insert(order)
                order, tr_sub = OrderStateMachine.transition(
                    order=order,
                    to_state=OrderState.SUBMITTED,
                    reason="Order submitted for execution",
                )
                await self._order_repo.update(order)
                await self._order_repo.record_transition(tr_sub)

            # 1. Shadow / Paper Simulation Routing
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
                    client_order_id=client_order_id,
                    filled_qty=order_data["qty"],
                )
                await self._position_repo.insert(pos)
                self._total_executed += 1

                # Update order to FILLED for paper execution
                if self._order_repo:
                    order, tr_filled = OrderStateMachine.transition(
                        order=order,
                        to_state=OrderState.FILLED,
                        filled_qty=order_data["qty"],
                        avg_price=order_data["entry_price"],
                        reason="Paper order filled immediately",
                    )
                    order.position_id = pos.id
                    await self._order_repo.update(order)
                    await self._order_repo.record_transition(tr_filled)

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
                order_result = await sub_client.place_live_order(
                    pair=pair,
                    side="BUY",
                    price=order_data["entry_price"],
                    qty=order_data["qty"],
                    client_order_id=client_order_id,
                )

                if not order_result.get("success"):
                    # Timeout / Network Ambiguity Handling: verify via client_order_id before giving up
                    if order_result.get("error") == "TIMEOUT" or order_result.get("requires_reconciliation"):
                        cl_id = order_result.get("client_order_id")
                        cl_id = order_result.get("client_order_id") or client_order_id
                        if cl_id:
                            try:
                                check_res = await sub_client.get_order_by_client_id(cl_id)
                                if check_res.get("success") and check_res.get("exchange_order_id"):
                                    order_result = check_res
                            except Exception as e:
                                logger.warning("Failed to verify ambiguous order %s: %s", cl_id, e)

                    if not order_result.get("success"):
                        logger.warning(
                            "Live CoinDCX BUY order placement failed for %s (%s): %s",
                            coin, bot.value, order_result.get("message") or order_result.get("error"),
                        )
                        if self._order_repo:
                            err_st = OrderState.UNKNOWN if order_result.get("error") == "TIMEOUT" else OrderState.REJECTED
                            order, tr_err = OrderStateMachine.transition(
                                order=order,
                                to_state=err_st,
                                reason=str(order_result.get("message") or order_result.get("error") or "Order placement failed"),
                            )
                            await self._order_repo.update(order)
                            await self._order_repo.record_transition(tr_err)
                        return

                # Fill Confirmation Gate: Only create local OPEN position if confirmed FILLED on exchange
                exchange_order_id = order_result.get("exchange_order_id")
                order_status = str(order_result.get("status", "OPEN")).upper()
                is_filled = order_result.get("is_filled", False) or (order_status == "FILLED")
                actual_filled_qty = float(order_result.get("filled_qty") or order_result.get("qty") or 0.0)

                if self._order_repo:
                    succ_st = OrderState.FILLED if is_filled else (OrderState.PARTIALLY_FILLED if actual_filled_qty > 0 else OrderState.OPEN)
                    order, tr_succ = OrderStateMachine.transition(
                        order=order,
                        to_state=succ_st,
                        filled_qty=actual_filled_qty,
                        avg_price=float(order_result.get("price", order_data["entry_price"])),
                        exchange_order_id=exchange_order_id,
                        reason=f"Exchange order response: {order_status}",
                    )
                    await self._order_repo.update(order)
                    await self._order_repo.record_transition(tr_succ)

                if not is_filled or actual_filled_qty <= 0.0 or not exchange_order_id:
                    logger.warning(
                        "Live order submitted (Exchange ID: %s) but not confirmed FILLED (Status: %s, Filled Qty: %s). Position NOT opened.",
                        exchange_order_id, order_status, actual_filled_qty,
                    )
                    return

                now = datetime.now(timezone.utc)
                fill_price = float(order_result.get("price", order_data["entry_price"]))
                fill_qty = actual_filled_qty

                pos = Position(
                    id=str(uuid.uuid4()),
                    bot=bot,
                    coin=coin,
                    pair=pair,
                    qty=fill_qty,
                    entry_price=fill_price,
                    entry_time=now,
                    mode=BotMode.LIVE,
                    status=PositionStatus.OPEN,
                    current_price=fill_price,
                    unrealised_pnl=0.0,
                    stop_loss=order_data["stop_loss"],
                    take_profit=order_data["take_profit"],
                    signal_id=signal_id,
                    exchange_order_id=exchange_order_id,
                    client_order_id=order_result.get("client_order_id"),
                    filled_qty=fill_qty,
                )

                await self._position_repo.insert(pos)
                self._total_executed += 1

                pos_payload = {
                    "position_id": pos.id,
                    "subaccount_id": sub_client.subaccount_id,
                    "exchange_order_id": exchange_order_id,
                    "client_order_id": pos.client_order_id,
                    "bot": bot.value,
                    "coin": coin,
                    "pair": pair,
                    "qty": pos.qty,
                    "filled_qty": pos.filled_qty,
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
                    "[%s] Confirmed Live CoinDCX Trade EXECUTED (Exchange ID: %s) and Position OPENED for %s (Qty: %s @ INR %.2f)",
                    sub_client.subaccount_id, exchange_order_id, coin, pos.qty, pos.entry_price,
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
            # Prevent duplicate exit submissions while an exit order is pending/in-flight
            if pos.id in self._pending_exits:
                continue

            clean_coin = extract_base_coin(pos.coin) or extract_base_coin(pos.pair)
            pair_upper = pos.pair.upper()
            is_usdt = pair_upper.endswith("/USDT") or pair_upper.endswith("USDT")

            raw_px = None
            if is_usdt:
                raw_px = (
                    current_prices.get(pos.pair)
                    or current_prices.get(f"{clean_coin}/USDT")
                    or current_prices.get(f"{clean_coin}USDT")
                    or current_prices.get(f"B-{clean_coin}_USDT")
                )
            else:
                raw_px = (
                    current_prices.get(pos.pair)
                    or current_prices.get(f"{clean_coin}/INR")
                    or current_prices.get(f"{clean_coin}INR")
                    or current_prices.get(f"B-{clean_coin}_INR")
                    or current_prices.get(clean_coin)
                    or current_prices.get(pos.coin)
                )

            if raw_px is None:
                logger.debug(
                    "No fresh ticker price matching quote currency for open position %s (%s, pair: %s). Preserving last mark.",
                    pos.id, pos.coin, pos.pair,
                )
                continue

            try:
                price = normalize_price(raw_px)
            except ValueError as e:
                logger.warning("Corrupted current market price '%s' for position %s (%s): %s", raw_px, pos.id, pos.coin, e)
                continue

            # Price magnitude sanity check against entry price (e.g. Reject 100x jumps from malformed ticker data)
            if pos.entry_price > 0:
                ratio = price / pos.entry_price
                if ratio > 10.0 or ratio < 0.1:
                    logger.error(
                        "Suspicious price jump detected for %s (entry: %.8f, market: %.8f, ratio: %.2fx). Rejecting exit check to protect P&L.",
                        pos.pair, pos.entry_price, price, ratio,
                    )
                    continue

            # 1. Update mark price, peak, trailing stop, and unrealised PnL in SQLite
            await self.position_manager.update_mark_price(pos, price)

            # 2. Evaluate exit triggers: strategy adapter TP/SL or dynamic trailing stop
            adapter = StrategyAdapterFactory.get_adapter(pos.bot)
            exit_trigger = adapter.check_exit(
                entry_price=pos.entry_price,
                current_price=price,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
            )
            if exit_trigger is None:
                trailing_stop = self.position_manager._trailing_stops.get(pos.id)
                if trailing_stop is not None and price <= trailing_stop:
                    exit_trigger = (ExitReason.STOP_LOSS, price)

            if exit_trigger is not None:
                exit_reason, exit_price = exit_trigger
                exchange_sell_order_id = None
                sell_filled_qty = pos.qty
                is_partial_sell = False

                self._pending_exits.add(pos.id)

                # 1. If live position, dispatch real CoinDCX sell order via place_live_order
                deployment_mode = getattr(self._config, "v2_deployment_mode", "").upper()
                if pos.mode == BotMode.LIVE and self._config.v2_trading_enabled and deployment_mode == "LIVE_MICROCASH":
                    sub_client = self._subaccount_manager.get_client(pos.bot)
                    try:
                        sell_result = await sub_client.place_live_order(
                            pair=pos.pair,
                            side="SELL",
                            price=exit_price,
                            qty=pos.qty,
                        )
                    except Exception as e:
                        logger.error("Network error dispatching live SELL order to CoinDCX for %s: %s", pos.coin, e)
                        self._pending_exits.discard(pos.id)
                        continue  # DO NOT close position if order failed

                    # Timeout / Network Ambiguity Handling
                    if not sell_result.get("success"):
                        if sell_result.get("error") == "TIMEOUT" or sell_result.get("requires_reconciliation"):
                            cl_id = sell_result.get("client_order_id")
                            if cl_id:
                                try:
                                    check_res = await sub_client.get_order_by_client_id(cl_id)
                                    if check_res.get("success") and check_res.get("exchange_order_id"):
                                        sell_result = check_res
                                except Exception as err:
                                    logger.warning("Failed to verify ambiguous SELL order %s: %s", cl_id, err)

                    if not sell_result.get("success"):
                        logger.warning(
                            "Live SELL order failed on CoinDCX for %s (Reason: %s, Details: %s). Position remains OPEN.",
                            pos.coin, sell_result.get("error"), sell_result.get("message") or sell_result.get("details"),
                        )
                        self._pending_exits.discard(pos.id)
                        continue  # DO NOT close position on exchange rejection / failure

                    exchange_sell_order_id = sell_result.get("exchange_order_id")
                    sell_status = str(sell_result.get("status", "OPEN")).upper()
                    is_sell_filled = sell_result.get("is_filled", False) or (sell_status == "FILLED")
                    actual_sell_qty = float(sell_result.get("filled_qty") or (pos.qty if is_sell_filled else 0.0))

                    is_partial_sell = (sell_status == "PARTIALLY_FILLED" or (0.0 < actual_sell_qty < pos.qty))

                    if actual_sell_qty <= 0.0 or (not is_sell_filled and not is_partial_sell):
                        logger.warning(
                            "Live SELL order submitted (Exchange ID: %s) but not yet FILLED (Status: %s, Filled: %s). Position remains OPEN.",
                            exchange_sell_order_id, sell_status, actual_sell_qty,
                        )
                        # Keep in pending exits to avoid duplicate submissions while pending on exchange
                        continue

                    sell_filled_qty = actual_sell_qty

                # Apply exact 1.572% round-trip statutory friction model on filled quantity
                pnl_data = friction_model.calculate_trade_net_pnl(
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    position_size_qty=sell_filled_qty,
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
                    qty=sell_filled_qty,
                    pnl=round(net_pnl, 2),
                    pnl_pct=round(net_pnl_pct, 2),
                    entry_time=pos.entry_time,
                    exit_time=now,
                    exit_reason=exit_reason,
                    mode=pos.mode,
                    signal_id=pos.signal_id,
                    exchange_order_id=exchange_sell_order_id or pos.exchange_order_id,
                    client_order_id=pos.client_order_id,
                )

                # Insert trade history
                await self._trade_repo.insert(trade)

                # Handle Partial vs Full Fill
                if is_partial_sell:
                    remaining_qty = round(pos.qty - sell_filled_qty, 8)
                    logger.info(
                        "Partial SELL filled on exchange for %s: Filled %.6f / Total %.6f (Remaining: %.6f). Position remains OPEN.",
                        pos.coin, sell_filled_qty, pos.qty, remaining_qty,
                    )
                    await self._position_repo.update_qty(pos.id, remaining_qty)
                    pos.qty = remaining_qty
                    self._pending_exits.discard(pos.id)
                else:
                    # Full exit: close position record (releases single-coin lock)
                    await self._position_repo.close(
                        position_id=pos.id,
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                    )
                    self.position_manager._peak_prices.pop(pos.id, None)
                    self.position_manager._trailing_stops.pop(pos.id, None)
                    self._pending_exits.discard(pos.id)

                    # Inform sub-account client of balance restoration
                    try:
                        sub_client = self._subaccount_manager.get_client(pos.bot)
                        sub_client.close_position_fill(
                            notional_returned=pos.entry_price * sell_filled_qty,
                            realized_pnl=net_pnl,
                        )
                    except Exception:
                        pass

                closed_trades.append(trade)

                trade_payload = {
                    "trade_id": trade.id,
                    "position_id": pos.id,
                    "exchange_order_id": trade.exchange_order_id,
                    "bot": pos.bot.value,
                    "coin": pos.coin,
                    "pair": pos.pair,
                    "qty": trade.qty,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "friction_cost": pnl_data.get("total_friction_cost", 0.0),
                    "exit_reason": exit_reason.value,
                    "exit_price": exit_price,
                    "mode": pos.mode.value if hasattr(pos.mode, "value") else str(pos.mode),
                    "is_partial": is_partial_sell,
                    "closed_at": now.isoformat(),
                }

                await self._bus.publish(EventType.TRADE_CLOSED, trade_payload)
                if not is_partial_sell:
                    await self._bus.publish(EventType.POSITION_CLOSED, trade_payload)
                await self._event_log.append(
                    event_type=EventType.TRADE_CLOSED.value,
                    source_service="trading_service",
                    entity_id=trade.id,
                    payload=trade_payload,
                )
                logger.info(
                    "Position %s (%s): %s %s PnL=INR %.2f (%.2f%%) [Friction=INR %.2f, Reason=%s, Exchange ID=%s]",
                    "PARTIALLY_FILLED" if is_partial_sell else "CLOSED",
                    trade_payload["mode"], pos.bot.value, pos.coin, trade.pnl, trade.pnl_pct, pnl_data.get("total_friction_cost", 0.0), exit_reason.value, trade.exchange_order_id,
                )

        return closed_trades

    async def poll_exits(self, price_provider: Optional[dict[str, float]] = None) -> list[Trade]:
        """
        Scheduled background task: checks open positions against live market prices.
        Runs approximately every 5 seconds.
        """
        open_positions = await self._position_repo.get_open()
        if not open_positions:
            return []

        current_prices = dict(price_provider) if price_provider else {}
        if not current_prices:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get("https://api.coindcx.com/exchange/ticker")
                    if resp.status_code == 200:
                        for item in resp.json():
                            m = str(item.get("market", "")).upper()
                            try:
                                last_p = normalize_price(item.get("last_price"))
                            except ValueError:
                                continue
                            if last_p > 0:
                                current_prices[m] = last_p
                                if m.startswith("B-") and "_" in m:
                                    base, quote = m[2:].split("_", 1)
                                    current_prices[f"{base}/{quote}"] = last_p
                                    current_prices[f"{base}{quote}"] = last_p
                                elif m.endswith("INR") and len(m) > 3:
                                    coin = m[:-3]
                                    current_prices[f"{coin}/INR"] = last_p
                                    current_prices[f"{coin}INR"] = last_p
                                    current_prices[f"B-{coin}_INR"] = last_p
                                elif m.endswith("USDT") and len(m) > 4:
                                    coin = m[:-4]
                                    current_prices[f"{coin}/USDT"] = last_p
                                    current_prices[f"{coin}USDT"] = last_p
                                    current_prices[f"B-{coin}_USDT"] = last_p
            except Exception as e:
                logger.debug("Failed to fetch fresh ticker prices for exit check: %s", e)

        return await self.check_open_position_exits(current_prices)

    async def reconcile_live_orders(self) -> dict[str, Any]:
        """
        Periodically reconciles local open positions against CoinDCX exchange state.
        Detects pending, filled, rejected, cancelled, partial fills, missing exchange orders,
        orphan orders, balance mismatches, and asset position mismatches.
        Runs approximately every 60 seconds.
        """
        if self.reconciliation_service:
            report = await self.reconciliation_service.reconcile_positions()
            self._last_reconciliation_report = report
            return report
        open_positions = await self._position_repo.get_open()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "IN_SYNC",
            "is_clean": True,
            "open_positions_count": len(open_positions),
            "positions_checked": len(open_positions),
            "orders_checked": 0,
            "reconciled": 0,
            "mismatches": 0,
            "unknown_orders": 0,
            "discrepancies": [],
            "orphan_orders": [],
            "missing_orders": [],
            "partial_fills": [],
            "filled_orders": [],
            "cancelled_rejected_orders": [],
            "balance_mismatches": [],
            "position_mismatches": [],
        }

    def get_health(self) -> dict:
        return {
            "healthy": self._started,
            "shadow_mode": self._config.v2_shadow_mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "total_executed": self._total_executed,
            "pending_exits_count": len(self._pending_exits),
            "reconciliation": self._last_reconciliation_report,
            "subaccounts": self._subaccount_manager.get_all_subaccount_telemetry(),
        }

    # ── Manual Position Controls & Profit Trailing ───────────────────────────

    async def manual_close_position(
        self,
        position_id: str,
        exit_price: Optional[float] = None,
        reason: str = "MANUAL",
    ) -> dict:
        """
        Manually close an open position immediately at market price.
        Deducts statutory 1.572% friction, records trade, and restores capacity.
        """
        from v2.backtest.friction import CoinDCXFrictionModel
        friction_model = CoinDCXFrictionModel()

        pos = await self._position_repo.get_by_id(position_id)
        if not pos or pos.status != PositionStatus.OPEN:
            return {"success": False, "error": "POSITION_NOT_OPEN", "message": f"Position {position_id} is not open."}

        price = exit_price or pos.current_price or pos.entry_price
        if price <= 0.0:
            price = pos.entry_price

        # 1. If live position, dispatch real CoinDCX sell order
        deployment_mode = getattr(self._config, "v2_deployment_mode", "").upper()
        sell_filled_qty = pos.qty
        is_partial_sell = False

        if pos.mode == BotMode.LIVE and self._config.v2_trading_enabled and deployment_mode == "LIVE_MICROCASH":
            sub_client = self._subaccount_manager.get_client(pos.bot)
            sell_result = await sub_client.place_live_order(
                pair=pos.pair,
                side="SELL",
                price=price,
                qty=pos.qty,
            )
            if not sell_result.get("success"):
                return {
                    "success": False,
                    "error": "EXCHANGE_ORDER_FAILED",
                    "message": sell_result.get("message") or sell_result.get("error"),
                }

            sell_filled_qty = sell_result.get("filled_qty", pos.qty)
            if sell_result.get("status") == "PARTIALLY_FILLED" or (0.0 < sell_filled_qty < pos.qty):
                is_partial_sell = True

        # 2. Compute 1.572% statutory friction based on filled quantity
        pnl_data = friction_model.calculate_trade_net_pnl(
            entry_price=pos.entry_price,
            exit_price=price,
            position_size_qty=sell_filled_qty,
        )
        now = datetime.now(timezone.utc)
        trade = Trade(
            id=str(uuid.uuid4()),
            position_id=pos.id,
            bot=pos.bot,
            coin=pos.coin,
            pair=pos.pair,
            entry_price=pos.entry_price,
            exit_price=price,
            qty=sell_filled_qty,
            pnl=round(pnl_data["net_pnl"], 2),
            pnl_pct=round(pnl_data["net_pnl_pct"], 2),
            entry_time=pos.entry_time,
            exit_time=now,
            exit_reason=ExitReason.MANUAL,
            mode=pos.mode,
            signal_id=pos.signal_id,
        )

        await self._trade_repo.insert(trade)

        if is_partial_sell:
            remaining_qty = round(pos.qty - sell_filled_qty, 8)
            await self._position_repo.update_qty(pos.id, remaining_qty)
            self._pending_exits.discard(pos.id)
            logger.info("Manual partial SELL filled for %s: Filled %.6f / Remaining %.6f", pos.coin, sell_filled_qty, remaining_qty)
            return {
                "success": True,
                "status": "PARTIALLY_FILLED",
                "filled_qty": sell_filled_qty,
                "remaining_qty": remaining_qty,
                "net_pnl": pnl_data["net_pnl"],
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "message": f"Manual partial sell filled for {sell_filled_qty} {pos.coin}. Remaining {remaining_qty} stays OPEN.",
            }
        else:
            await self._position_repo.close(position_id=pos.id, exit_price=price, exit_reason=ExitReason.MANUAL)
            self.position_manager._peak_prices.pop(pos.id, None)
            self.position_manager._trailing_stops.pop(pos.id, None)
            self._pending_exits.discard(pos.id)

            # Restore subaccount headroom
            try:
                sub_client = self._subaccount_manager.get_client(pos.bot)
                sub_client.close_position_fill(
                    notional_returned=pos.entry_price * sell_filled_qty,
                    realized_pnl=pnl_data["net_pnl"],
                )
            except Exception:
                pass

            trade_payload = {
                "trade_id": trade.id,
                "position_id": pos.id,
                "bot": pos.bot.value,
                "coin": pos.coin,
                "pair": pos.pair,
                "qty": trade.qty,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "exit_reason": "MANUAL",
                "exit_price": price,
                "closed_at": now.isoformat(),
            }
            await self._bus.publish(EventType.POSITION_CLOSED, trade_payload)

            logger.info("Manual SELL fully confirmed for position %s (%s). Position CLOSED.", pos.id, pos.pair)
            return {
                "success": True,
                "status": "CLOSED",
                "trade_id": trade.id,
                "position_id": pos.id,
                "coin": pos.coin,
                "exit_price": price,
                "filled_qty": sell_filled_qty,
                "net_pnl": pnl_data["net_pnl"],
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "message": f"Position {pos.coin} closed manually at ₹{price:.2f} (Net PnL: ₹{trade.pnl:.2f})",
            }

    async def modify_position_targets(
        self,
        position_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
    ) -> dict:
        """
        Manually adjust Stop-Loss, Take-Profit targets, or Trailing Stop % on an active open position.
        """
        pos = await self._position_repo.get_by_id(position_id)
        if not pos or pos.status != PositionStatus.OPEN:
            return {"success": False, "error": "POSITION_NOT_OPEN", "message": f"Position {position_id} is not open."}

        new_sl = float(stop_loss) if stop_loss is not None else pos.stop_loss
        new_tp = float(take_profit) if take_profit is not None else pos.take_profit

        await self._position_repo.update_brackets(position_id, stop_loss=new_sl, take_profit=new_tp)

        trailing_stop_val = None
        if trailing_stop_pct is not None and float(trailing_stop_pct) > 0:
            trailing_stop_val = await self.position_manager.update_trailing_stop(
                position_id=position_id,
                current_price=pos.current_price or pos.entry_price,
                trailing_pct=float(trailing_stop_pct) / 100.0 if float(trailing_stop_pct) > 1.0 else float(trailing_stop_pct),
            )

        logger.info("Modified targets for position %s on %s: SL=₹%s, TP=₹%s, Trailing SL=₹%s", pos.id, pos.coin, new_sl, new_tp, trailing_stop_val)

        return {
            "success": True,
            "position_id": pos.id,
            "coin": pos.coin,
            "stop_loss": new_sl,
            "take_profit": new_tp,
            "trailing_stop": trailing_stop_val,
            "message": f"Targets for {pos.coin} updated: SL=₹{new_sl or 0:.2f}, TP=₹{new_tp or 0:.2f}",
        }

