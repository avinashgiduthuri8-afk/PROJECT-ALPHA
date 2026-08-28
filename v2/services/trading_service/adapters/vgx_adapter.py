"""
VGX Adapter — Volatile Grid Execution strategy.
"""

from __future__ import annotations

from v2.core.types import BotName
from .base import BaseBotAdapter


class VGXAdapter(BaseBotAdapter):
    """Calculates volatile grid orders with step intervals."""

    def __init__(self) -> None:
        super().__init__(BotName.VGX)

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

        # Step take profit: 2.0%
        # Boundary stop loss: 4.0%
        stop_loss = round(current_price * 0.96, 4)
        take_profit = round(current_price * 1.02, 4)

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
