"""
V2 Position Manager & State Tracking Engine.

Manages full position lifecycle states: PENDING_ENTRY → OPEN → PENDING_EXIT → CLOSED.
Supports bracket order logic (Stop Loss, Take Profit, Trailing Stop) and deducts statutory
round-trip drag (1.572% total friction: 0.20% exchange fee + 18% GST + 1% Sec 194S TDS + 0.10% slippage)
upon position closure. Persists all transitions directly to SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.logging import get_logger
from v2.core.types import (
    BotMode, BotName, ExitReason, Position, PositionStatus, Trade
)
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository

logger = get_logger("v2.services.trading_service.position_manager")

# Statutory Round-Trip Drag Rate: 1.572% Total Friction
# Breakdown: 0.20% Exchange Fee + 18% GST on Fee (0.036%) + 1.00% Sec 194S TDS + 0.10% Slippage
STATUTORY_ROUND_TRIP_DRAG_RATE = 0.01572


class PositionState(str, Enum):
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN          = "OPEN"
    PENDING_EXIT  = "PENDING_EXIT"
    CLOSED        = "CLOSED"


class PositionManager:
    """
    Position Lifecycle & State Tracking Manager.
    Handles position state transitions, bracket evaluations (SL, TP, Trailing Stop),
    statutory fee computations, and SQLite database persistence.
    """

    def __init__(
        self,
        position_repo: PositionRepository,
        trade_repo: Optional[TradeRepository] = None,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._position_repo = position_repo
        self._trade_repo = trade_repo
        self._bus = bus
        self._peak_prices: Dict[str, float] = {}
        self._trailing_stops: Dict[str, float] = {}

    def compute_statutory_drag(self, entry_price: float, exit_price: float, qty: float) -> float:
        """
        Compute statutory 1.572% round-trip drag friction.
        Friction is calculated on the total traded value (entry notional + exit notional).
        """
        entry_notional = entry_price * qty
        exit_notional = exit_price * qty
        total_traded_value = entry_notional + exit_notional
        # Half of 1.572% applied to round-trip total value, or 1.572% on average position value
        return total_traded_value * (STATUTORY_ROUND_TRIP_DRAG_RATE / 2.0)

    async def register_position(
        self,
        bot: BotName,
        coin: str,
        pair: str,
        entry_price: float,
        qty: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        mode: BotMode = BotMode.PAPER,
        signal_id: Optional[str] = None,
        initial_status: PositionState = PositionState.OPEN,
    ) -> Position:
        """
        Register a new position and persist it to SQLite.
        """
        pos_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        status_enum = PositionStatus.OPEN if initial_status in (PositionState.OPEN, PositionState.PENDING_ENTRY) else PositionStatus.CLOSED

        pos = Position(
            id=pos_id,
            bot=bot,
            coin=coin.upper(),
            pair=pair.upper().replace("_", "/"),
            qty=qty,
            entry_price=entry_price,
            entry_time=now,
            mode=mode,
            status=status_enum,
            current_price=entry_price,
            unrealised_pnl=0.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_id=signal_id,
        )

        await self._position_repo.insert(pos)

        # Initialize peak price tracker for trailing stop
        self._peak_prices[pos_id] = entry_price

        if self._bus:
            payload = {
                "position_id": pos_id,
                "bot": bot.value if hasattr(bot, "value") else str(bot),
                "coin": pos.coin,
                "pair": pos.pair,
                "entry_price": entry_price,
                "qty": qty,
                "status": initial_status.value,
                "opened_at": now.isoformat(),
            }
            await self._bus.publish(EventType.POSITION_OPENED, payload)

        logger.info(
            "[%s] Registered position %s for %s (%s) @ INR %.2f (Qty: %s)",
            bot.value, pos_id, pos.coin, pos.pair, entry_price, qty,
        )
        return pos

    async def update_position_state(
        self, position_id: str, new_state: PositionState
    ) -> None:
        """Transition position lifecycle state."""
        status_val = PositionStatus.OPEN if new_state != PositionState.CLOSED else PositionStatus.CLOSED
        await self._position_repo.update_status(position_id, status_val)
        logger.info("Position %s transitioned to state %s", position_id, new_state.value)

    async def update_trailing_stop(
        self, position_id: str, current_price: float, trailing_pct: float = 0.03
    ) -> Optional[float]:
        """
        Update dynamic trailing stop trigger level as peak price moves up.
        """
        pos = await self._position_repo.get_by_id(position_id)
        if not pos or pos.status == PositionStatus.CLOSED:
            return None

        peak = max(self._peak_prices.get(position_id, pos.entry_price), current_price)
        self._peak_prices[position_id] = peak

        trailing_stop = peak * (1.0 - trailing_pct)
        # Ensure trailing stop only moves upwards and never drops below initial stop loss
        if pos.stop_loss and trailing_stop < pos.stop_loss:
            trailing_stop = pos.stop_loss

        self._trailing_stops[position_id] = trailing_stop
        return trailing_stop

    async def evaluate_brackets(
        self, pair: str, current_price: float
    ) -> List[Tuple[Position, ExitReason, float]]:
        """
        Evaluate all active positions for a pair against current price for Stop Loss,
        Take Profit, or Trailing Stop breaches.
        Returns list of (Position, ExitReason, exit_price).
        """
        open_positions = await self._position_repo.get_active_positions()
        triggers: List[Tuple[Position, ExitReason, float]] = []

        target_pair = pair.upper().replace("_", "/")

        for pos in open_positions:
            if pos.pair.upper() != target_pair:
                continue

            # Update peak price for trailing stop evaluation
            self._peak_prices[pos.id] = max(self._peak_prices.get(pos.id, pos.entry_price), current_price)

            # Update unrealised PnL in DB
            unrealised = (current_price - pos.entry_price) * pos.qty
            await self._position_repo.update_price(pos.id, current_price, round(unrealised, 2))

            # 1. Take Profit trigger check
            if pos.take_profit and current_price >= pos.take_profit:
                triggers.append((pos, ExitReason.TAKE_PROFIT, current_price))
                continue

            # 2. Stop Loss trigger check
            if pos.stop_loss and current_price <= pos.stop_loss:
                triggers.append((pos, ExitReason.STOP_LOSS, current_price))
                continue

            # 3. Trailing Stop trigger check
            trailing_stop = self._trailing_stops.get(pos.id)
            if trailing_stop and current_price <= trailing_stop:
                triggers.append((pos, ExitReason.STOP_LOSS, current_price))
                continue

        return triggers

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_reason: ExitReason = ExitReason.TAKE_PROFIT,
    ) -> Tuple[Optional[Position], Optional[Trade]]:
        """
        Close a position, deduct statutory 1.572% friction, and persist trade record to SQLite.
        """
        pos = await self._position_repo.get_by_id(position_id)
        if not pos or pos.status == PositionStatus.CLOSED:
            logger.warning("Attempted to close non-existent or already CLOSED position %s", position_id)
            return None, None

        gross_pnl = (exit_price - pos.entry_price) * pos.qty
        gross_pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100.0 if pos.entry_price > 0 else 0.0

        # Deduct statutory 1.572% round-trip drag friction
        fee_drag = self.compute_statutory_drag(pos.entry_price, exit_price, pos.qty)
        net_realized_pnl = round(gross_pnl - fee_drag, 2)
        net_pnl_pct = round(((net_realized_pnl) / (pos.entry_price * pos.qty)) * 100.0, 2) if pos.entry_price * pos.qty > 0 else 0.0

        now = datetime.now(timezone.utc)

        # Update position record in DB
        await self._position_repo.close_position(
            position_id=pos.id,
            exit_price=exit_price,
            exit_reason=exit_reason,
        )

        trade = Trade(
            id=str(uuid.uuid4()),
            position_id=pos.id,
            bot=pos.bot,
            coin=pos.coin,
            pair=pos.pair,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            qty=pos.qty,
            pnl=net_realized_pnl,
            pnl_pct=net_pnl_pct,
            entry_time=pos.entry_time,
            exit_time=now,
            exit_reason=exit_reason,
            mode=pos.mode,
            signal_id=pos.signal_id,
        )

        if self._trade_repo:
            await self._trade_repo.insert(trade)

        # Clean up tracking dictionaries
        self._peak_prices.pop(position_id, None)
        self._trailing_stops.pop(position_id, None)

        if self._bus:
            payload = {
                "trade_id": trade.id,
                "position_id": pos.id,
                "bot": pos.bot.value if hasattr(pos.bot, "value") else str(pos.bot),
                "coin": pos.coin,
                "pair": pos.pair,
                "gross_pnl": round(gross_pnl, 2),
                "statutory_fee_drag": round(fee_drag, 2),
                "net_pnl": net_realized_pnl,
                "pnl_pct": net_pnl_pct,
                "exit_reason": exit_reason.value if hasattr(exit_reason, "value") else str(exit_reason),
                "exit_price": exit_price,
                "closed_at": now.isoformat(),
            }
            await self._bus.publish(EventType.POSITION_CLOSED, payload)
            await self._bus.publish(EventType.TRADE_CLOSED, payload)

        logger.info(
            "[%s] Position %s CLOSED via %s @ INR %.2f | Gross PnL: INR %.2f, Statutory Drag: INR %.2f, Net PnL: INR %.2f (%.2f%%)",
            pos.bot.value, pos.id, exit_reason.value, exit_price, gross_pnl, fee_drag, net_realized_pnl, net_pnl_pct,
        )

        return pos, trade
