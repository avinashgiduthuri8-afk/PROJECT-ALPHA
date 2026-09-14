"""
4. BBS (Bollinger Band Squeeze Breakout) Strategy Adapter.

Specification:
  - Bollinger Bands (20,2) squeeze inside Keltner Channels (20, 1.5 ATR)
  - Base SL: 8.0% (Tightened: 5.0%), Base TP: 25.0%
  - Minimum Net R:R >= 2.00 after statutory friction deductions
"""

from __future__ import annotations

from typing import Any

from core.types import BotName
from execution.trading.precision_rules import round_price, round_qty, round_qty_up

from .base import BaseBotAdapter


class BBSAdapter(BaseBotAdapter):
    """Execution adapter for Bollinger Band Squeeze Breakout bot."""

    def __init__(self) -> None:
        super().__init__(BotName.BBS)
        self.base_sl_pct = 2.5
        self.tightened_sl_pct = 1.5
        self.take_profit_pct = 6.0

    def calculate_order(
        self,
        coin: str,
        pair: str,
        approved_amount: float,
        current_price: float,
        ai_adjustments: dict,
    ) -> dict[str, Any]:
        tighten = ai_adjustments.get("tighten_stop", False)
        sl_pct = self.tightened_sl_pct if tighten else self.base_sl_pct

        # Dynamic TP: Standard 6.0% unless High Conviction (score >= 90) which targets 25.0%
        score = float(
            ai_adjustments.get("score") or ai_adjustments.get("confluence_score") or 0.0
        )
        is_high_conviction = score >= 90.0 or ai_adjustments.get(
            "high_conviction", False
        )
        tp_pct = 25.0 if is_high_conviction else self.take_profit_pct

        rounded_entry = round_price(pair, current_price)
        raw_sl = rounded_entry * (1.0 - sl_pct / 100.0)
        raw_tp = rounded_entry * (1.0 + tp_pct / 100.0)

        rounded_sl = round_price(pair, raw_sl)
        rounded_tp = round_price(pair, raw_tp)

        approved_amount = max(200.0, float(approved_amount))
        raw_qty = approved_amount / rounded_entry if rounded_entry > 0 else 0.0
        rounded_qty = round_qty(pair, raw_qty)
        if rounded_entry * rounded_qty < 200.0 and rounded_entry > 0:
            rounded_qty = round_qty_up(pair, 200.0 / rounded_entry)

        return {
            "bot": self.bot_name,
            "coin": coin,
            "pair": pair,
            "entry_price": rounded_entry,
            "qty": rounded_qty,
            "amount": round(rounded_entry * rounded_qty, 2),
            "stop_loss": rounded_sl,
            "take_profit": rounded_tp,
            "strategy": "Bollinger Band Squeeze Breakout",
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "net_rr_target": 1.50,
        }
