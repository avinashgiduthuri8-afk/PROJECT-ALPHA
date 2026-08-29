"""
Multi-Timeframe OHLCV Data Feeder for PROJECT-ALPHA Backtesting Engine.

Supports CoinDCX INR pairs with mixed-value price tiers and realistic order rounding:
  - Mega-Cap / High Value: BTC/INR, ETH/INR, BNB/INR
  - Mid-Cap / Medium Value: SOL/INR, AVAX/INR, LINK/INR
  - Low-Value / Fractional: XRP/INR, ADA/INR, MATIC/INR, DOGE/INR, TRX/INR, SHIB/INR
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class PairSpec:
    pair: str
    base_price: float
    volatility: float
    price_precision: int       # Decimals for price rounding (e.g. 2 for ₹100.25, 6 for ₹0.001824)
    qty_precision: int         # Decimals for lot quantity rounding (e.g. 5 for BTC, 0 for DOGE)
    min_qty: float             # Minimum tradeable lot size
    min_notional_inr: float = 100.0  # Minimum order notional in INR (CoinDCX standard: ₹100)


COINDCX_INR_PAIRS: Dict[str, PairSpec] = {
    # ── Tier 1: Mega-Cap / High-Value Coins ──────────────────────────────────
    "BTC/INR": PairSpec("BTC/INR", base_price=8200000.0, volatility=0.015, price_precision=2, qty_precision=5, min_qty=0.00001),
    "ETH/INR": PairSpec("ETH/INR", base_price=260000.0, volatility=0.020, price_precision=2, qty_precision=4, min_qty=0.0001),
    "BNB/INR": PairSpec("BNB/INR", base_price=52000.0, volatility=0.022, price_precision=1, qty_precision=3, min_qty=0.001),

    # ── Tier 2: Mid-Cap / Medium-Value Coins ─────────────────────────────────
    "SOL/INR": PairSpec("SOL/INR", base_price=12500.0, volatility=0.035, price_precision=1, qty_precision=2, min_qty=0.01),
    "AVAX/INR": PairSpec("AVAX/INR", base_price=2800.0, volatility=0.038, price_precision=1, qty_precision=2, min_qty=0.01),
    "LINK/INR": PairSpec("LINK/INR", base_price=1400.0, volatility=0.032, price_precision=1, qty_precision=2, min_qty=0.01),

    # ── Tier 3: Low-Price & Fractional Coins ─────────────────────────────────
    "XRP/INR": PairSpec("XRP/INR", base_price=110.0, volatility=0.030, price_precision=2, qty_precision=1, min_qty=0.1),
    "ADA/INR": PairSpec("ADA/INR", base_price=65.0, volatility=0.035, price_precision=2, qty_precision=1, min_qty=0.1),
    "MATIC/INR": PairSpec("MATIC/INR", base_price=48.0, volatility=0.040, price_precision=2, qty_precision=1, min_qty=0.1),
    "DOGE/INR": PairSpec("DOGE/INR", base_price=16.50, volatility=0.050, price_precision=3, qty_precision=0, min_qty=1.0),
    "TRX/INR": PairSpec("TRX/INR", base_price=18.00, volatility=0.028, price_precision=3, qty_precision=0, min_qty=1.0),
    "SHIB/INR": PairSpec("SHIB/INR", base_price=0.0018, volatility=0.060, price_precision=6, qty_precision=-3, min_qty=1000.0),
}


# Default fallback for any unlisted pair
DEFAULT_PAIR_SPEC = PairSpec("CUSTOM/INR", base_price=100.0, volatility=0.025, price_precision=2, qty_precision=2, min_qty=0.1)


def get_pair_spec(pair: str) -> PairSpec:
    """Lookup pair specification and precision parameters."""
    normalized = pair.replace("_", "/").upper()
    return COINDCX_INR_PAIRS.get(normalized, DEFAULT_PAIR_SPEC)


def round_price(pair: str, price: float) -> float:
    """Round price according to pair tick precision."""
    spec = get_pair_spec(pair)
    if spec.price_precision <= 0:
        return round(price)
    return round(price, spec.price_precision)


def round_qty(pair: str, qty: float) -> float:
    """Round lot quantity down according to pair step precision."""
    spec = get_pair_spec(pair)
    if spec.qty_precision < 0:
        # Step size is greater than 1 (e.g. SHIB step size = 1000)
        step = 10 ** abs(spec.qty_precision)
        return float(math.floor(qty / step) * step)
    elif spec.qty_precision == 0:
        return float(math.floor(qty))
    else:
        factor = 10 ** spec.qty_precision
        return float(math.floor(qty * factor) / factor)


class DataFeeder:
    """Provides historical/synthetic OHLCV dataframes with technical indicators pre-computed."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self._cache: Dict[str, pd.DataFrame] = {}

    def generate_ohlcv_dataframe(
        self,
        pair: str = "BTC/INR",
        timeframe: str = "1H",
        sessions: int = 300,
    ) -> pd.DataFrame:
        """
        Generate a multi-session OHLCV dataframe with realistic price action,
        volume spikes, and technical indicators for backtesting.
        """
        spec = get_pair_spec(pair)
        cache_key = f"{spec.pair}_{timeframe}_{sessions}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        np.random.seed(self.seed + hash(pair) % 1000)

        base_price = spec.base_price
        daily_vol = spec.volatility

        tf_minutes = {"15M": 15, "1H": 60, "4H": 240}.get(timeframe, 60)
        num_bars = sessions * (1440 // tf_minutes)  # Total bars across 250+ sessions

        start_time = datetime.now(timezone.utc) - timedelta(minutes=num_bars * tf_minutes)
        timestamps = [start_time + timedelta(minutes=i * tf_minutes) for i in range(num_bars)]

        # Geometric Brownian Motion + Volatility Regimes (Trend, Pullback, Squeeze)
        returns = np.random.normal(loc=0.0001, scale=daily_vol / np.sqrt(1440 / tf_minutes), size=num_bars)
        
        # Add cyclical trend/regime shifts
        cycles = np.sin(np.linspace(0, 12 * np.pi, num_bars)) * 0.002
        returns += cycles

        prices = base_price * np.exp(np.cumsum(returns))

        # Construct High, Low, Open, Close with realistic noise
        high_noise = np.abs(np.random.normal(0, daily_vol * 0.5, num_bars)) * prices
        low_noise = np.abs(np.random.normal(0, daily_vol * 0.5, num_bars)) * prices

        opens = np.roll(prices, 1)
        opens[0] = base_price
        closes = prices
        highs = np.maximum(opens, closes) + high_noise
        lows = np.minimum(opens, closes) - low_noise

        # Format with discrete price precision
        prec = max(0, spec.price_precision)
        opens = np.round(opens, prec)
        highs = np.round(highs, prec)
        lows = np.round(lows, prec)
        closes = np.round(closes, prec)

        base_vol = 10000000.0 / base_price
        volume = base_vol * (1.0 + np.abs(returns) * 50 + np.random.exponential(0.5, num_bars))

        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.round(volume, 2),
        })

        # Pre-compute core technical indicators for strategies
        df = self._add_technical_indicators(df)

        self._cache[cache_key] = df
        return df.copy()

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA 9, 21, 50, 200, MACD, RSI, ATR, Donchian, Bollinger Bands, SuperTrend, Keltner."""
        closes = df["close"]
        highs = df["high"]
        lows = df["low"]

        # EMAs
        df["ema_9"] = closes.ewm(span=9, adjust=False).mean()
        df["ema_21"] = closes.ewm(span=21, adjust=False).mean()
        df["ema_50"] = closes.ewm(span=50, adjust=False).mean()
        df["ema_200"] = closes.ewm(span=200, adjust=False).mean()

        # Volume EMA
        df["vol_ema_20"] = df["volume"].ewm(span=20, adjust=False).mean()
        df["rvol"] = df["volume"] / (df["vol_ema_20"] + 1e-9)

        # MACD
        ema_12 = closes.ewm(span=12, adjust=False).mean()
        ema_26 = closes.ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # RSI 14
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # ATR 14
        tr = np.maximum(
            highs - lows,
            np.maximum(
                (highs - closes.shift(1)).abs(),
                (lows - closes.shift(1)).abs(),
            ),
        )
        df["atr_14"] = pd.Series(tr).ewm(span=14, adjust=False).mean()

        # Donchian 20
        df["donchian_high_20"] = highs.rolling(20).max().shift(1)
        df["donchian_low_20"] = lows.rolling(20).min().shift(1)

        # Bollinger Bands (20, 2)
        sma_20 = closes.rolling(20).mean()
        std_20 = closes.rolling(20).std()
        df["bb_upper"] = sma_20 + (2.0 * std_20)
        df["bb_lower"] = sma_20 - (2.0 * std_20)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / (sma_20 + 1e-9)

        # Keltner Channels (20, 1.5 ATR)
        df["kc_upper"] = sma_20 + (1.5 * df["atr_14"])
        df["kc_lower"] = sma_20 - (1.5 * df["atr_14"])

        # VWAP
        tp = (highs + lows + closes) / 3.0
        df["vwap"] = (tp * df["volume"]).cumsum() / (df["volume"].cumsum() + 1e-9)

        # CVD (Cumulative Volume Delta estimate)
        candle_direction = np.sign(closes - df["open"])
        df["cvd"] = (candle_direction * df["volume"]).cumsum()

        # NR7 Flag (Narrow Range 7)
        candle_range = highs - lows
        df["candle_range"] = candle_range
        df["min_range_7"] = candle_range.rolling(7).min()
        df["is_nr7"] = candle_range == df["min_range_7"]

        return df
