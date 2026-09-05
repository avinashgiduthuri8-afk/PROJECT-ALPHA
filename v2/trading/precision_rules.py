"""
PROJECT-ALPHA Precision & Order Book Rounding Engine.

Lookup table and rounding helpers for all 12 CoinDCX INR pairs:
  - Tier 1 (Mega): BTC/INR, ETH/INR, BNB/INR
  - Tier 2 (Mid): SOL/INR, AVAX/INR, LINK/INR
  - Tier 3 (Low/Fractional): XRP/INR, ADA/INR, MATIC/INR, DOGE/INR, TRX/INR, SHIB/INR
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class PairPrecisionSpec:
    pair: str
    base_price: float
    price_decimals: int    # Decimal places for price rounding (tick size)
    lot_step_decimals: int # Decimal places for quantity step rounding (roundp)
    min_lot_qty: float     # Minimum tradeable quantity
    min_notional_inr: float = 100.0  # CoinDCX minimum order value in INR


# ── Canonical 12 CoinDCX INR Trading Pairs Precision Table ──────────────────
PRECISION_TABLE: Dict[str, PairPrecisionSpec] = {
    # ── Tier 1: Mega-Cap / High-Value ─────────────────────────────────────────
    "BTC/INR": PairPrecisionSpec(
        pair="BTC/INR",
        base_price=8200000.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=5,   # Step: 0.00001 BTC
        min_lot_qty=0.00001,
        min_notional_inr=100.0,
    ),
    "ETH/INR": PairPrecisionSpec(
        pair="ETH/INR",
        base_price=260000.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=4,   # Step: 0.0001 ETH
        min_lot_qty=0.0001,
        min_notional_inr=100.0,
    ),
    "BNB/INR": PairPrecisionSpec(
        pair="BNB/INR",
        base_price=52000.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=3,   # Step: 0.001 BNB
        min_lot_qty=0.001,
        min_notional_inr=100.0,
    ),

    # ── Tier 2: Mid-Cap Medium-Value ──────────────────────────────────────────
    "SOL/INR": PairPrecisionSpec(
        pair="SOL/INR",
        base_price=12500.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=2,   # Step: 0.01 SOL
        min_lot_qty=0.01,
        min_notional_inr=100.0,
    ),
    "AVAX/INR": PairPrecisionSpec(
        pair="AVAX/INR",
        base_price=2800.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=2,   # Step: 0.01 AVAX
        min_lot_qty=0.01,
        min_notional_inr=100.0,
    ),
    "LINK/INR": PairPrecisionSpec(
        pair="LINK/INR",
        base_price=1400.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=2,   # Step: 0.01 LINK
        min_lot_qty=0.01,
        min_notional_inr=100.0,
    ),

    # ── Tier 3: Low Price & Fractional Coins ──────────────────────────────────
    "XRP/INR": PairPrecisionSpec(
        pair="XRP/INR",
        base_price=110.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=1,   # Step: 0.1 XRP
        min_lot_qty=0.1,
        min_notional_inr=100.0,
    ),
    "ADA/INR": PairPrecisionSpec(
        pair="ADA/INR",
        base_price=65.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=1,   # Step: 0.1 ADA
        min_lot_qty=0.1,
        min_notional_inr=100.0,
    ),
    "MATIC/INR": PairPrecisionSpec(
        pair="MATIC/INR",
        base_price=48.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=1,   # Step: 0.1 MATIC
        min_lot_qty=0.1,
        min_notional_inr=100.0,
    ),
    "DOGE/INR": PairPrecisionSpec(
        pair="DOGE/INR",
        base_price=16.50,
        price_decimals=3,      # Tick: ₹0.001
        lot_step_decimals=0,   # Step: 1.0 DOGE
        min_lot_qty=1.0,
        min_notional_inr=100.0,
    ),
    "TRX/INR": PairPrecisionSpec(
        pair="TRX/INR",
        base_price=18.00,
        price_decimals=3,      # Tick: ₹0.001
        lot_step_decimals=0,   # Step: 1.0 TRX
        min_lot_qty=1.0,
        min_notional_inr=100.0,
    ),
    "SHIB/INR": PairPrecisionSpec(
        pair="SHIB/INR",
        base_price=0.0018,
        price_decimals=6,      # Tick: ₹0.000001
        lot_step_decimals=-3,  # Step: 1000 SHIB
        min_lot_qty=1000.0,
        min_notional_inr=100.0,
    ),
    "ZEC/INR": PairPrecisionSpec(

        pair="ZEC/INR",
        base_price=3500.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=4,   # Step: 0.0001 ZEC
        min_lot_qty=0.0001,
        min_notional_inr=100.0,
    ),
    "POL/INR": PairPrecisionSpec(
        pair="POL/INR",
        base_price=48.0,
        price_decimals=2,
        lot_step_decimals=1,
        min_lot_qty=0.1,
        min_notional_inr=100.0,
    ),
}

DEFAULT_SPEC = PairPrecisionSpec(
    pair="CUSTOM/INR",
    base_price=100.0,
    price_decimals=2,
    lot_step_decimals=6,
    min_lot_qty=0.000001,
    min_notional_inr=100.0,
)


def get_pair_spec(pair: str) -> PairPrecisionSpec:
    """Normalize and look up pair precision specifications."""
    clean_pair = pair.upper().replace("_", "/").replace("B-", "").replace("-", "/")
    if "/" not in clean_pair:
        clean_pair = f"{clean_pair}/INR"
    if clean_pair in PRECISION_TABLE:
        return PRECISION_TABLE[clean_pair]

    base_coin = clean_pair.split("/")[0]
    inr_key = f"{base_coin}/INR"
    if inr_key in PRECISION_TABLE:
        return PRECISION_TABLE[inr_key]

    return DEFAULT_SPEC


def round_price(pair: str, price: float) -> float:
    """Round price according to pair tick precision."""
    spec = get_pair_spec(pair)
    if spec.price_decimals <= 0:
        return float(round(price))
    return float(round(price, spec.price_decimals))


def round_qty(pair: str, qty: float) -> float:
    """Round lot quantity down to pair step size (roundp)."""
    if qty <= 0:
        return 0.0

    spec = get_pair_spec(pair)
    if spec.lot_step_decimals < 0:
        step = 10 ** abs(spec.lot_step_decimals)
        res = float(math.floor(qty / step) * step)
    elif spec.lot_step_decimals == 0:
        res = float(math.floor(qty))
    else:
        factor = 10 ** spec.lot_step_decimals
        res = float(math.floor(qty * factor) / factor)

    # If step size floored a small positive micro-order to 0.0, preserve precision up to 6 decimals
    if res == 0.0 and qty > 0:
        res = float(math.floor(qty * 1_000_000) / 1_000_000)

    return res


def validate_order_notional(
    pair: str,
    price: float,
    qty: float,
    min_notional: Optional[float] = None,
) -> bool:
    """
    Validate that the order meets both minimum lot size and minimum order value (₹100).
    """
    spec = get_pair_spec(pair)
    min_val = min_notional if min_notional is not None else spec.min_notional_inr
    notional = price * qty
    return (qty >= spec.min_lot_qty) and (notional >= min_val)

