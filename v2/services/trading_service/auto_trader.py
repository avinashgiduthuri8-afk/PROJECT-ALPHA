"""
V2 Auto Trade Dispatcher & Strategy Router.

Subscribes to SIGNAL_GENERATED events on the EventBus, maps signals to isolated
production bot strategies (STE, HDA, VCP, BBS), evaluates sub-account capital limits,
enforces order book precision & min ₹100 notional rules, and dispatches HMAC-signed orders.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Dict, Optional, Set

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.logging import get_logger
from v2.core.types import BotName, Signal
from v2.trading.precision_rules import (
    extract_base_coin,
    normalize_price,
    normalize_qty,
    round_price,
    round_qty,
    round_qty_up,
    validate_order_notional,
    validate_trade_parameters,
)
from v2.trading.subaccount_manager import CoinDCXSubAccountClient, CoinDCXSubAccountManager

logger = get_logger("v2.services.trading_service.auto_trader")


class AutoTradeRouter:
    """
    Auto Trade Dispatcher & Strategy Router.
    Enforces signal idempotency, cross-strategy asset locking, precision rules, and HMAC-signed sub-account order dispatch.
    """

    def __init__(
        self,
        bus: EventBus,
        subaccount_manager: Optional[CoinDCXSubAccountManager] = None,
        dry_run: bool = False,
        position_repo: Optional[Any] = None,
    ) -> None:
        self._bus = bus
        self._subaccount_manager = subaccount_manager or CoinDCXSubAccountManager()
        self.dry_run = dry_run
        self._position_repo = position_repo
        self._processed_idempotency_keys: Set[str] = set()
        self._lock = threading.RLock()

    def map_signal_to_bot(self, signal_data: Dict[str, Any]) -> BotName:
        """
        Map incoming signal payload/dataclass to isolated production strategy (STE, HDA, VCP, BBS).
        """
        bot_hint = signal_data.get("bot") or signal_data.get("target_bot") or signal_data.get("source_bot")
        if bot_hint:
            bot_str = str(bot_hint).upper()
            for b in BotName:
                if b.value == bot_str:
                    return b

        opp = str(signal_data.get("opportunity_type", "")).lower()
        if "momentum" in opp or "continuation" in opp:
            return BotName.STE
        elif "breakout" in opp or "recovery" in opp:
            return BotName.HDA
        elif "accumulation" in opp or "vcp" in opp:
            return BotName.VCP
        elif "squeeze" in opp or "bollinger" in opp or "bbs" in opp:
            return BotName.BBS

        # Default allocation strategy
        return BotName.STE

    def generate_idempotency_key(self, coin: str, signal_id: str) -> str:
        return f"{coin.upper()}::{signal_id}"

    def is_signal_processed(self, idempotency_key: str) -> bool:
        with self._lock:
            return idempotency_key in self._processed_idempotency_keys

    def mark_signal_processed(self, idempotency_key: str) -> None:
        with self._lock:
            self._processed_idempotency_keys.add(idempotency_key)

    async def handle_signal_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """EventBus handler callback for SIGNAL_GENERATED."""
        await self.handle_signal(payload)

    async def handle_signal(
        self,
        signal: Signal | Dict[str, Any],
        dry_run: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Main signal processing pipeline:
          1. Extract signal fields & generate idempotency key
          2. Check idempotency (reject duplicates)
          3. Map signal to target production bot (STE, HDA, VCP, BBS)
          4. Retrieve sub-account client & calculate trade parameters
          5. Enforce pre-trade precision rules (round price, round qty, min ₹100 notional)
          6. Dispatch order to CoinDCX sub-account or simulate dry-run
        """
        is_dry_run = dry_run if dry_run is not None else self.dry_run

        if isinstance(signal, Signal):
            signal_data = {
                "id": signal.id,
                "coin": signal.coin,
                "pair": signal.pair,
                "opportunity_type": signal.opportunity_type.value if hasattr(signal.opportunity_type, "value") else str(signal.opportunity_type),
                "score": signal.score,
                "target_bot": signal.raw_payload.get("target_bot") if signal.raw_payload else None,
                "price": signal.raw_payload.get("price") if signal.raw_payload else None,
                "trade_amount": signal.raw_payload.get("trade_amount", 500.0) if signal.raw_payload else 500.0,
            }
        elif isinstance(signal, dict):
            signal_data = dict(signal)
        else:
            logger.error("Invalid signal object passed to handle_signal: %s", type(signal))
            return None

        signal_id = str(signal_data.get("id") or signal_data.get("signal_id") or "UNKNOWN_SIG")
        coin = str(signal_data.get("coin") or "BTC").upper()
        pair = str(signal_data.get("pair") or f"{coin}/INR").upper().replace("_", "/")

        idempotency_key = self.generate_idempotency_key(coin, signal_id)
        if self.is_signal_processed(idempotency_key):
            logger.warning("Duplicate signal rejected by idempotency filter: %s", idempotency_key)
            return {
                "success": False,
                "error": "DUPLICATE_SIGNAL",
                "idempotency_key": idempotency_key,
                "message": f"Signal {idempotency_key} has already been processed.",
            }

        target_bot = self.map_signal_to_bot(signal_data)

        # Cross-Strategy Single Coin Lock: if coin is already open in any strategy bot, reject
        if self._position_repo is not None:
            try:
                candidate_base = extract_base_coin(coin) or extract_base_coin(pair)
                get_open_coro = self._position_repo.get_open()
                if inspect.isawaitable(get_open_coro):
                    open_positions = await get_open_coro
                else:
                    open_positions = get_open_coro
                for op in open_positions:
                    op_base = extract_base_coin(getattr(op, "coin", "")) or extract_base_coin(getattr(op, "pair", ""))
                    if candidate_base and op_base and candidate_base == op_base:
                        op_bot = getattr(op, "bot", "BOT")
                        op_bot_name = op_bot.value if hasattr(op_bot, "value") else str(op_bot)
                        target_bot_name = target_bot.value if hasattr(target_bot, "value") else str(target_bot)
                        logger.warning(
                            "AutoTradeRouter rejected signal for %s: active position already exists in strategy %s (target: %s)",
                            candidate_base, op_bot_name, target_bot_name,
                        )
                        return {
                            "success": False,
                            "error": "OPPORTUNITY_LOCKED_ACTIVE_PAIR",
                            "idempotency_key": idempotency_key,
                            "message": f"Asset {candidate_base} already has an active open position in strategy {op_bot_name}. Cross-strategy lock prevents opening in {target_bot_name}.",
                        }
            except Exception as exc:
                logger.debug("AutoTradeRouter active position cross-strategy check error: %s", exc)

        client = self._subaccount_manager.get_client(target_bot)

        raw_price = signal_data.get("price") or signal_data.get("current_price")
        try:
            price = normalize_price(raw_price)
        except ValueError as exc:
            logger.warning(
                "AutoTradeRouter rejected signal for %s: invalid price '%s': %s",
                pair, raw_price, exc,
            )
            return {
                "success": False,
                "error": "INVALID_PRICE",
                "idempotency_key": idempotency_key,
                "message": f"Signal has invalid price: {exc}",
            }

        trade_amount_inr = float(signal_data.get("trade_amount") or signal_data.get("amount") or client.config.default_trade_amount_inr)
        
        is_usdt_pair = pair.upper().endswith("/USDT") or pair.upper().endswith("USDT")
        usdt_inr_rate = float(signal_data.get("usdt_inr_rate") or 91.50)

        if is_usdt_pair:
            target_usdt = trade_amount_inr / usdt_inr_rate if usdt_inr_rate > 0 else (trade_amount_inr / 91.50)
            qty = target_usdt / price if price > 0 else 0.0
        else:
            qty = trade_amount_inr / price if price > 0 else 0.0

        # Pre-trade precision validation
        rounded_price = round_price(pair, price)
        rounded_qty = round_qty(pair, qty)
        notional_value = rounded_price * rounded_qty
        notional_inr = (notional_value * usdt_inr_rate) if is_usdt_pair else notional_value

        # Hard ₹200 minimum trading value invariant:
        # If calculated notional is below ₹200.00, round quantity UP to the next valid exchange lot step
        if notional_inr < 200.0:
            rounded_qty = round_qty_up(pair, qty)
            notional_value = rounded_price * rounded_qty
            notional_inr = (notional_value * usdt_inr_rate) if is_usdt_pair else notional_value

        if not validate_order_notional(pair, rounded_price, rounded_qty, min_notional=200.0, usdt_inr_rate=usdt_inr_rate) or notional_inr < 200.0:
            logger.warning(
                "Order rejected by precision gate: notional value INR %.2f < min ₹200.00 for pair %s",
                notional_inr, pair,
            )
            return {
                "success": False,
                "error": "ORDER_NOTIONAL_BELOW_MINIMUM",
                "notional_value": notional_inr,
                "message": f"Notional value INR {notional_inr:.2f} is below minimum INR 200.00",
            }

        # Mark signal as processed once validated
        self.mark_signal_processed(idempotency_key)

        if is_dry_run:
            logger.info(
                "[DRY-RUN] AutoTradeRouter mapped signal %s to bot %s for pair %s @ %.4f (Qty: %s, Notional INR: %.2f)",
                signal_id, target_bot.value, pair, rounded_price, rounded_qty, notional_inr,
            )
            return {
                "success": True,
                "dry_run": True,
                "bot": target_bot.value,
                "subaccount_id": client.subaccount_id,
                "pair": pair,
                "price": rounded_price,
                "qty": rounded_qty,
                "notional": notional_value,
                "idempotency_key": idempotency_key,
            }

        order_result = client.place_order(
            pair=pair,
            side="BUY",
            price=rounded_price,
            qty=rounded_qty,
            client_order_id=f"ORD_{idempotency_key.replace('::', '_')}",
        )
        if inspect.isawaitable(order_result):
            order_result = await order_result

        if order_result.get("success"):
            order_record = order_result.get("order", {})
            order_record["idempotency_key"] = idempotency_key
            logger.info("Order successfully dispatched via AutoTradeRouter for signal %s", signal_id)
            return {
                "success": True,
                "bot": target_bot.value,
                "subaccount_id": client.subaccount_id,
                "order": order_record,
                "idempotency_key": idempotency_key,
            }
        else:
            return order_result
