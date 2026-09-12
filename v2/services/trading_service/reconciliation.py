"""
V2 Exchange Balance & Reconciliation Worker.

Runs periodic async background reconciliation jobs (e.g. every 60s) to reconcile
local SQLite position records against CoinDCX sub-account open orders and balances.
Flags orphan orders, partial fills, desynced balances, or manual exchange interventions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from v2.core.logging import get_logger
from v2.core.types import BotName, PositionStatus
from v2.repository.position_repo import PositionRepository
from v2.trading.subaccount_manager import CoinDCXSubAccountManager

logger = get_logger("v2.services.trading_service.reconciliation")


class ReconciliationService:
    """
    Exchange Balance & Position Reconciliation Worker.
    Periodically checks local position DB records against CoinDCX sub-account clients.
    """

    def __init__(
        self,
        position_repo: PositionRepository,
        subaccount_manager: Optional[CoinDCXSubAccountManager] = None,
        interval_seconds: int = 60,
    ) -> None:
        self._position_repo = position_repo
        self._subaccount_manager = subaccount_manager or CoinDCXSubAccountManager()
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_reconciliation_result: Dict[str, Any] = {}

    async def start(self) -> None:
        """Start periodic background reconciliation loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._reconciliation_loop())
        logger.info("ReconciliationService background worker started (interval: %ds)", self.interval_seconds)

    async def stop(self) -> None:
        """Stop background worker gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ReconciliationService background worker stopped")

    async def _reconciliation_loop(self) -> None:
        while self._running:
            try:
                await self.reconcile_positions()
            except Exception as exc:
                logger.error("Error in reconciliation loop: %s", exc, exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def reconcile_positions(self) -> Dict[str, Any]:
        """
        Reconcile local SQLite open positions, order records, and balances
        against CoinDCX REST API sub-account state.

        Detects and reports:
          - orphan orders (active orders on exchange not in SQLite)
          - missing orders (SQLite open positions with order IDs missing on exchange)
          - partial fills (quantity discrepancies; auto-aligns SQLite quantity)
          - filled orders (confirmed filled orders)
          - cancelled/rejected orders (auto-repairs SQLite position to CLOSED)
          - balance mismatches (INR cash + deployed capital discrepancies vs CoinDCX)
          - position mismatches (crypto asset holding discrepancies vs SQLite open positions)
        """
        now_str = datetime.now(timezone.utc).isoformat()
        active_positions = await self._position_repo.get_active_positions()

        orphan_orders: List[Dict[str, Any]] = []
        missing_orders: List[Dict[str, Any]] = []
        partial_fills: List[Dict[str, Any]] = []
        filled_orders: List[Dict[str, Any]] = []
        cancelled_rejected_orders: List[Dict[str, Any]] = []
        balance_mismatches: List[Dict[str, Any]] = []
        position_mismatches: List[Dict[str, Any]] = []
        discrepancies: List[Dict[str, Any]] = []
        desynced_positions: List[Dict[str, Any]] = []

        orders_checked = 0
        reconciled_count = 0
        mismatches_count = 0
        unknown_orders_count = 0

        # Build lookup maps for SQLite open positions
        pos_by_ex_id: Dict[str, Any] = {}
        pos_by_client_id: Dict[str, Any] = {}
        pos_qty_by_coin: Dict[str, float] = {}

        for pos in active_positions:
            ex_id = getattr(pos, "exchange_order_id", None)
            cl_id = getattr(pos, "client_order_id", None) or getattr(pos, "id", None)
            coin = (getattr(pos, "coin", "") or "").upper()
            qty = float(getattr(pos, "qty", 0.0) or 0.0)

            if ex_id:
                pos_by_ex_id[str(ex_id)] = pos
            if cl_id:
                pos_by_client_id[str(cl_id)] = pos

            if coin:
                pos_qty_by_coin[coin] = pos_qty_by_coin.get(coin, 0.0) + qty

        # 1. Query Exchange Open Active Orders & Check for Orphan Orders
        master_client = self._subaccount_manager.get_client(BotName.STE)
        try:
            active_orders_res = await master_client.get_active_orders()
            if active_orders_res.get("success"):
                ex_active_orders = active_orders_res.get("orders", [])
                for ex_ord in ex_active_orders:
                    ex_ord_id = str(ex_ord.get("id") or ex_ord.get("order_id") or "")
                    cl_ord_id = str(ex_ord.get("client_order_id") or "")
                    market = str(ex_ord.get("market") or ex_ord.get("pair") or "")

                    matched_pos = pos_by_ex_id.get(ex_ord_id) or pos_by_client_id.get(cl_ord_id)
                    if not matched_pos:
                        orphan_item = {
                            "exchange_order_id": ex_ord_id or None,
                            "client_order_id": cl_ord_id or None,
                            "market": market,
                            "status": str(ex_ord.get("status", "OPEN")).upper(),
                            "side": str(ex_ord.get("side", "")).upper(),
                            "price": float(ex_ord.get("price_per_unit") or ex_ord.get("price") or 0.0),
                            "qty": float(ex_ord.get("total_quantity") or ex_ord.get("quantity") or 0.0),
                            "action": "FLAGGED_ORPHAN_ORDER",
                            "message": f"Active order {ex_ord_id} on exchange has no corresponding active position in SQLite.",
                        }
                        orphan_orders.append(orphan_item)
                        discrepancies.append(orphan_item)
                        mismatches_count += 1
        except Exception as exc:
            logger.warning("Error fetching active orders for reconciliation: %s", exc)

        # 2. Check Each Local Active Position against Exchange Status
        for pos in active_positions:
            orders_checked += 1
            ex_id = getattr(pos, "exchange_order_id", None)
            cl_id = getattr(pos, "client_order_id", None) or getattr(pos, "id", None)
            bot_name = getattr(pos, "bot", BotName.STE)
            sub_client = self._subaccount_manager.get_client(bot_name)

            if not ex_id:
                missing_item = {
                    "position_id": pos.id,
                    "coin": pos.coin,
                    "bot": bot_name.value if hasattr(bot_name, "value") else str(bot_name),
                    "exchange_order_id": None,
                    "local_status": str(getattr(pos.status, "value", pos.status)),
                    "exchange_status": "MISSING_EXCHANGE_ORDER_ID",
                    "action": "FLAGGED_MISSING_EXCHANGE_ORDER_ID",
                    "message": f"Position {pos.id} is active locally but has no exchange_order_id.",
                }
                missing_orders.append(missing_item)
                discrepancies.append(missing_item)
                unknown_orders_count += 1
                mismatches_count += 1
                continue

            try:
                status_res = await sub_client.get_order_status(str(ex_id))
                if not status_res.get("success") and cl_id:
                    status_res = await sub_client.get_order_by_client_id(str(cl_id))

                if not status_res.get("success"):
                    missing_item = {
                        "position_id": pos.id,
                        "coin": pos.coin,
                        "bot": bot_name.value if hasattr(bot_name, "value") else str(bot_name),
                        "exchange_order_id": ex_id,
                        "local_status": str(getattr(pos.status, "value", pos.status)),
                        "exchange_status": "ORDER_NOT_FOUND_ON_EXCHANGE",
                        "action": "FLAGGED_MISSING_ORDER",
                        "message": f"Order {ex_id} for position {pos.id} was not found on exchange.",
                    }
                    missing_orders.append(missing_item)
                    discrepancies.append(missing_item)
                    unknown_orders_count += 1
                    mismatches_count += 1
                    continue

                ex_status = str(status_res.get("status", "UNKNOWN")).upper()
                ex_filled_qty = float(status_res.get("filled_qty", 0.0))
                reconciled_count += 1

                # Cancelled or Rejected on exchange
                if ex_status in ("CANCELLED", "REJECTED", "EXPIRED", "FAILED"):
                    canc_item = {
                        "position_id": pos.id,
                        "coin": pos.coin,
                        "bot": bot_name.value if hasattr(bot_name, "value") else str(bot_name),
                        "exchange_order_id": ex_id,
                        "local_status": str(getattr(pos.status, "value", pos.status)),
                        "exchange_status": ex_status,
                        "action": "AUTO_REPAIRED_TO_CLOSED",
                        "message": f"Position {pos.id} closed because exchange order status is {ex_status}.",
                    }
                    cancelled_rejected_orders.append(canc_item)
                    discrepancies.append(canc_item)
                    mismatches_count += 1
                    from v2.core.types import ExitReason
                    await self._position_repo.close(pos.id, exit_price=pos.entry_price, exit_reason=ExitReason.MANUAL)

                # Filled order
                elif ex_status == "FILLED":
                    filled_item = {
                        "position_id": pos.id,
                        "coin": pos.coin,
                        "exchange_order_id": ex_id,
                        "status": "FILLED",
                        "filled_qty": ex_filled_qty or pos.qty,
                        "action": "CONFIRMED_FILLED",
                    }
                    filled_orders.append(filled_item)
                    if str(getattr(pos.status, "value", pos.status)).upper() == "PENDING_ENTRY":
                        from v2.core.types import PositionStatus
                        await self._position_repo.update_status(pos.id, PositionStatus.OPEN)

                    if ex_filled_qty > 0 and abs(ex_filled_qty - pos.qty) > 1e-6:
                        partial_item = {
                            "position_id": pos.id,
                            "coin": pos.coin,
                            "exchange_order_id": ex_id,
                            "local_qty": pos.qty,
                            "exchange_filled_qty": ex_filled_qty,
                            "action": "QUANTITY_ALIGNED",
                            "message": f"Local position quantity {pos.qty} aligned to exchange filled quantity {ex_filled_qty}.",
                        }
                        partial_fills.append(partial_item)
                        discrepancies.append(partial_item)
                        mismatches_count += 1
                        await self._position_repo.update_qty(pos.id, ex_filled_qty)
                        pos.qty = ex_filled_qty

                # Partially filled order
                elif ex_status == "PARTIALLY_FILLED":
                    if ex_filled_qty > 0 and abs(ex_filled_qty - pos.qty) > 1e-6:
                        partial_item = {
                            "position_id": pos.id,
                            "coin": pos.coin,
                            "exchange_order_id": ex_id,
                            "local_qty": pos.qty,
                            "exchange_filled_qty": ex_filled_qty,
                            "action": "QUANTITY_ALIGNED",
                            "message": f"Local position quantity {pos.qty} aligned to exchange partial fill quantity {ex_filled_qty}.",
                        }
                        partial_fills.append(partial_item)
                        discrepancies.append(partial_item)
                        mismatches_count += 1
                        await self._position_repo.update_qty(pos.id, ex_filled_qty)
                        pos.qty = ex_filled_qty

            except Exception as e:
                logger.error("Error reconciling position %s against exchange: %s", pos.id, e)
                desynced_positions.append({"position_id": pos.id, "reason": str(e)})

        # 3. Check Account Balances & INR Mismatches
        try:
            bal_res = await master_client.get_balances()
            if bal_res.get("success"):
                ex_inr_bal = float(bal_res.get("inr_balance", 0.0))
                ex_inr_locked = float(bal_res.get("inr_locked", 0.0))
                ex_inr_total = ex_inr_bal + ex_inr_locked
                local_inr = master_client.wallet_balance_inr
                diff = abs(local_inr - ex_inr_total)

                if diff > 1.0 and ex_inr_total > 0:
                    bal_item = {
                        "local_inr": local_inr,
                        "exchange_inr_balance": ex_inr_bal,
                        "exchange_inr_locked": ex_inr_locked,
                        "difference": round(diff, 2),
                        "action": "BALANCE_ALIGNED_TO_EXCHANGE",
                        "message": f"Local wallet balance INR {local_inr:.2f} differs from exchange INR {ex_inr_total:.2f} by INR {diff:.2f}.",
                    }
                    balance_mismatches.append(bal_item)
                    discrepancies.append(bal_item)
                    mismatches_count += 1
                    with master_client._lock:
                        master_client._shared_state["wallet_balance_inr"] = ex_inr_bal

                # 4. Check Asset Position Quantity Mismatches vs Real CoinDCX Crypto Holdings
                asset_balances = bal_res.get("asset_balances", {})
                all_coins = set(pos_qty_by_coin.keys()).union(asset_balances.keys())
                for coin in all_coins:
                    if coin == "INR":
                        continue
                    local_coin_qty = pos_qty_by_coin.get(coin, 0.0)
                    exchange_coin_qty = float(asset_balances.get(coin, 0.0))
                    qty_diff = abs(local_coin_qty - exchange_coin_qty)

                    if qty_diff > 1e-6 and (local_coin_qty > 0 or exchange_coin_qty > 0):
                        pos_mismatch_item = {
                            "coin": coin,
                            "local_qty": local_coin_qty,
                            "exchange_qty": exchange_coin_qty,
                            "difference": round(qty_diff, 8),
                            "action": "POSITION_MISMATCH_DETECTED",
                            "message": f"SQLite open position quantity for {coin} ({local_coin_qty}) differs from CoinDCX holding ({exchange_coin_qty}).",
                        }
                        position_mismatches.append(pos_mismatch_item)
                        discrepancies.append(pos_mismatch_item)
                        mismatches_count += 1
        except Exception as exc:
            logger.warning("Error performing balance & asset position reconciliation: %s", exc)

        is_clean = (
            len(orphan_orders) == 0 and
            len(missing_orders) == 0 and
            len(partial_fills) == 0 and
            len(cancelled_rejected_orders) == 0 and
            len(balance_mismatches) == 0 and
            len(position_mismatches) == 0 and
            len(desynced_positions) == 0
        )

        status_str = "IN_SYNC" if is_clean else "DISCREPANCIES_DETECTED"

        result = {
            "timestamp": now_str,
            "status": status_str,
            "is_clean": is_clean,
            "open_positions_count": len(active_positions),
            "positions_checked": len(active_positions),
            "orders_checked": orders_checked,
            "reconciled": reconciled_count,
            "mismatches": mismatches_count,
            "unknown_orders": unknown_orders_count,
            "discrepancies": discrepancies,
            "orphan_orders": orphan_orders,
            "missing_orders": missing_orders,
            "partial_fills": partial_fills,
            "filled_orders": filled_orders,
            "cancelled_rejected_orders": cancelled_rejected_orders,
            "balance_mismatches": balance_mismatches,
            "position_mismatches": position_mismatches,
            "desynced_positions": desynced_positions,
            "synced_count": reconciled_count,
            "total_active_positions": len(active_positions),
        }

        self._last_reconciliation_result = result
        if not is_clean:
            logger.warning(
                "CoinDCX Exchange Reconciliation flagged issues: %d mismatches (%d orphans, %d missing, %d partials, %d cancelled, %d bal_mismatch, %d pos_mismatch)",
                mismatches_count, len(orphan_orders), len(missing_orders), len(partial_fills),
                len(cancelled_rejected_orders), len(balance_mismatches), len(position_mismatches)
            )
        else:
            logger.info("CoinDCX Exchange Reconciliation cleanly verified %d active positions and balances", len(active_positions))

        return result

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "last_result": self._last_reconciliation_result,
        }
