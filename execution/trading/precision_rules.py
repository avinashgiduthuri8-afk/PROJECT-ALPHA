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
    min_notional_inr: float = 200.0  # CoinDCX minimum order value in INR
    min_notional_usdt: float = 1.0   # CoinDCX minimum order value in USDT
    quote_currency: str = "INR"

    @property
    def min_quantity(self) -> float:
        return self.min_lot_qty

    def __getitem__(self, item: str):
        if hasattr(self, item):
            return getattr(self, item)
        if item == "min_quantity":
            return self.min_lot_qty
        raise KeyError(item)



# ── Canonical 12 CoinDCX INR Trading Pairs Precision Table ──────────────────
PRECISION_TABLE: Dict[str, PairPrecisionSpec] = {
    # ── Tier 1: Mega-Cap / High-Value ─────────────────────────────────────────
    "BTC/INR": PairPrecisionSpec(
        pair="BTC/INR",
        base_price=8200000.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=5,   # Step: 0.00001 BTC
        min_lot_qty=0.00001,
        min_notional_inr=200.0,
    ),
    "ETH/INR": PairPrecisionSpec(
        pair="ETH/INR",
        base_price=260000.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=4,   # Step: 0.0001 ETH
        min_lot_qty=0.0001,
        min_notional_inr=200.0,
    ),
    "BNB/INR": PairPrecisionSpec(
        pair="BNB/INR",
        base_price=52000.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=3,   # Step: 0.001 BNB
        min_lot_qty=0.001,
        min_notional_inr=200.0,
    ),

    # ── Tier 2: Mid-Cap Medium-Value ──────────────────────────────────────────
    "SOL/INR": PairPrecisionSpec(
        pair="SOL/INR",
        base_price=12500.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=2,   # Step: 0.01 SOL
        min_lot_qty=0.01,
        min_notional_inr=200.0,
    ),
    "AVAX/INR": PairPrecisionSpec(
        pair="AVAX/INR",
        base_price=2800.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=2,   # Step: 0.01 AVAX
        min_lot_qty=0.01,
        min_notional_inr=200.0,
    ),
    "LINK/INR": PairPrecisionSpec(
        pair="LINK/INR",
        base_price=1400.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=2,   # Step: 0.01 LINK
        min_lot_qty=0.01,
        min_notional_inr=200.0,
    ),

    # ── Tier 3: Low Price & Fractional Coins ──────────────────────────────────
    "XRP/INR": PairPrecisionSpec(
        pair="XRP/INR",
        base_price=110.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=1,   # Step: 0.1 XRP
        min_lot_qty=0.1,
        min_notional_inr=200.0,
    ),
    "ADA/INR": PairPrecisionSpec(
        pair="ADA/INR",
        base_price=65.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=1,   # Step: 0.1 ADA
        min_lot_qty=0.1,
        min_notional_inr=200.0,
    ),
    "MATIC/INR": PairPrecisionSpec(
        pair="MATIC/INR",
        base_price=48.0,
        price_decimals=2,      # Tick: ₹0.01
        lot_step_decimals=1,   # Step: 0.1 MATIC
        min_lot_qty=0.1,
        min_notional_inr=200.0,
    ),
    "DOGE/INR": PairPrecisionSpec(
        pair="DOGE/INR",
        base_price=16.50,
        price_decimals=3,      # Tick: ₹0.001
        lot_step_decimals=0,   # Step: 1.0 DOGE
        min_lot_qty=1.0,
        min_notional_inr=200.0,
    ),
    "TRX/INR": PairPrecisionSpec(
        pair="TRX/INR",
        base_price=18.00,
        price_decimals=3,      # Tick: ₹0.001
        lot_step_decimals=0,   # Step: 1.0 TRX
        min_lot_qty=1.0,
        min_notional_inr=200.0,
    ),
    "SHIB/INR": PairPrecisionSpec(
        pair="SHIB/INR",
        base_price=0.0018,
        price_decimals=6,      # Tick: ₹0.000001
        lot_step_decimals=-3,  # Step: 1000 SHIB
        min_lot_qty=1000.0,
        min_notional_inr=200.0,
    ),
    "ZEC/INR": PairPrecisionSpec(
        pair="ZEC/INR",
        base_price=3500.0,
        price_decimals=1,      # Tick: ₹0.10
        lot_step_decimals=4,   # Step: 0.0001 ZEC
        min_lot_qty=0.0001,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
    ),
    "POL/INR": PairPrecisionSpec(
        pair="POL/INR",
        base_price=48.0,
        price_decimals=2,
        lot_step_decimals=1,
        min_lot_qty=0.1,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
    ),

    # ── USDT Direct Pairs ─────────────────────────────────────────────────────
    "BTC/USDT": PairPrecisionSpec(
        pair="BTC/USDT",
        base_price=90000.0,
        price_decimals=2,      # Tick: $0.01
        lot_step_decimals=5,   # Step: 0.00001 BTC
        min_lot_qty=0.00001,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "ETH/USDT": PairPrecisionSpec(
        pair="ETH/USDT",
        base_price=2700.0,
        price_decimals=2,      # Tick: $0.01
        lot_step_decimals=4,   # Step: 0.0001 ETH
        min_lot_qty=0.0001,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "SOL/USDT": PairPrecisionSpec(
        pair="SOL/USDT",
        base_price=135.0,
        price_decimals=2,      # Tick: $0.01
        lot_step_decimals=3,   # Step: 0.001 SOL
        min_lot_qty=0.001,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "BNB/USDT": PairPrecisionSpec(
        pair="BNB/USDT",
        base_price=600.0,
        price_decimals=2,
        lot_step_decimals=3,
        min_lot_qty=0.001,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "NEAR/USDT": PairPrecisionSpec(
        pair="NEAR/USDT",
        base_price=2.50,
        price_decimals=3,
        lot_step_decimals=2,
        min_lot_qty=0.01,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "RENDER/USDT": PairPrecisionSpec(
        pair="RENDER/USDT",
        base_price=6.0,
        price_decimals=3,
        lot_step_decimals=2,
        min_lot_qty=0.01,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "PEPE/USDT": PairPrecisionSpec(
        pair="PEPE/USDT",
        base_price=0.000008,
        price_decimals=8,
        lot_step_decimals=-2,  # Step: 100 PEPE
        min_lot_qty=100.0,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "DOGE/USDT": PairPrecisionSpec(
        pair="DOGE/USDT",
        base_price=0.10,
        price_decimals=4,
        lot_step_decimals=1,
        min_lot_qty=0.1,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
    "FET/USDT": PairPrecisionSpec(
        pair="FET/USDT",
        base_price=1.20,
        price_decimals=3,
        lot_step_decimals=2,
        min_lot_qty=0.01,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="USDT",
    ),
}

DEFAULT_SPEC = PairPrecisionSpec(
    pair="CUSTOM/INR",
    base_price=100.0,
    price_decimals=8,
    lot_step_decimals=4,
    min_lot_qty=0.0001,
    min_notional_inr=200.0,
    min_notional_usdt=1.0,
    quote_currency="INR",
)


def normalize_price(raw_price: Any) -> float:
    """
    Canonical price normalization at the market data & execution boundary.
    Accepts int, float, str, Decimal. Rejects non-positive, NaN, and Infinite values.
    """
    if raw_price is None:
        raise ValueError("Price cannot be None")
    try:
        val = float(str(raw_price).strip().replace(",", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot parse price from '{raw_price}': {exc}") from exc

    if math.isnan(val) or math.isinf(val) or val <= 0.0:
        raise ValueError(f"Invalid price value: {raw_price} (parsed as {val})")
    return val


def normalize_qty(raw_qty: Any) -> float:
    """
    Canonical quantity normalization.
    Accepts int, float, str, Decimal. Rejects non-positive, NaN, and Infinite values.
    """
    if raw_qty is None:
        raise ValueError("Quantity cannot be None")
    try:
        val = float(str(raw_qty).strip().replace(",", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Cannot parse quantity from '{raw_qty}': {exc}") from exc

    if math.isnan(val) or math.isinf(val) or val <= 0.0:
        raise ValueError(f"Invalid quantity value: {raw_qty} (parsed as {val})")
    return val


def infer_price_decimals(price: float) -> int:
    """
    Dynamically infer required decimal precision based on price magnitude so fractional
    and sub-₹1 assets (e.g. 0.0034, 0.000008, 0.16) never lose significant digits.
    """
    if price >= 1000.0:
        return 2
    elif price >= 100.0:
        return 2
    elif price >= 1.0:
        return 4
    elif price >= 0.01:
        return 6
    elif price >= 0.0001:
        return 8
    elif price >= 0.000001:
        return 10
    return 12


def infer_lot_decimals(price: float) -> int:
    """
    Dynamically infer quantity step decimals based on asset price magnitude.
    """
    if price >= 10000.0:
        return 5
    elif price >= 1000.0:
        return 4
    elif price >= 10.0:
        return 2
    elif price >= 1.0:
        return 1
    elif price >= 0.01:
        return 0
    elif price >= 0.0001:
        return -2  # Step size: 100 units
    return -3      # Step size: 1000 units


def get_pair_spec(pair: str, reference_price: Optional[float] = None) -> PairPrecisionSpec:
    """
    Normalize and look up pair precision specifications.
    For unknown / dynamic pairs, precision is dynamically scaled to the reference price
    so sub-₹1 prices are NEVER truncated to an unsafe 2-decimal limit.
    """
    clean_pair = pair.upper().replace("_", "/").replace("B-", "").replace("-", "/")
    if "/" not in clean_pair:
        clean_pair = f"{clean_pair}/INR"

    if clean_pair in PRECISION_TABLE:
        return PRECISION_TABLE[clean_pair]

    base_coin = clean_pair.split("/")[0]
    quote = clean_pair.split("/")[1] if "/" in clean_pair else "INR"
    is_usdt = (quote == "USDT")
    pair_key = f"{base_coin}/{quote}"

    if pair_key in PRECISION_TABLE:
        return PRECISION_TABLE[pair_key]

    if reference_price is not None and reference_price > 0:
        p_dec = infer_price_decimals(reference_price)
        lot_dec = infer_lot_decimals(reference_price)
        min_lot = 10 ** (-lot_dec) if lot_dec > 0 else (10 ** abs(lot_dec) if lot_dec < 0 else 1.0)
        return PairPrecisionSpec(
            pair=pair_key,
            base_price=reference_price,
            price_decimals=p_dec,
            lot_step_decimals=lot_dec,
            min_lot_qty=min_lot,
            min_notional_inr=200.0,
            min_notional_usdt=1.0,
            quote_currency=quote,
        )

    if is_usdt:
        return PairPrecisionSpec(
            pair=pair_key,
            base_price=1.0,
            price_decimals=6,
            lot_step_decimals=4,
            min_lot_qty=0.0001,
            min_notional_inr=200.0,
            min_notional_usdt=1.0,
            quote_currency="USDT",
        )

    return PairPrecisionSpec(
        pair=pair_key,
        base_price=100.0,
        price_decimals=8,
        lot_step_decimals=4,
        min_lot_qty=0.0001,
        min_notional_inr=200.0,
        min_notional_usdt=1.0,
        quote_currency="INR",
    )


def round_price(pair: str, price: float) -> float:
    """
    Round price according to pair tick precision.
    Guarantees that a strictly positive fractional price is NEVER rounded down to 0.0.
    """
    if price <= 0.0 or math.isnan(price) or math.isinf(price):
        return 0.0

    spec = get_pair_spec(pair, reference_price=price)
    required_decimals = max(spec.price_decimals, infer_price_decimals(price))
    res = float(round(price, required_decimals))

    # Defense: If rounding produced 0.0 on a positive price, expand precision
    if res == 0.0 and price > 0.0:
        for extra in range(required_decimals + 1, 14):
            res = float(round(price, extra))
            if res > 0.0:
                break
        if res == 0.0:
            res = float(price)

    return res


def round_qty(pair: str, qty: float) -> float:
    """Round lot quantity down to pair step size (roundp)."""
    if qty <= 0 or math.isnan(qty) or math.isinf(qty):
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

    # If step size floored a small positive micro-order to 0.0, preserve precision up to 8 decimals
    if res == 0.0 and qty > 0:
        res = float(math.floor(qty * 100_000_000) / 100_000_000)
    if res == 0.0 and qty > 0:
        res = float(qty)

    return res


# Alias for explicit clarity
round_qty_down = round_qty


def round_qty_up(pair: str, qty: float) -> float:
    """Round lot quantity UP to pair step size (ceil)."""
    if qty <= 0 or math.isnan(qty) or math.isinf(qty):
        return 0.0

    spec = get_pair_spec(pair)
    if spec.lot_step_decimals < 0:
        step = 10 ** abs(spec.lot_step_decimals)
        res = float(math.ceil(qty / step) * step)
    elif spec.lot_step_decimals == 0:
        res = float(math.ceil(qty))
    else:
        factor = 10 ** spec.lot_step_decimals
        res = float(math.ceil(qty * factor) / factor)

    if res == 0.0 and qty > 0:
        res = float(math.ceil(qty * 100_000_000) / 100_000_000)
    if res == 0.0 and qty > 0:
        res = float(qty)

    return res


def validate_order_notional(
    pair: str,
    price: float,
    qty: float,
    min_notional: Optional[float] = None,
    usdt_inr_rate: float = 91.50,
) -> bool:
    """
    Validate that the order meets both minimum lot size and minimum order value (₹200 or USDT equivalent).
    """
    if price <= 0.0 or qty <= 0.0 or math.isnan(price) or math.isnan(qty) or math.isinf(price) or math.isinf(qty):
        return False

    spec = get_pair_spec(pair, reference_price=price)
    notional = price * qty
    is_usdt = pair.upper().endswith("/USDT") or pair.upper().endswith("USDT")
    
    if min_notional is not None:
        min_val = min_notional
    else:
        min_val = spec.min_notional_usdt if is_usdt else spec.min_notional_inr

    # If pair is USDT and min_val is given in INR (e.g. 200.0), convert to USDT equivalent
    if is_usdt and min_val >= 50.0:
        min_val = min_val / usdt_inr_rate

    return (qty >= spec.min_lot_qty - 1e-9) and (round(notional, 2) >= round(min_val, 2))


def validate_trade_parameters(
    pair: str,
    price: float,
    qty: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    is_long: bool = True,
    min_notional: float = 200.0,
    usdt_inr_rate: float = 91.50,
) -> tuple[bool, Optional[str]]:
    """
    Hard pre-execution validation gate.
    Verifies price, quantity, notional, TP/SL integrity, and mathematical consistency.
    """
    # 1. Price validation
    if price is None or price <= 0.0 or math.isnan(price) or math.isinf(price):
        return False, f"Invalid entry price: {price}"

    # 2. Quantity validation
    if qty is None or qty <= 0.0 or math.isnan(qty) or math.isinf(qty):
        return False, f"Invalid quantity: {qty}"

    # 3. Notional validation
    notional = price * qty
    is_usdt = pair.upper().endswith("/USDT") or pair.upper().endswith("USDT")
    min_val = (min_notional / usdt_inr_rate) if is_usdt and min_notional >= 50.0 else min_notional
    if notional < min_val * 0.99:
        return False, f"Notional {notional:.4f} is below minimum {min_val:.2f}"

    # 4. Stop Loss validation
    if stop_loss is not None:
        if stop_loss <= 0.0 or math.isnan(stop_loss) or math.isinf(stop_loss):
            return False, f"Invalid stop loss: {stop_loss}"
        if is_long and stop_loss >= price:
            return False, f"Long stop loss {stop_loss} must be strictly below entry price {price}"
        if not is_long and stop_loss <= price:
            return False, f"Short stop loss {stop_loss} must be strictly above entry price {price}"
        ratio_sl = stop_loss / price
        if ratio_sl < 0.2 or ratio_sl > 5.0:
            return False, f"Stop loss {stop_loss} magnitude is inconsistent with entry {price} (ratio: {ratio_sl:.2f})"

    # 5. Take Profit validation
    if take_profit is not None:
        if take_profit <= 0.0 or math.isnan(take_profit) or math.isinf(take_profit):
            return False, f"Invalid take profit: {take_profit}"
        if is_long and take_profit <= price:
            return False, f"Long take profit {take_profit} must be strictly above entry price {price}"
        if not is_long and take_profit >= price:
            return False, f"Short take profit {take_profit} must be strictly below entry price {price}"
        ratio_tp = take_profit / price
        if ratio_tp < 0.2 or ratio_tp > 5.0:
            return False, f"Take profit {take_profit} magnitude is inconsistent with entry {price} (ratio: {ratio_tp:.2f})"

    return True, None


def extract_base_coin(sym: Optional[str]) -> str:
    """Normalize any symbol, pair, or CoinDCX ticker (e.g. 'B-ETH_INR', 'ETH/INR', 'ETHUSDT', 'ETH') to base coin 'ETH'."""
    if not sym:
        return ""
    s = str(sym).upper().strip()
    if s.startswith("B-"):
        s = s[2:]
    if "/" in s:
        s = s.split("/")[0]
    elif "_" in s:
        s = s.split("_")[0]
    elif s.endswith("INR") and len(s) > 3:
        s = s[:-3]
    elif s.endswith("USDT") and len(s) > 4:
        s = s[:-4]
    return s.strip()



