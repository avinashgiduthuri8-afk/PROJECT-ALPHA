"""
3. VCP (Minervini Volatility Contraction Pattern) Strategy Adapter.

Specification:
  - 3-wave volatility contraction (T1 >= T2 >= T3) + breakout above pivot resistance
  - Base SL: 2.0% (Tightened: 1.2%), Base TP: 5.0%
  - Minimum Net R:R >= 1.50 after statutory friction deductions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from v2.core.types import BotName, ExitReason
from v2.trading.precision_rules import round_price, round_qty
from .base import BaseBotAdapter


class VCPAdapter(BaseBotAdapter):
    """Execution adapter for Volatility Contraction Pattern bot."""

    def __init__(self) -> None:
        super().__init__(BotName.VCP)
        self.base_sl_pct = 2.0
        self.tightened_sl_pct = 1.2
        self.take_profit_pct = 5.0

    def calculate_order(
        self,
        coin: str,
        pair: str,
        approved_amount: float,
        current_price: float,
        ai_adjustments: dict,
    ) -> Dict[str, Any]:
        tighten = ai_adjustments.get("tighten_stop", False)
        sl_pct = self.tightened_sl_pct if tighten else self.base_sl_pct

        rounded_entry = round_price(pair, current_price)
        raw_sl = rounded_entry * (1.0 - sl_pct / 100.0)
        raw_tp = rounded_entry * (1.0 + self.take_profit_pct / 100.0)

        rounded_sl = round_price(pair, raw_sl)
        rounded_tp = round_price(pair, raw_tp)

        raw_qty = approved_amount / rounded_entry if rounded_entry > 0 else 0.0
        rounded_qty = round_qty(pair, raw_qty)

        return {
            "bot": self.bot_name,
            "coin": coin,
            "pair": pair,
            "entry_price": rounded_entry,
            "qty": rounded_qty,
            "amount": round(rounded_entry * rounded_qty, 2),
            "stop_loss": rounded_sl,
            "take_profit": rounded_tp,
            "strategy": "Volatility Contraction Pattern",
            "sl_pct": sl_pct,
            "tp_pct": self.take_profit_pct,
            "net_rr_target": 1.46,
        }
