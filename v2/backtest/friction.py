"""
CoinDCX & Indian Statutory Tax Friction Model (Sec 194S TDS + GST + Exchange Fees + Slippage).

Friction Specifications:
  - Buy Friction (INR Spot): 0.20% Exchange Fee + 18% GST on Fee (0.036%) = 0.236%
  - Buy Friction (C2C Crypto Pairs): 1.00% Sec 194S TDS + 0.20% Fee + 18% GST = 1.236%
  - Sell Friction (All Pairs): 1.00% Sec 194S TDS + 0.20% Fee + 18% GST = 1.236%
  - Execution Slippage Buffer: 0.05% per side (0.10% round-trip)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class FrictionConfig:
    exchange_fee_pct: float = 0.20       # 0.20% base trading fee
    gst_rate_pct: float = 18.0           # 18% GST on exchange fee (0.036%)
    tds_rate_pct: float = 1.00           # 1.00% Sec 194S TDS on sell (and C2C buy)
    slippage_per_side_pct: float = 0.05   # 0.05% per side execution buffer
    is_c2c_pair: bool = False            # True for crypto-to-crypto (e.g. BTC/USDT), False for INR

    @property
    def buy_fee_pct(self) -> float:
        base = self.exchange_fee_pct * (1.0 + self.gst_rate_pct / 100.0)  # 0.236%
        if self.is_c2c_pair:
            base += self.tds_rate_pct  # 1.236%
        return round(base, 4)

    @property
    def sell_fee_pct(self) -> float:
        base = (self.exchange_fee_pct * (1.0 + self.gst_rate_pct / 100.0)) + self.tds_rate_pct  # 1.236%
        return round(base, 4)

    @property
    def round_trip_fee_pct(self) -> float:
        return round(self.buy_fee_pct + self.sell_fee_pct, 4)

    @property
    def round_trip_slippage_pct(self) -> float:
        return round(self.slippage_per_side_pct * 2.0, 4)

    @property
    def total_round_trip_drag_pct(self) -> float:
        return round(self.round_trip_fee_pct + self.round_trip_slippage_pct, 4)


class CoinDCXFrictionModel:
    """Calculates net execution prices and realized PnL after statutory TDS, GST, and slippage."""

    def __init__(self, config: FrictionConfig = None) -> None:
        self.config = config or FrictionConfig()

    def get_effective_entry_price(self, raw_entry_price: float) -> float:
        """Entry price after applying buy-side slippage and buy fee friction."""
        price_with_slippage = raw_entry_price * (1.0 + self.config.slippage_per_side_pct / 100.0)
        effective_price = price_with_slippage * (1.0 + self.config.buy_fee_pct / 100.0)
        return round(effective_price, 4)

    def get_effective_exit_price(self, raw_exit_price: float) -> float:
        """Exit price after applying sell-side slippage and sell-side TDS/GST/fee friction."""
        price_with_slippage = raw_exit_price * (1.0 - self.config.slippage_per_side_pct / 100.0)
        effective_price = price_with_slippage * (1.0 - self.config.sell_fee_pct / 100.0)
        return round(effective_price, 4)

    def calculate_trade_net_pnl(
        self,
        entry_price: float,
        exit_price: float,
        position_size_qty: float,
    ) -> Dict[str, float]:
        """
        Calculates gross vs. net realized PnL for a trade execution.
        """
        gross_entry_cost = entry_price * position_size_qty
        gross_exit_proceeds = exit_price * position_size_qty
        gross_pnl = gross_exit_proceeds - gross_entry_cost
        gross_pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

        eff_entry_price = self.get_effective_entry_price(entry_price)
        eff_exit_price = self.get_effective_exit_price(exit_price)

        net_entry_cost = eff_entry_price * position_size_qty
        net_exit_proceeds = eff_exit_price * position_size_qty
        net_pnl = net_exit_proceeds - net_entry_cost
        net_pnl_pct = ((eff_exit_price - eff_entry_price) / eff_entry_price) * 100.0 if eff_entry_price > 0 else 0.0

        total_friction_cost = net_entry_cost - gross_entry_cost + (gross_exit_proceeds - net_exit_proceeds)

        return {
            "gross_entry_cost": round(gross_entry_cost, 2),
            "gross_exit_proceeds": round(gross_exit_proceeds, 2),
            "gross_pnl": round(gross_pnl, 2),
            "gross_pnl_pct": round(gross_pnl_pct, 2),
            "eff_entry_price": round(eff_entry_price, 4),
            "eff_exit_price": round(eff_exit_price, 4),
            "net_pnl": round(net_pnl, 2),
            "net_pnl_pct": round(net_pnl_pct, 2),
            "total_friction_cost": round(total_friction_cost, 2),
        }
