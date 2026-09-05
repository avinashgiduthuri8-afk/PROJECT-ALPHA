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
from v2.core.types import BotName, OppType, Signal
from v2.trading.precision_rules import round_price, round_qty, validate_order_notional
from v2.trading.subaccount_manager import CoinDCXSubAccountClient, CoinDCXSubAccountManager

logger = get_logger("v2.services.trading_service.auto_trader")


class AutoTradeRouter:
    """
    Auto Trade Dispatcher & Strategy Router.
    Enforces signal idempotency, strategy mapping, precision rules, and HMAC-signed sub-account order dispatch.
    """

    def __init__(
        self,
        bus: EventBus,
        subaccount_manager: Optional[CoinDCXSubAccountManager] = None,
        dry_run: bool = False,
    ) -> None:
        self._bus = bus
        self._subaccount_manager = subaccount_manager or CoinDCXSubAccountManager()
        self.dry_run = dry_run
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
                "price": signal.raw_payload.get("price", 100.0) if signal.raw_payload else 100.0,
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
        client = self._subaccount_manager.get_client(target_bot)

        price = float(signal_data.get("price") or signal_data.get("current_price") or 100.0)
        trade_amount = float(signal_data.get("trade_amount") or signal_data.get("amount") or client.config.default_trade_amount_inr)
        qty = trade_amount / price if price > 0 else 0.0

        # Pre-trade precision validation
        rounded_price = round_price(pair, price)
        rounded_qty = round_qty(pair, qty)
        notional_value = rounded_price * rounded_qty

        if not validate_order_notional(pair, rounded_price, rounded_qty):
            logger.warning(
                "Order rejected by precision gate: notional value INR %.2f < min ₹100.00 for pair %s",
                notional_value, pair,
            )
            return {
                "success": False,
                "error": "ORDER_NOTIONAL_BELOW_MINIMUM",
                "notional_value": notional_value,
                "message": f"Notional value INR {notional_value:.2f} is below minimum INR 100.00",
            }

        # Mark signal as processed once validated
        self.mark_signal_processed(idempotency_key)

        if is_dry_run:
            logger.info(
                "[DRY-RUN] AutoTradeRouter mapped signal %s to bot %s for pair %s @ INR %.2f (Qty: %s, Notional: INR %.2f)",
                signal_id, target_bot.value, pair, rounded_price, rounded_qty, notional_value,
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
