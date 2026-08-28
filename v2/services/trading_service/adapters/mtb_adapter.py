"""
MTB Adapter — Momentum Trend Breakout strategy.
"""

from __future__ import annotations

from typing import Optional

from v2.core.types import BotName
from .base import BaseBotAdapter


class MTBAdapter(BaseBotAdapter):
    """Calculates breakout trade orders with dynamic ATR-based or percentage stops."""

    def __init__(self) -> None:
        super().__init__(BotName.MTB)

    def calculate_order(
        self,
        coin: str,
        pair: str,
        approved_amount: float,
        current_price: float,
        ai_adjustments: dict,
    ) -> dict:
        if current_price <= 0.0:
            current_price = 1.0

        tighten = ai_adjustments.get("tighten_stop", False)
        
        # Stop loss percentage: 2.0% normal, 1.2% if tightened by AI
        sl_pct = 0.012 if tighten else 0.020
        # Take profit percentage: 4.5% standard
        tp_pct = 0.045

        stop_loss = round(current_price * (1.0 - sl_pct), 4)
        take_profit = round(current_price * (1.0 + tp_pct), 4)

        qty = round(approved_amount / current_price, 6)

        return {
            "bot": self.bot_name,
            "coin": coin,
            "pair": pair,
            "entry_price": current_price,
            "qty": qty,
            "amount": approved_amount,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
