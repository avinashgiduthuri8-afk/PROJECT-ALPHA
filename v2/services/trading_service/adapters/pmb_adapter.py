"""
PMB Adapter — Pullback Momentum Breakout strategy.
"""

from __future__ import annotations

from v2.core.types import BotName
from .base import BaseBotAdapter


class PMBAdapter(BaseBotAdapter):
    """Calculates pullback accumulation orders with support-anchored stop loss."""

    def __init__(self) -> None:
        super().__init__(BotName.PMB)

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
        
        # Stop loss: 2.5% standard, 1.5% tightened
        sl_pct = 0.015 if tighten else 0.025
        # Take profit: 3.5%
        tp_pct = 0.035

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
