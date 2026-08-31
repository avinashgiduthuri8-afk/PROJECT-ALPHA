"""
Public Market Data Ingestion Feeder.

Continuously polls and streams live candle updates, ticker prices, and depth
for the active scanning universe, caching in memory and persisting to CandleRepository.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.logging import get_logger
from v2.repository.candle_repo import CandleRepository

from .public_client import CoinDCXPublicClient

logger = get_logger("v2.market.feeder")

DEFAULT_PAIRS = [
    "BTC/INR",
    "ETH/INR",
    "SOL/INR",
    "AVAX/INR",
    "LINK/INR",
    "DOGE/INR",
    "SHIB/INR",
    "MATIC/INR",
]

DEFAULT_INTERVALS = ["5m", "15m", "1h"]


class MarketFeeder:
    """Orchestrates public market data ingestion and real-time cache updating."""

    def __init__(
        self,
        client: Optional[CoinDCXPublicClient] = None,
        candle_repo: Optional[CandleRepository] = None,
        bus: Optional[EventBus] = None,
        pairs: Optional[list[str]] = None,
        intervals: Optional[list[str]] = None,
        poll_interval: float = 15.0,
    ) -> None:
        self._client = client or CoinDCXPublicClient()
        self._candle_repo = candle_repo
        self._bus = bus
        self._pairs = [p.upper() for p in (pairs or DEFAULT_PAIRS)]
        self._intervals = intervals or DEFAULT_INTERVALS
        self._poll_interval = poll_interval

        self._candle_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._ticker_cache: dict[str, dict[str, Any]] = {}
        self._orderbook_cache: dict[str, dict[str, Any]] = {}

        self._running = False
        self._feeder_task: Optional[asyncio.Task] = None
        self._last_poll_time: Optional[float] = None
        self._total_polls = 0
        self._total_errors = 0

    @property
    def client(self) -> CoinDCXPublicClient:
        return self._client

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._feeder_task = asyncio.create_task(self._feeder_loop())
        logger.info(
            "MarketFeeder started",
            extra={"pairs": self._pairs, "intervals": self._intervals, "interval_sec": self._poll_interval},
        )

    async def stop(self) -> None:
        self._running = False
        if self._feeder_task:
            self._feeder_task.cancel()
            try:
                await self._feeder_task
            except asyncio.CancelledError:
                pass
            self._feeder_task = None

        await self._client.close()
        logger.info("MarketFeeder stopped")

    # ── Feeder Loop ───────────────────────────────────────────────────────────

    async def _feeder_loop(self) -> None:
        while self._running:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._total_errors += 1
                logger.warning("Error in market feeder cycle", extra={"error": str(exc)})

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def poll_once(self) -> dict[str, Any]:
        """Execute a single market data polling and synchronization cycle."""
        self._total_polls += 1
        self._last_poll_time = time.time()

        # 1. Fetch live 24h tickers
        try:
            tickers = await self._client.get_tickers()
            for t in tickers:
                m = t.get("market", "")
                self._ticker_cache[m] = t
                # Also index by standard pair notation (e.g. BTCINR, BTC/INR)
                if m.endswith("INR"):
                    base = m[:-3]
                    self._ticker_cache[f"{base}/INR"] = t
                elif m.endswith("USDT"):
                    base = m[:-4]
                    self._ticker_cache[f"{base}/USDT"] = t
        except Exception as exc:
            logger.warning("Failed to fetch tickers in poll cycle", extra={"error": str(exc)})

        # 2. Fetch candles for all active pairs & intervals
        updated_counts = 0
        for pair in self._pairs:
            for interval in self._intervals:
                try:
                    candles = await self._client.get_candles(pair=pair, interval=interval, limit=120)
                    if candles:
                        self._candle_cache[(pair, interval)] = candles
                        updated_counts += len(candles)

                        # Idempotent write to CandleRepository if configured
                        if self._candle_repo:
                            await self._candle_repo.upsert_candles(candles)
                except Exception as exc:
                    logger.debug("Failed to pull candles for pair", extra={"pair": pair, "interval": interval, "error": str(exc)})

        # 3. Publish MARKET_DATA_UPDATED event over EventBus
        summary = {
            "timestamp": int(self._last_poll_time),
            "updated_pairs": len(self._pairs),
            "total_candles_updated": updated_counts,
            "sample_prices": {p: self.get_latest_price(p) for p in self._pairs[:4]},
        }

        if self._bus:
            await self._bus.publish(EventType.MARKET_DATA_UPDATED, summary)

        return summary

    # ── Read Accessors ────────────────────────────────────────────────────────

    def get_latest_price(self, pair: str) -> Optional[float]:
        """Get latest price from ticker cache or most recent candle."""
        pair_clean = pair.upper()
        if pair_clean in self._ticker_cache:
            return float(self._ticker_cache[pair_clean].get("last_price") or 0.0)

        # Fallback to most recent candle close across cached intervals
        for interval in ["5m", "15m", "1h"]:
            candles = self._candle_cache.get((pair_clean, interval))
            if candles:
                return float(candles[-1].get("close") or 0.0)

        return None

    def get_cached_candles(self, pair: str, timeframe: str) -> list[dict[str, Any]]:
        """Retrieve in-memory cached candles for instant signal calculation."""
        return self._candle_cache.get((pair.upper(), timeframe), [])

    async def fetch_orderbook(self, pair: str) -> dict[str, Any]:
        """Fetch and cache top-of-book depth."""
        ob = await self._client.get_orderbook(pair)
        self._orderbook_cache[pair.upper()] = ob
        if self._bus:
            await self._bus.publish(EventType.ORDERBOOK_UPDATED, ob)
        return ob

    def get_cached_orderbook(self, pair: str) -> Optional[dict[str, Any]]:
        return self._orderbook_cache.get(pair.upper())

    def get_health(self) -> dict[str, Any]:
        return {
            "healthy": self._running,
            "total_polls": self._total_polls,
            "total_errors": self._total_errors,
            "last_poll_at": self._last_poll_time,
            "tracked_pairs": len(self._pairs),
            "cached_intervals": len(self._candle_cache),
        }
