"""
CoinDCX Public REST Market Data Client.

Provides zero-credential access to live tickers, historical OHLCV candles,
and top-of-book depth with strict token-bucket rate limiting (8 req/s) and
exponential backoff retry resilience.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from v2.core.logging import get_logger

logger = get_logger("v2.market.public_client")


class TokenBucketRateLimiter:
    """Token bucket rate limiter ensuring strictly <= max_rate_per_sec requests."""

    def __init__(self, max_rate_per_sec: float = 8.0, burst: int = 8) -> None:
        self._max_rate = max_rate_per_sec
        self._capacity = burst
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now
            self._tokens = min(self._capacity, self._tokens + elapsed * self._max_rate)

            if self._tokens < 1.0:
                needed = (1.0 - self._tokens) / self._max_rate
                await asyncio.sleep(needed)
                self._tokens = 0.0
                self._last_update = time.monotonic()
            else:
                self._tokens -= 1.0


class CoinDCXPublicClient:
    """Asynchronous client for public CoinDCX market data."""

    BASE_URL_EXCHANGE = "https://api.coindcx.com"
    BASE_URL_PUBLIC   = "https://public.coindcx.com"

    def __init__(
        self,
        timeout: float = 10.0,
        rate_limit_per_sec: float = 8.0,
        max_retries: int = 3,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._rate_limiter = TokenBucketRateLimiter(max_rate_per_sec=rate_limit_per_sec)
        self._semaphore = asyncio.Semaphore(int(rate_limit_per_sec))
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "CoinDCXPublicClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # ── Pair Formatting Helper ────────────────────────────────────────────────

    @staticmethod
    def format_pair(pair: str) -> str:
        """
        Normalize trading pair to CoinDCX format.
        Examples:
          'BTC/INR'  -> 'B-BTC_INR'
          'BTCINR'   -> 'B-BTC_INR'
          'ETH/USDT' -> 'B-ETH_USDT'
          'B-BTC_INR'-> 'B-BTC_INR'
        """
        pair_clean = pair.strip().upper()
        if pair_clean.startswith("B-") or pair_clean.startswith("I-"):
            return pair_clean

        if "/" in pair_clean:
            base, quote = pair_clean.split("/", 1)
            return f"B-{base}_{quote}"

        for quote in ["USDT", "INR", "BTC", "ETH"]:
            if pair_clean.endswith(quote) and len(pair_clean) > len(quote):
                base = pair_clean[: -len(quote)]
                return f"B-{base}_{quote}"

        return f"B-{pair_clean}"

    # ── HTTP Request with Rate Limiting & Retry ───────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        client = self._get_client()

        for attempt in range(self._max_retries + 1):
            await self._rate_limiter.acquire()
            async with self._semaphore:
                try:
                    resp = await client.request(method, url, params=params)
                    
                    if resp.status_code == 200:
                        return resp.json()

                    # Handle Rate Limit (429) or Server Errors (5xx)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        if attempt == self._max_retries:
                            resp.raise_for_status()
                        backoff = 1.0 * (attempt + 1)
                        logger.warning(
                            "CoinDCX API temporary response, retrying",
                            extra={"status": resp.status_code, "attempt": attempt + 1, "backoff": backoff},
                        )
                        await asyncio.sleep(backoff)
                        continue

                    resp.raise_for_status()

                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == self._max_retries:
                        logger.error("CoinDCX API request failed after retries", extra={"url": url, "error": str(exc)})
                        raise
                    backoff = 1.0 * (attempt + 1)
                    logger.warning(
                        "CoinDCX connection error, retrying",
                        extra={"error": str(exc), "attempt": attempt + 1, "backoff": backoff},
                    )
                    await asyncio.sleep(backoff)

        raise httpx.HTTPError(f"Request failed to {url} after {self._max_retries} retries")

    # ── Public Endpoints ──────────────────────────────────────────────────────

    async def get_tickers(self) -> list[dict[str, Any]]:
        """
        Fetch 24-hour ticker statistics across all CoinDCX markets.
        GET https://api.coindcx.com/exchange/ticker
        """
        url = f"{self.BASE_URL_EXCHANGE}/exchange/ticker"
        raw_data = await self._request("GET", url)

        if not isinstance(raw_data, list):
            logger.warning("Unexpected tickers payload shape", extra={"type": type(raw_data).__name__})
            return []

        tickers = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            market = item.get("market", "")
            last_price = float(item.get("last_price") or 0.0)
            bid = float(item.get("bid") or last_price)
            ask = float(item.get("ask") or last_price)
            high = float(item.get("high") or 0.0)
            low = float(item.get("low") or 0.0)
            volume = float(item.get("volume") or 0.0)
            change_24h = float(item.get("change_24_hour") or 0.0)
            timestamp = int(item.get("timestamp") or time.time())

            tickers.append({
                "market": market,
                "last_price": last_price,
                "bid": bid,
                "ask": ask,
                "high": high,
                "low": low,
                "volume": volume,
                "change_24_hour": change_24h,
                "timestamp": timestamp,
            })

        return tickers

    async def get_candles(
        self,
        pair: str,
        interval: str = "15m",
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        """
        Fetch historical OHLCV candlestick bars.
        GET https://public.coindcx.com/market_data/candles
        Returns list of candles sorted chronologically (oldest -> newest).
        """
        formatted_pair = self.format_pair(pair)
        url = f"{self.BASE_URL_PUBLIC}/market_data/candles"
        params = {
            "pair": formatted_pair,
            "interval": interval,
            "limit": limit,
        }

        raw_data = await self._request("GET", url, params=params)

        if not isinstance(raw_data, list):
            logger.warning("Unexpected candles payload shape", extra={"pair": pair, "type": type(raw_data).__name__})
            return []

        candles = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue

            # Parse open, high, low, close, volume, timestamp
            o = float(item.get("open") or item.get("o") or 0.0)
            h = float(item.get("high") or item.get("h") or 0.0)
            l = float(item.get("low")  or item.get("l") or 0.0)
            c = float(item.get("close") or item.get("c") or 0.0)
            v = float(item.get("volume") or item.get("v") or 0.0)

            raw_time = item.get("time") or item.get("t") or item.get("timestamp") or 0
            # Normalize to epoch seconds
            ts = int(raw_time)
            if ts > 10000000000:  # If millisecond timestamp
                ts = ts // 1000

            candles.append({
                "pair": pair.upper(),
                "timeframe": interval,
                "timestamp": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            })

        # Ensure sorted chronologically ascending (oldest -> newest)
        candles.sort(key=lambda x: x["timestamp"])
        return candles

    async def get_orderbook(self, pair: str) -> dict[str, Any]:
        """
        Fetch top-of-book depth for spread and slippage evaluation.
        GET https://public.coindcx.com/market_data/orderbook
        """
        formatted_pair = self.format_pair(pair)
        url = f"{self.BASE_URL_PUBLIC}/market_data/orderbook"
        params = {"pair": formatted_pair}

        raw_data = await self._request("GET", url, params=params)

        if not isinstance(raw_data, dict):
            return {
                "pair": pair.upper(),
                "bids": {},
                "asks": {},
                "best_bid": 0.0,
                "best_ask": 0.0,
                "spread": 0.0,
                "spread_pct": 0.0,
                "timestamp": int(time.time()),
            }

        bids = raw_data.get("bids") or {}
        asks = raw_data.get("asks") or {}

        # Extract top bids and asks
        best_bid = 0.0
        best_ask = 0.0

        if isinstance(bids, dict) and bids:
            best_bid = max(float(p) for p in bids.keys())
        elif isinstance(bids, list) and bids:
            best_bid = float(bids[0][0] if isinstance(bids[0], list) else bids[0])

        if isinstance(asks, dict) and asks:
            best_ask = min(float(p) for p in asks.keys())
        elif isinstance(asks, list) and asks:
            best_ask = float(asks[0][0] if isinstance(asks[0], list) else asks[0])

        spread = max(0.0, best_ask - best_bid) if (best_ask > 0 and best_bid > 0) else 0.0
        mid = (best_ask + best_bid) / 2.0 if (best_ask > 0 and best_bid > 0) else 1.0
        spread_pct = (spread / mid) * 100.0 if mid > 0 else 0.0

        return {
            "pair": pair.upper(),
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": round(spread, 4),
            "spread_pct": round(spread_pct, 4),
            "timestamp": int(time.time()),
        }
