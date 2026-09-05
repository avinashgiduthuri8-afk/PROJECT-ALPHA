"""
V2 MarketContextService — Market Regime & Live Sentiment Tracker.

Polls macro bellwethers (BTC, ETH) and market sentiment feeds (Alternative.me Fear & Greed)
to dynamically evaluate overall crypto market regime (RISK_ON / RISK_OFF).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from v2.core.logging import get_logger

logger = get_logger("v2.services.scanner_service.market_context")


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average (EMA) for a price series."""
    if not prices or len(prices) < period:
        return []
    multiplier = 2.0 / (period + 1)
    # Start with Simple Moving Average of first 'period' elements
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema


def determine_trend_from_candles(candles: List[Dict[str, Any]]) -> str:
    """
    Determine trend (BULLISH, BEARISH, SIDEWAYS) using Fast EMA(9) and Slow EMA(21).
    Candles must be ordered chronologically (oldest first).
    """
    if not candles or len(candles) < 21:
        return "SIDEWAYS"

    closes: List[float] = []
    for c in candles:
        val = c.get("close", c.get("c", c.get("price", 0.0)))
        try:
            closes.append(float(val))
        except (ValueError, TypeError):
            continue

    if len(closes) < 21:
        return "SIDEWAYS"

    ema9_series = calculate_ema(closes, 9)
    ema21_series = calculate_ema(closes, 21)

    if not ema9_series or not ema21_series:
        return "SIDEWAYS"

    ema9 = ema9_series[-1]
    ema21 = ema21_series[-1]
    current_close = closes[-1]

    # Percent difference between EMA9 and EMA21
    diff_pct = (ema9 - ema21) / ema21 if ema21 > 0 else 0.0

    if diff_pct > 0.0015 and current_close >= ema9:
        return "BULLISH"
    elif diff_pct < -0.0015 and current_close <= ema9:
        return "BEARISH"
    return "SIDEWAYS"


class MarketContextService:
    """
    Asynchronously tracks macro crypto market context, including:
      - BTC Trend (Fast EMA9 vs Slow EMA21)
      - ETH Trend (Fast EMA9 vs Slow EMA21)
      - Market Regime (RISK_ON vs RISK_OFF)
      - Fear & Greed Index (0-100)
    """

    def __init__(self, timeout_seconds: float = 6.0) -> None:
        self._timeout = timeout_seconds
        self._latest_context: Dict[str, Any] = {
            "btc_trend": "BULLISH",
            "eth_trend": "BULLISH",
            "market_regime": "RISK_ON",
            "fear_and_greed": 50,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "btc_price": 0.0,
            "eth_price": 0.0,
        }
        self._last_refresh_at: Optional[datetime] = None

    def evaluate_regime(
        self,
        btc_candles: List[Dict[str, Any]],
        eth_candles: List[Dict[str, Any]],
    ) -> Tuple[str, str, str]:
        """
        Evaluate BTC trend, ETH trend, and combined Market Regime.
        Returns: (btc_trend, eth_trend, market_regime)
        """
        btc_trend = determine_trend_from_candles(btc_candles)
        eth_trend = determine_trend_from_candles(eth_candles)

        if btc_trend == "BEARISH":
            market_regime = "RISK_OFF"
        elif btc_trend == "BULLISH":
            market_regime = "RISK_ON"
        else:  # btc_trend == "SIDEWAYS"
            # If BTC is sideways but ETH is bullish or momentum is positive, permit RISK_ON
            if eth_trend == "BULLISH":
                market_regime = "RISK_ON"
            else:
                # Check recent 2-bar momentum for BTC
                if len(btc_candles) >= 2:
                    c1 = float(btc_candles[-1].get("close", btc_candles[-1].get("c", 0.0)) or 0.0)
                    c0 = float(btc_candles[-2].get("close", btc_candles[-2].get("c", 0.0)) or 0.0)
                    market_regime = "RISK_ON" if c1 >= c0 else "RISK_OFF"
                else:
                    market_regime = "RISK_ON"

        return btc_trend, eth_trend, market_regime

    async def fetch_fear_and_greed(self) -> int:
        """
        Fetch Alternative.me Fear & Greed Index (0-100).
        Falls back to neutral 50 on error or timeout.
        """
        url = "https://api.alternative.me/fng/?limit=1"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", [])
                if items and "value" in items[0]:
                    return int(items[0]["value"])
        except Exception as exc:
            logger.warning("Failed to fetch Fear & Greed index, falling back to neutral 50: %s", exc)
        return 50

    async def fetch_pair_candles(self, pair: str, interval: str = "15m", limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch raw candles for a pair directly from CoinDCX API."""
        url = "https://public.coindcx.com/market_data/candles"
        params = {"pair": pair, "interval": interval, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    # Sort ascending by timestamp if time field present
                    def _get_ts(c: Dict[str, Any]) -> int:
                        return int(c.get("time", c.get("t", 0)) or 0)
                    return sorted(data, key=_get_ts)
        except Exception as exc:
            logger.debug("Failed to fetch candles for %s: %s", pair, exc)
        return []

    async def refresh_market_context(self) -> Dict[str, Any]:
        """
        Poll live exchange endpoints for BTC & ETH + sentiment index.
        Updates internal cache and returns fresh payload.
        """
        try:
            # 1. Fetch BTC & ETH candles concurrently
            btc_task = self.fetch_pair_candles("B-BTC_USDT", interval="15m", limit=30)
            eth_task = self.fetch_pair_candles("B-ETH_USDT", interval="15m", limit=30)
            fng_task = self.fetch_fear_and_greed()

            btc_candles, eth_candles, fng_index = await asyncio.gather(
                btc_task, eth_task, fng_task, return_exceptions=True
            )

            # Handle possible gather exceptions
            btc_data = btc_candles if isinstance(btc_candles, list) else []
            eth_data = eth_candles if isinstance(eth_candles, list) else []
            fng_val = fng_index if isinstance(fng_index, int) else 50

            # Fallback to INR pairs if USDT candles returned empty
            if not btc_data:
                btc_data = await self.fetch_pair_candles("B-BTC_INR", interval="15m", limit=30)
            if not eth_data:
                eth_data = await self.fetch_pair_candles("B-ETH_INR", interval="15m", limit=30)

            btc_trend, eth_trend, regime = self.evaluate_regime(btc_data, eth_data)

            btc_price = float(btc_data[-1].get("close", btc_data[-1].get("c", 0.0))) if btc_data else 0.0
            eth_price = float(eth_data[-1].get("close", eth_data[-1].get("c", 0.0))) if eth_data else 0.0

            self._latest_context = {
                "btc_trend": btc_trend,
                "eth_trend": eth_trend,
                "market_regime": regime,
                "fear_and_greed": fng_val,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "btc_price": btc_price,
                "eth_price": eth_price,
            }
            self._last_refresh_at = datetime.now(timezone.utc)
            logger.info(
                "Market context refreshed: BTC=%s, ETH=%s, Regime=%s, F&G=%d",
                btc_trend, eth_trend, regime, fng_val
            )
        except Exception as exc:
            logger.exception("Error during market context refresh: %s", exc)

        return self._latest_context

    def get_current_sentiment(self) -> Dict[str, Any]:
        """Return the current cached market sentiment context."""
        return self._latest_context
