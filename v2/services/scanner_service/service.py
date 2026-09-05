"""
V2 ScannerService.

Bridges the V1 scanner HTTP API and the V2 event bus.

Responsibilities:
  - Poll GET /api/v1/scanner/signals on the scheduler interval
  - Transform V1 response → V2 Signal domain objects via adapter
  - Deduplicate: only publish SIGNAL_GENERATED for new signals
  - Detect expiry: publish SIGNAL_EXPIRED when a live signal passes TTL
  - Persist all signals to SignalRepository
  - Expose get_live_signals() for the API layer
  - Report health status

No V1 imports — coupling is via HTTP only.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.types import MarketState, OppType, Priority, Signal
from v2.core.logging import get_logger
from v2.repository.signal_repo import SignalRepository
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.candle_repo import CandleRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository

from .adapter import v1_response_to_signals
from .confluence_engine import ConfluenceEngine
from .calibration_worker import CalibrationWorker
from .market_context import MarketContextService, calculate_ema
from .news_fetcher import NewsRiskService
from .signal_filter import (
    filter_by_priority, filter_live, deduplicate, detect_expired, _dedup_key,
)


logger = get_logger("v2.services.scanner_service")


class AsyncRateLimiter:
    """Token bucket rate limiter enforcing max N requests per second."""

    def __init__(self, max_rate: float = 8.0) -> None:
        self.max_rate = max_rate
        self._min_interval = 1.0 / max_rate
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_call = loop.time()


def canonical_to_coindcx_pair(pair: str) -> str:
    # "BTC/INR" -> "B-BTC_INR"
    base, quote = pair.upper().split("/")
    return f"B-{base}_{quote}"


class ScannerService:
    """
    Bridges V1 scanner → V2 event bus.

    Lifecycle:
        service = ScannerService(bus, signal_repo, event_log_repo, config)
        await service.start()         # subscribe handlers, called once at startup
        await service.poll()          # called by scheduler every N seconds
        await service.stop()          # unsubscribe, flush state
    """

    def __init__(
        self,
        bus: EventBus,
        signal_repo: SignalRepository,
        event_log_repo: EventLogRepository,
        config: V2Config,
        candle_repo: Optional[CandleRepository] = None,
        position_repo: Optional[PositionRepository] = None,
        trade_repo: Optional[TradeRepository] = None,
        market_context_service: Optional[MarketContextService] = None,
        news_risk_service: Optional[NewsRiskService] = None,
        calibration_worker: Optional[CalibrationWorker] = None,
    ) -> None:
        self._bus = bus
        self._signal_repo = signal_repo
        self._event_log = event_log_repo
        self._config = config
        self._candle_repo = candle_repo
        self._position_repo = position_repo
        self._trade_repo = trade_repo

        # Post-exit cooldown tracking {coin_symbol: {"exit_time": datetime, "exit_reason": str, "price": float}}
        self._cooldowns: dict[str, dict] = {}


        # Services for Macro Context, Sentiment, and News Risk
        self._market_context_service = market_context_service or MarketContextService()
        self._news_risk_service = news_risk_service or NewsRiskService(
            api_token=getattr(config, "cryptopanic_api_key", None)
        )
        self._rate_limiter = AsyncRateLimiter(max_rate=8.0)

        # In-memory live signal cache  {signal_id: Signal}
        self._live: dict[str, Signal] = {}
        # In-memory latest scan evaluated coins snapshot {symbol_or_pair: dict}
        self._latest_evaluated_coins: dict[str, dict] = {}
        # Dedup set — {coin::generated_at} for signals already seen this session
        self._seen_keys: set[str] = set()

        self._poll_count = 0
        self._last_poll_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._started = False

        self._min_priority = Priority(self._config.v2_scanner_min_priority)

        # C2 High-Conviction Confluence Engine (5-layer evaluation, strict rejection gate, max 1–2 signals)
        self._confluence_engine = ConfluenceEngine(
            strict_threshold=getattr(self._config, "v2_scanner_strict_confluence_threshold", 85),
            max_signals=getattr(self._config, "v2_scanner_max_signals", 2),
        )

        # Dynamic Win-Rate Feedback Calibration Worker
        self._calibration_worker = calibration_worker or CalibrationWorker(
            bus=bus,
            confluence_engine=self._confluence_engine,
        )

    @property
    def confluence_engine(self) -> ConfluenceEngine:
        return self._confluence_engine

    @property
    def market_context_service(self) -> MarketContextService:
        return self._market_context_service

    @property
    def news_risk_service(self) -> NewsRiskService:
        return self._news_risk_service

    @property
    def calibration_worker(self) -> CalibrationWorker:
        return self._calibration_worker

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe bus handlers. Called once at application startup."""
        if self._started:
            return
        self._started = True
        self._bus.subscribe(EventType.POSITION_CLOSED, self.on_position_closed)
        self._bus.subscribe(EventType.TRADE_EXECUTED, self.on_trade_executed)
        await self._bus.publish(
            EventType.SYSTEM_STARTUP,
            {"service": "scanner_service"},
        )
        logger.info("ScannerService started")

        # Bootstrap active post-exit cooldowns from recent closed trades
        if self._trade_repo:
            try:
                recent_trades = await self._trade_repo.get_recent(limit=30)
                now = datetime.now(timezone.utc)
                cooldown_dur = getattr(self._config, "v2_post_exit_cooldown_seconds", 900)
                for tr in recent_trades:
                    c_time = getattr(tr, "closed_at", None) or getattr(tr, "executed_at", None)
                    if c_time:
                        if c_time.tzinfo is None:
                            c_time = c_time.replace(tzinfo=timezone.utc)
                        if (now - c_time).total_seconds() < cooldown_dur:
                            coin_clean = (getattr(tr, "coin", "") or "").upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
                            if coin_clean and coin_clean not in self._cooldowns:
                                self._cooldowns[coin_clean] = {
                                    "exit_time": c_time,
                                    "exit_reason": getattr(tr, "exit_reason", "CLOSED"),
                                    "price": float(getattr(tr, "price", 0.0) or 0.0),
                                }
                if self._cooldowns:
                    logger.info("Bootstrapped %d active post-exit cooldowns: %s", len(self._cooldowns), list(self._cooldowns.keys()))
            except Exception as exc:
                logger.debug("Could not bootstrap post-exit cooldowns: %s", exc)

        # Start dynamic calibration worker
        await self._calibration_worker.start()

        # Database-first candle bootstrapping and periodic flushing
        if self._candle_repo:
            asyncio.create_task(self.bootstrap_candles())
            self._flusher_task = asyncio.create_task(self._candle_flusher_loop())

    async def stop(self) -> None:
        """Unsubscribe and flush in-memory state."""
        self._started = False
        self._bus.unsubscribe(EventType.POSITION_CLOSED, self.on_position_closed)
        self._bus.unsubscribe(EventType.TRADE_EXECUTED, self.on_trade_executed)
        self._live.clear()

        # Stop calibration worker
        await self._calibration_worker.stop()

        # Stop background flusher loop
        if hasattr(self, "_flusher_task") and self._flusher_task:
            self._flusher_task.cancel()
            try:
                await self._flusher_task
            except asyncio.CancelledError:
                pass
            self._flusher_task = None

        logger.info("ScannerService stopped")

    # ── Signal Lifecycle & Cooldown Handlers ──────────────────────────────────

    async def on_position_closed(self, event_type: EventType, payload: dict) -> None:
        """Record post-exit cooldown and invalidate any live signals for this coin."""
        coin = (payload.get("coin") or "").upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
        if not coin:
            return
        now = datetime.now(timezone.utc)
        exit_reason = payload.get("exit_reason", "CLOSED")
        exit_price = float(payload.get("exit_price") or payload.get("price") or 0.0)
        cooldown_dur = getattr(self._config, "v2_post_exit_cooldown_seconds", 900)
        self._cooldowns[coin] = {
            "exit_time": now,
            "exit_reason": exit_reason,
            "price": exit_price,
        }
        logger.info(
            "Post-exit cooldown started for %s (%s, duration: %ds)",
            coin, exit_reason, cooldown_dur
        )

        # Evict any active in-memory live signals for this coin
        to_evict = [sid for sid, sig in self._live.items() if sig.coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "") == coin]
        for sid in to_evict:
            sig = self._live.pop(sid, None)
            if sig:
                try:
                    await self._signal_repo.mark_expired(sid)
                except Exception:
                    pass

    async def on_trade_executed(self, event_type: EventType, payload: dict) -> None:
        """Mark signal consumed when trade executes."""
        signal_id = payload.get("signal_id")
        coin = (payload.get("coin") or "").upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
        if signal_id:
            self._live.pop(signal_id, None)
            try:
                await self._signal_repo.mark_consumed(signal_id)
            except Exception:
                pass
        # Also clean up any other live signals for this coin
        if coin:
            to_evict = [sid for sid, sig in self._live.items() if sig.coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "") == coin]
            for sid in to_evict:
                self._live.pop(sid, None)

    # ── Database-First Bootstrapping & Periodic Candle Cache Flushing ────────
    async def bootstrap_candles(self) -> None:
        """Database-first bootstrapping: warm up market_candles table for all watchlist coins."""
        logger.info("[Bootstrap] Starting database-first candle warm-up...")
        try:
            coins = await self._fetch_watchlist_coins()
            canonical_inr_coins = {
                "BTC", "ETH", "BNB", "SOL", "AVAX", "LINK", 
                "XRP", "ADA", "MATIC", "DOGE", "TRX", "SHIB", "POL"
            }
            
            pairs = []
            for coin in coins:
                coin_upper = coin.upper()
                quote = "INR" if coin_upper in canonical_inr_coins else "USDT"
                pairs.append(f"{coin_upper}/{quote}")

            for pair in pairs:
                for timeframe in ["15m", "1d"]:
                    try:
                        db_candles = await self._candle_repo.get_recent_candles(pair, timeframe, limit=120)
                        if len(db_candles) < 120:
                            logger.info(
                                "[Bootstrap] Insufficient cached candles for pair=%s timeframe=%s (%d/120). Catching up from exchange API...",
                                pair, timeframe, len(db_candles)
                            )
                            coindcx_pair = canonical_to_coindcx_pair(pair)
                            interval = "1d" if timeframe == "1d" else "15m"
                            raw_candles = await self._fetch_coindcx_candles(coindcx_pair, interval, limit=120)
                            
                            if raw_candles:
                                formatted = []
                                for c in raw_candles:
                                    try:
                                        ts_ms = int(c.get("time", c.get("t", 0)) or 0)
                                        close = float(c.get("close", c.get("c", 0.0)) or 0.0)
                                        if ts_ms <= 0 or close <= 0:
                                            continue
                                        formatted.append({
                                            "pair": pair,
                                            "timeframe": timeframe,
                                            "timestamp": ts_ms,
                                            "open": float(c.get("open", c.get("o", close))),
                                            "high": float(c.get("high", c.get("h", close))),
                                            "low": float(c.get("low", c.get("l", close))),
                                            "close": close,
                                            "volume": float(c.get("volume", c.get("v", 0.0))),
                                        })
                                    except (TypeError, ValueError, KeyError):
                                        continue
                                
                                if formatted:
                                    await self._candle_repo.upsert_candles(formatted)
                                    logger.info(
                                        "[Bootstrap] Idempotent upserted %d candles for pair=%s timeframe=%s",
                                        len(formatted), pair, timeframe
                                    )
                        else:
                            logger.info(
                                "[Bootstrap] Sufficient cached candles found in SQLite for pair=%s timeframe=%s (%d)",
                                pair, timeframe, len(db_candles)
                            )
                    except Exception as exc:
                        logger.warning(
                            "[Bootstrap] Failed to bootstrap candles for pair=%s timeframe=%s: %s",
                            pair, timeframe, exc
                        )
            logger.info("[Bootstrap] Database-first candle warm-up complete.")
        except Exception as exc:
            logger.exception("[Bootstrap] Critical failure during candle warm-up", extra={"error": str(exc)})

    async def _fetch_watchlist_coins(self) -> list[str]:
        """Fetch current watchlist coins from V1 scanner."""
        url = f"{self._config.v2_scanner_base_url}/watchlist"
        headers = {}
        if self._config.dashboard_api_key:
            headers["X-API-Key"] = self._config.dashboard_api_key

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and "coins" in data:
                    return data["coins"]
        except Exception as exc:
            logger.warning(
                "Failed to fetch watchlist from V1 scanner, falling back to defaults: %s",
                exc
            )
        
        # Default fallback
        return ["BTC", "ETH", "SOL", "BNB", "XRP", "ZEC"]

    async def _fetch_coindcx_candles(
        self, coindcx_pair: str, interval: str, limit: int = 120
    ) -> list[dict]:
        """Fetch candles directly from CoinDCX API with rate limit safety."""
        url = "https://public.coindcx.com/market_data/candles"
        params = {"pair": coindcx_pair, "interval": interval, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await asyncio.sleep(0.125)  # Enforce rate limiting safety (max 8 req/s)
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
        except Exception as exc:
            logger.debug(
                "Failed to fetch candles from CoinDCX for pair=%s: %s",
                coindcx_pair, exc
            )
        return []

    async def _candle_flusher_loop(self) -> None:
        """Background task to fetch latest closed candles from CoinDCX and flush to database."""
        logger.info("[Flusher] Background candle flusher loop started")
        while self._started:
            try:
                # Wait for the configured scanner poll interval
                await asyncio.sleep(self._config.v2_scanner_poll_interval)
                if not self._started:
                    break
                
                logger.info("[Flusher] Periodic candle flush cycle started")
                coins = await self._fetch_watchlist_coins()
                canonical_inr_coins = {
                    "BTC", "ETH", "BNB", "SOL", "AVAX", "LINK", 
                    "XRP", "ADA", "MATIC", "DOGE", "TRX", "SHIB", "POL"
                }
                
                pairs = []
                for coin in coins:
                    coin_upper = coin.upper()
                    quote = "INR" if coin_upper in canonical_inr_coins else "USDT"
                    pairs.append(f"{coin_upper}/{quote}")

                for pair in pairs:
                    for timeframe in ["15m", "1d"]:
                        coindcx_pair = canonical_to_coindcx_pair(pair)
                        interval = "1d" if timeframe == "1d" else "15m"
                        # Limit to last 5 candles to catch the latest closed ones
                        raw_candles = await self._fetch_coindcx_candles(coindcx_pair, interval, limit=5)
                        
                        if raw_candles:
                            formatted = []
                            for c in raw_candles:
                                try:
                                    ts_ms = int(c.get("time", c.get("t", 0)) or 0)
                                    close = float(c.get("close", c.get("c", 0.0)) or 0.0)
                                    if ts_ms <= 0 or close <= 0:
                                        continue
                                    formatted.append({
                                        "pair": pair,
                                        "timeframe": timeframe,
                                        "timestamp": ts_ms,
                                        "open": float(c.get("open", c.get("o", close))),
                                        "high": float(c.get("high", c.get("h", close))),
                                        "low": float(c.get("low", c.get("l", close))),
                                        "close": close,
                                        "volume": float(c.get("volume", c.get("v", 0.0))),
                                    })
                                except (TypeError, ValueError, KeyError):
                                    continue
                            
                            if formatted:
                                await self._candle_repo.upsert_candles(formatted)
                                
                logger.info("[Flusher] Periodic candle flush cycle completed successfully")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("[Flusher] Unexpected error in candle flusher loop", extra={"error": str(exc)})

    # ── True Multi-Timeframe (MTF) Data Fetching ─────────────────────────────
    async def fetch_mtf_candles(self, coindcx_pair: str) -> dict[str, list[dict]]:
        """
        Fetch true discrete 5m, 15m, and 1h candle feeds with 8 req/s rate-limiting gate.
        """
        timeframes = ["5m", "15m", "1h"]
        results: dict[str, list[dict]] = {}
        for tf in timeframes:
            await self._rate_limiter.acquire()
            raw = await self._fetch_coindcx_candles(coindcx_pair, interval=tf, limit=30)
            results[tf] = raw
        return results

    def evaluate_mtf_alignment(
        self,
        mtf_candles: dict[str, list[dict]],
    ) -> tuple[bool, dict]:
        """
        Calculates Fast EMA(9) vs Slow EMA(21) and momentum individually per timeframe.
        Returns: (is_aligned, indicator_details)
        """
        details: dict = {}
        tf_aligned = {}

        for tf, candles in mtf_candles.items():
            closes = []
            for c in candles:
                val = c.get("close", c.get("c", c.get("price", 0.0)))
                try:
                    closes.append(float(val))
                except (ValueError, TypeError):
                    continue

            if len(closes) >= 21:
                ema9 = calculate_ema(closes, 9)[-1]
                ema21 = calculate_ema(closes, 21)[-1]
                momentum = closes[-1] - closes[-2] if len(closes) >= 2 else 0.0
                aligned = ema9 >= ema21
                details[tf] = {
                    "ema9": round(ema9, 4),
                    "ema21": round(ema21, 4),
                    "momentum": round(momentum, 4),
                    "aligned": aligned,
                }
                tf_aligned[tf] = aligned
            else:
                details[tf] = {"aligned": True, "note": "insufficient_bars"}
                tf_aligned[tf] = True

        # True MTF alignment requires at least 15m and 1h alignment
        is_aligned = tf_aligned.get("15m", True) and tf_aligned.get("1h", True)
        return is_aligned, details

    # ── Polling (called by scheduler) ─────────────────────────────────────────

    async def poll(self) -> dict:
        """
        Fetch fresh signals from V1 scanner, update live cache, and publish events.

        Returns a summary dict for scheduler logging.
        """
        summary = {
            "fetched": 0,
            "new_signals": 0,
            "expired": 0,
            "errors": 0,
        }

        try:
            # 1. Refresh Live Macro Market Context (BTC, ETH, Fear & Greed)
            market_context = await self._market_context_service.refresh_market_context()
            self._confluence_engine.update_market_sentiment(
                btc_trend=market_context.get("btc_trend", "BULLISH"),
                eth_trend=market_context.get("eth_trend", "BULLISH"),
                regime=market_context.get("market_regime", "RISK_ON"),
                fear_greed=market_context.get("fear_and_greed", 50),
            )

            # 2. Refresh News Feeds
            await self._news_risk_service.fetch_latest_news()

            # 3. Fetch candidate signals
            raw = await self._fetch_v1_signals()
            summary["fetched"] = len(raw)

            # 4. Adapt V1 → V2 Signal
            candidates = v1_response_to_signals(
                raw,
                signal_ttl_seconds=self._config.v2_scanner_signal_ttl,
            )

            # 5. Enrich raw candidate dicts with News Risk Evaluations
            enriched_raw = []
            cand_by_coin = {c.get("coin", "").upper(): c for c in raw}
            for sig in candidates:
                cand_dict = cand_by_coin.get(sig.coin.upper(), {"coin": sig.coin})
                cand_dict["news"] = self._news_risk_service.evaluate_coin_news(sig.coin)
                enriched_raw.append(cand_dict)

            # 6. Filter by minimum priority
            candidates = filter_by_priority(candidates, self._min_priority)

            # 7. Evaluate through C2 5-Layer Confluence Engine & Strict Rejection Gate
            high_conviction_signals, eval_results = self._confluence_engine.evaluate_candidates(
                raw_candidates=enriched_raw,
                signals=candidates,
            )

            # 8. Retain latest-scan evaluation snapshot in memory (atomic replacement)
            new_eval_snapshot: dict[str, dict] = {}
            for res in eval_results:
                coin_sym = res.signal.coin.upper()
                cand_raw = cand_by_coin.get(coin_sym, {})
                
                # Determine EMA trend
                if coin_sym == "BTC":
                    ema_trend = self._market_context_service.get_current_sentiment().get("btc_trend", "SIDEWAYS")
                elif coin_sym == "ETH":
                    ema_trend = self._market_context_service.get_current_sentiment().get("eth_trend", "SIDEWAYS")
                else:
                    ema_trend = "BULLISH" if res.signal.mtf_alignment else "SIDEWAYS"

                raw_payload = res.signal.raw_payload or {}
                price_val = float(cand_raw.get("price") or raw_payload.get("price") or raw_payload.get("close") or 0.0)
                vol_24h = float(cand_raw.get("volume_24h") or cand_raw.get("volume") or raw_payload.get("volume_24h") or 0.0)
                vol_ratio = float(cand_raw.get("volume_spike_ratio") or cand_raw.get("volume_ratio") or raw_payload.get("volume_spike_ratio") or 1.0)
                rsi_val = float(cand_raw.get("rsi") or raw_payload.get("rsi_14") or raw_payload.get("rsi") or 50.0)

                eval_item = {
                    "symbol": coin_sym,
                    "coin": coin_sym,
                    "pair": res.signal.pair,
                    "price": price_val,
                    "volume_24h": vol_24h,
                    "volume_ratio": vol_ratio,
                    "ema_trend": ema_trend,
                    "rsi": rsi_val,
                    "mtf_alignment": "15m_1h" if res.signal.mtf_alignment else "none",
                    "is_mtf_aligned": bool(res.signal.mtf_alignment),
                    "confluence_score": res.confluence_score,
                    "status": "PASSED" if res.accepted else "REJECTED",
                    "accepted": res.accepted,
                    "eval_breakdown": {
                        "chart": {
                            "score": res.layer_evaluations["chart"].score,
                            "passed": res.layer_evaluations["chart"].passed,
                            "details": res.layer_evaluations["chart"].details,
                            "reasons": res.layer_evaluations["chart"].reasons,
                        } if "chart" in res.layer_evaluations else {},
                        "indicator": {
                            "score": res.layer_evaluations["indicator"].score,
                            "passed": res.layer_evaluations["indicator"].passed,
                            "details": res.layer_evaluations["indicator"].details,
                            "reasons": res.layer_evaluations["indicator"].reasons,
                        } if "indicator" in res.layer_evaluations else {},
                        "sentiment": {
                            "score": res.layer_evaluations["sentiment"].score,
                            "passed": res.layer_evaluations["sentiment"].passed,
                            "details": res.layer_evaluations["sentiment"].details,
                            "reasons": res.layer_evaluations["sentiment"].reasons,
                        } if "sentiment" in res.layer_evaluations else {},
                        "news": {
                            "score": res.layer_evaluations["news"].score,
                            "passed": res.layer_evaluations["news"].passed,
                            "details": res.layer_evaluations["news"].details,
                            "reasons": res.layer_evaluations["news"].reasons,
                        } if "news" in res.layer_evaluations else {},
                    },
                    "rejection_reasons": res.rejection_reasons,
                    "rejection_reason": "; ".join(res.rejection_reasons) if res.rejection_reasons else None,
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                }
                new_eval_snapshot[coin_sym] = eval_item
                new_eval_snapshot[res.signal.pair.upper()] = eval_item
                clean_pair = res.signal.pair.replace("/", "").replace("_", "").replace("-", "").upper()
                new_eval_snapshot[clean_pair] = eval_item

            self._latest_evaluated_coins = new_eval_snapshot

            # 9. Suppress signal generation if coin has an active position or live signal
            open_coins: set[str] = set()
            if self._position_repo:
                try:
                    open_positions = await self._position_repo.get_open()
                    for p in open_positions:
                        p_coin = getattr(p, "coin", "") or ""
                        p_clean = p_coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
                        if p_clean:
                            open_coins.add(p_clean)
                except Exception as e:
                    logger.debug("Could not fetch open positions for scanner filter: %s", e)

            # Clean up expired cooldowns
            now_utc = datetime.now(timezone.utc)
            cooldown_dur = getattr(self._config, "v2_post_exit_cooldown_seconds", 900)
            expired_cooldowns = []
            for c_coin, c_info in list(self._cooldowns.items()):
                c_exit = c_info["exit_time"]
                if c_exit.tzinfo is None:
                    c_exit = c_exit.replace(tzinfo=timezone.utc)
                elapsed = (now_utc - c_exit).total_seconds()
                if elapsed >= cooldown_dur:
                    expired_cooldowns.append(c_coin)
            for c_coin in expired_cooldowns:
                del self._cooldowns[c_coin]
                logger.info("Post-exit cooldown expired for %s. Re-entry allowed for genuinely new opportunities.", c_coin)

            live_coins = {s.coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "") for s in self._live.values()}

            actionable_candidates = []
            for sig in high_conviction_signals:
                sig_coin = sig.coin.upper().replace("/INR", "").replace("/USDT", "").replace("B-", "")
                if sig_coin in self._cooldowns:
                    c_exit = self._cooldowns[sig_coin]["exit_time"]
                    if c_exit.tzinfo is None:
                        c_exit = c_exit.replace(tzinfo=timezone.utc)
                    rem = cooldown_dur - (now_utc - c_exit).total_seconds()
                    logger.info(
                        "Signal generation suppressed for %s: post-exit cooldown active (%.0fs remaining after %s)",
                        sig_coin, max(0.0, rem), self._cooldowns[sig_coin]["exit_reason"]
                    )
                    continue
                if sig_coin in open_coins:
                    logger.info("Signal generation suppressed for %s: active open position exists in fleet", sig_coin)
                    continue
                if sig_coin in live_coins:
                    logger.debug("Signal generation suppressed for %s: unexpired live signal already active", sig_coin)
                    continue
                actionable_candidates.append(sig)

            # 10. Deduplicate against seen set
            new_signals, new_keys = deduplicate(actionable_candidates, self._seen_keys)
            self._seen_keys.update(new_keys)

            # 11. Persist new signals and publish events
            for sig in new_signals:
                await self._signal_repo.insert(sig)
                self._live[sig.id] = sig
                await self._publish_signal_generated(sig)
                summary["new_signals"] += 1

            # 12. Detect expiry in live cache
            live_list = list(self._live.values())
            still_live, newly_expired = detect_expired(live_list)

            for sig in newly_expired:
                del self._live[sig.id]
                self._seen_keys.discard(_dedup_key(sig))
                await self._signal_repo.mark_expired(sig.id, reason="TTL")
                await self._publish_signal_expired(sig)
                summary["expired"] += 1

            self._poll_count += 1
            self._last_poll_at = datetime.now(timezone.utc)
            self._last_error = None
            logger.info(
                "Scanner poll complete",
                extra={**summary, "live_count": len(self._live), "evaluated_count": len(eval_results)},
            )

        except Exception as exc:
            self._last_error = str(exc)
            summary["errors"] = 1
            logger.exception("Scanner poll failed", extra={"error": str(exc)})

        return summary

    async def check_expiry(self) -> int:
        """
        Check in-memory live signals for expiry (called by signal_expiry_check job).
        Returns count of signals expired.
        """
        live_list = list(self._live.values())
        _, newly_expired = detect_expired(live_list)
        for sig in newly_expired:
            del self._live[sig.id]
            self._seen_keys.discard(_dedup_key(sig))
            await self._signal_repo.mark_expired(sig.id, reason="TTL")
            await self._publish_signal_expired(sig)
        return len(newly_expired)


    # ── Public query interface ─────────────────────────────────────────────────

    def get_live_signals(self) -> list[Signal]:
        """Return current live signals sorted by score desc."""
        return sorted(self._live.values(), key=lambda s: s.score, reverse=True)

    def get_scanned_coins(
        self,
        min_score: Optional[int] = None,
        limit: int = 50,
        sort_by: str = "confluence_score",
    ) -> list[dict]:
        """Return unique evaluated coins from the latest scan pass."""
        unique_coins: dict[str, dict] = {}
        for k, item in self._latest_evaluated_coins.items():
            pair = item.get("pair") or item.get("symbol")
            if pair not in unique_coins:
                unique_coins[pair] = item

        items = list(unique_coins.values())
        if min_score is not None:
            items = [c for c in items if c.get("confluence_score", 0) >= min_score]

        if sort_by == "confluence_score":
            items.sort(key=lambda c: c.get("confluence_score", 0), reverse=True)
        elif sort_by == "price":
            items.sort(key=lambda c: c.get("price", 0.0), reverse=True)
        elif sort_by == "symbol":
            items.sort(key=lambda c: c.get("symbol", ""))

        return items[:limit]

    def get_scanned_coin_detail(self, symbol: str) -> Optional[dict]:
        """Return detail for a specific scanned coin (case-insensitive, handles BTC, BTCINR, BTC/INR)."""
        if not symbol:
            return None
        sym_clean = symbol.strip().upper()
        # Direct lookup
        if sym_clean in self._latest_evaluated_coins:
            return self._latest_evaluated_coins[sym_clean]

        # Clean alphanumeric lookup
        sym_alpha = sym_clean.replace("/", "").replace("_", "").replace("-", "")
        if sym_alpha in self._latest_evaluated_coins:
            return self._latest_evaluated_coins[sym_alpha]

        # Suffix / symbol matching
        for k, v in self._latest_evaluated_coins.items():
            if k.upper() == sym_clean or v.get("symbol", "").upper() == sym_clean:
                return v
        return None

    def get_health(self) -> dict:
        return {
            "poll_count":         self._poll_count,
            "last_poll_at":       self._last_poll_at.isoformat() if self._last_poll_at else None,
            "live_signals":       len(self._live),
            "evaluated_coins":    len(self.get_scanned_coins()),
            "last_error":         self._last_error,
            "healthy":            self._last_error is None and self._poll_count > 0,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _fetch_v1_signals(self) -> list[dict]:
        """Call V1 scanner signals endpoint, falling back to native CoinDCX candle scanning."""
        url = f"{self._config.v2_scanner_base_url}/signals"
        headers = {}
        if self._config.dashboard_api_key:
            headers["X-API-Key"] = self._config.dashboard_api_key

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data:
                        return data
                    if isinstance(data, dict):
                        signals = data.get("signals", [])
                        if signals:
                            return signals
        except Exception:
            # V1 is not running locally — fall back to native candle scanning
            pass

        return await self._generate_native_candidates()

    async def _generate_native_candidates(self) -> list[dict]:
        """Generate candidate signals natively from cached/fetched CoinDCX candles with full technical features."""
        coins = await self._fetch_watchlist_coins()
        canonical_inr_coins = {"BTC", "ETH", "SOL", "BNB", "XRP", "ZEC", "AVAX", "LINK", "DOGE", "SHIB", "MATIC"}
        candidates: list[dict] = []

        for coin in coins:
            coin_upper = coin.upper()
            quote = "INR" if coin_upper in canonical_inr_coins else "USDT"
            pair = f"{coin_upper}/{quote}"

            candles: list[dict] = []
            if self._candle_repo:
                try:
                    candles = await self._candle_repo.get_recent_candles(pair, "15m", limit=30)
                except Exception:
                    pass

            if not candles:
                coindcx_pair = canonical_to_coindcx_pair(pair)
                candles = await self._fetch_coindcx_candles(coindcx_pair, "15m", limit=30)

            if not candles:
                continue

            closes: list[float] = []
            highs: list[float] = []
            lows: list[float] = []
            volumes: list[float] = []

            for c in candles:
                try:
                    cl = float(c.get("close", c.get("c", 0.0)))
                    hi = float(c.get("high", c.get("h", cl)))
                    lo = float(c.get("low", c.get("l", cl)))
                    vo = float(c.get("volume", c.get("v", 0.0)))
                    if cl > 0:
                        closes.append(cl)
                        highs.append(hi)
                        lows.append(lo)
                        volumes.append(vo)
                except (ValueError, TypeError):
                    continue

            if not closes:
                continue

            latest_close = closes[-1]
            latest_high = highs[-1] if highs else latest_close
            latest_low = lows[-1] if lows else latest_close

            # Multi-Timeframe Alignment: check 15m and 1d
            candles_1d: list[dict] = []
            if self._candle_repo:
                try:
                    candles_1d = await self._candle_repo.get_recent_candles(pair, "1d", limit=30)
                except Exception:
                    pass

            # Coin class determination
            if coin_upper in ("BTC", "ETH", "SOL", "BNB"):
                coin_class = "A"
            elif coin_upper in ("XRP", "ADA", "MATIC", "LINK", "AVAX", "DOGE"):
                coin_class = "B"
            else:
                coin_class = "C"

            rsi = 50.0
            volume_ratio = 1.0
            vol_24h = sum(volumes) if volumes else 0.0

            if len(closes) >= 21:
                ema9_list = calculate_ema(closes, 9)
                ema21_list = calculate_ema(closes, 21)
                ema9 = ema9_list[-1] if ema9_list else latest_close
                ema21 = ema21_list[-1] if ema21_list else latest_close

                # RSI 14
                if len(closes) >= 15:
                    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
                    gains = [d if d > 0 else 0.0 for d in deltas]
                    losses = [-d if d < 0 else 0.0 for d in deltas]
                    avg_g = sum(gains[-14:]) / 14.0
                    avg_l = sum(losses[-14:]) / 14.0
                    if avg_l > 0:
                        rs = avg_g / avg_l
                        rsi = 100.0 - (100.0 / (1.0 + rs))
                    elif avg_g > 0:
                        rsi = 100.0

                # Volume ratio
                if volumes:
                    avg_vol = sum(volumes[-20:]) / max(1, len(volumes[-20:]))
                    volume_ratio = round(volumes[-1] / avg_vol, 2) if avg_vol > 0 else 1.0

                # 15m trend & MTF alignment
                is_15m_bullish = (ema9 >= ema21) and (latest_close >= ema21 * 0.998)
                is_1d_aligned = True
                if candles_1d and len(candles_1d) >= 5:
                    closes_1d = [float(c.get("close", c.get("c", 0.0))) for c in candles_1d if float(c.get("close", c.get("c", 0.0))) > 0]
                    if len(closes_1d) >= 5:
                        ema_1d = calculate_ema(closes_1d, min(9, len(closes_1d)))[-1]
                        is_1d_aligned = (closes_1d[-1] >= ema_1d) or (closes_1d[-1] >= closes_1d[0])
                mtf_aligned = bool(is_15m_bullish and is_1d_aligned)

                # Market state determination
                recent_high = max(highs[-10:-1]) if len(highs) >= 10 else latest_high
                if ema9 >= ema21:
                    if latest_close >= recent_high or ((latest_close - ema9) / ema9 > 0.005):
                        market_state = MarketState.BREAKOUT.value
                    elif latest_close >= ema9:
                        market_state = MarketState.BULL_TREND.value
                    else:
                        market_state = MarketState.PULLBACK.value
                else:
                    if latest_close > ema9:
                        market_state = MarketState.RECOVERY.value
                    else:
                        market_state = MarketState.DOWNTREND.value

                # Bot Archetype & Opportunity Type selection
                recent_range = (max(highs[-5:]) - min(lows[-5:])) if len(highs) >= 5 else 1.0
                wider_range = (max(highs[-15:]) - min(lows[-15:])) if len(highs) >= 15 else 1.0
                is_vcp = wider_range > 0 and (recent_range / wider_range) < 0.45

                if volume_ratio >= 1.5:
                    bot = "HDA"
                    opp_type = "absorption"
                    strategy_name = "High Delivery Absorption"
                elif is_vcp and is_15m_bullish:
                    bot = "VCP"
                    opp_type = "contraction"
                    strategy_name = "Volatility Contraction Pattern"
                elif market_state == MarketState.BREAKOUT.value:
                    bot = "STE"
                    opp_type = "momentum_trade"
                    strategy_name = "SuperTrend ATR Range Expansion"
                else:
                    bot = "STE"
                    opp_type = "continuation"
                    strategy_name = "SuperTrend ATR Range Expansion"

                # Candidate technical score calculation
                score = 75.0
                if ema9 >= ema21 and ema21 > 0:
                    spread_ratio = (ema9 - ema21) / ema21
                    score += min(15.0, spread_ratio * 500)
                if 45 <= rsi <= 70:
                    score += 5.0
                if market_state in (MarketState.BREAKOUT.value, MarketState.BULL_TREND.value):
                    score += 5.0
                if mtf_aligned:
                    score += 5.0
                score = min(95.0, max(50.0, score))
            else:
                market_state = MarketState.SIDEWAYS.value
                opp_type = "watchlist"
                bot = "STE"
                strategy_name = "SuperTrend ATR Range Expansion"
                mtf_aligned = False
                score = 65.0

            candidates.append({
                "coin": coin_upper,
                "pair": pair,
                "score": round(score, 1),
                "price": latest_close,
                "priority": "Elite" if score >= 90 else ("High" if score >= 80 else "Medium"),
                "strategy": strategy_name,
                "timeframe": "15m",
                "market_state": market_state,
                "opportunity_type": opp_type,
                "coin_class": coin_class,
                "mtf_alignment": mtf_aligned,
                "is_mtf_aligned": mtf_aligned,
                "bot": bot,
                "rsi": round(rsi, 2),
                "volume_24h": round(vol_24h, 2),
                "volume_ratio": round(volume_ratio, 2),
            })

        return candidates

    async def _publish_signal_generated(self, sig: Signal) -> None:
        raw_p = sig.raw_payload or {}
        price = float(raw_p.get("price") or raw_p.get("close") or 0.0)
        bot = sig.source_bot if sig.source_bot in ("STE", "HDA", "VCP", "BBS") else raw_p.get("bot", "STE")
        payload = {
            "signal_id":        sig.id,
            "coin":             sig.coin,
            "pair":             sig.pair,
            "priority":         sig.priority.value,
            "score":            sig.score,
            "price":            price,
            "market_state":     sig.market_state.value,
            "opportunity_type": sig.opportunity_type.value,
            "bot":              bot,
            "coin_class":       sig.coin_class,
            "expires_at":       sig.expires_at.isoformat(),
            "source":           "scanner_service",
            "confluence":       sig.confluence_breakdown or {},
        }
        await self._bus.publish(EventType.SIGNAL_GENERATED, payload)
        await self._event_log.append(
            event_type     = EventType.SIGNAL_GENERATED.value,
            payload        = payload,
            source_service = "scanner_service",
            entity_id      = sig.id,
        )

    async def _publish_signal_expired(self, sig: Signal) -> None:
        payload = {
            "signal_id": sig.id,
            "coin":      sig.coin,
            "reason":    "TTL",
        }
        await self._bus.publish(EventType.SIGNAL_EXPIRED, payload)
        await self._event_log.append(
            event_type     = EventType.SIGNAL_EXPIRED.value,
            payload        = payload,
            source_service = "scanner_service",
            entity_id      = sig.id,
        )
