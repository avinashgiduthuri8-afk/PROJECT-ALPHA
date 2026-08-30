"""
PROJECT-ALPHA — Phase 2 & Phase 3 Test Suite:
  - Phase 2: Market Regime & Live Sentiment Tracker (BTC/ETH EMAs, Fear & Greed Index)
  - Phase 2: Live News & Delisting Risk Scraper (CryptoPanic, Delisting Keywords, Negative Risk)
  - Phase 3: True Multi-Timeframe (MTF) Data Fetching & Rate Limiter (5m, 15m, 1h Feeds)
  - Integration with C2 Confluence Engine & ScannerService
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

from v2.core.types import MarketState, Priority, RiskLevel, Signal, OppType
from v2.core.config import get_config
from v2.bus.event_bus import EventBus
from v2.repository.signal_repo import SignalRepository
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.candle_repo import CandleRepository
from v2.services.scanner_service.market_context import (
    MarketContextService,
    calculate_ema,
    determine_trend_from_candles,
)
from v2.services.scanner_service.news_fetcher import (
    NewsRiskService,
    DELISTING_KEYWORDS,
    NEGATIVE_NEWS_KEYWORDS,
)
from v2.services.scanner_service.service import (
    ScannerService,
    AsyncRateLimiter,
)
from v2.services.scanner_service.confluence_engine import (
    ConfluenceEngine,
    MarketSentimentEvaluator,
    NewsEventsEvaluator,
)


def _make_bullish_candles(count: int = 30, base_price: float = 60000.0) -> list[dict]:
    candles = []
    for i in range(count):
        price = base_price + (i * 200.0)
        candles.append({
            "time": 1700000000000 + i * 900000,
            "open": price - 50.0,
            "high": price + 100.0,
            "low": price - 100.0,
            "close": price,
            "volume": 10.0 + i,
        })
    return candles


def _make_bearish_candles(count: int = 30, base_price: float = 60000.0) -> list[dict]:
    candles = []
    for i in range(count):
        price = base_price - (i * 200.0)
        candles.append({
            "time": 1700000000000 + i * 900000,
            "open": price + 50.0,
            "high": price + 100.0,
            "low": price - 100.0,
            "close": price,
            "volume": 10.0 + i,
        })
    return candles


def _make_test_signal(
    coin: str = "SOL",
    score: int = 90,
    priority: Priority = Priority.ELITE,
    market_state: MarketState = MarketState.BREAKOUT,
    mtf_alignment: bool = True,
) -> Signal:
    now = datetime.now(timezone.utc)
    return Signal(
        id=f"sig_{coin}_1",
        coin=coin,
        pair=f"{coin}/INR",
        market_state=market_state,
        opportunity_type=OppType.MOMENTUM_TRADE,
        priority=priority,
        risk_level=RiskLevel.LOW,
        score=score,
        confidence=90,
        coin_class="A",
        mtf_alignment=mtf_alignment,
        generated_at=now,
        expires_at=now,
    )


# ── 1. MarketContextService Tests ─────────────────────────────────────────────

def test_calculate_ema():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0]
    ema_5 = calculate_ema(prices, 5)
    assert len(ema_5) == len(prices) - 5 + 1
    assert ema_5[-1] > ema_5[0]

    # Insufficient prices returns []
    assert calculate_ema([10.0, 11.0], 5) == []


def test_determine_trend_from_candles():
    bull_candles = _make_bullish_candles(30)
    bear_candles = _make_bearish_candles(30)
    flat_candles = [{"close": 50000.0} for _ in range(30)]

    assert determine_trend_from_candles(bull_candles) == "BULLISH"
    assert determine_trend_from_candles(bear_candles) == "BEARISH"
    assert determine_trend_from_candles(flat_candles) == "SIDEWAYS"
    assert determine_trend_from_candles([]) == "SIDEWAYS"


def test_market_context_evaluate_regime():
    service = MarketContextService()
    bull_btc = _make_bullish_candles(30)
    bear_btc = _make_bearish_candles(30)
    bull_eth = _make_bullish_candles(30)
    bear_eth = _make_bearish_candles(30)

    # Bullish BTC -> RISK_ON
    btc_t, eth_t, regime = service.evaluate_regime(bull_btc, bull_eth)
    assert btc_t == "BULLISH"
    assert eth_t == "BULLISH"
    assert regime == "RISK_ON"

    # Bearish BTC -> RISK_OFF
    btc_t, eth_t, regime = service.evaluate_regime(bear_btc, bull_eth)
    assert btc_t == "BEARISH"
    assert regime == "RISK_OFF"


@pytest.mark.anyio
async def test_fetch_fear_and_greed_fallback():
    service = MarketContextService(timeout_seconds=0.5)

    # Mock response
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"value": "72", "value_classification": "Greed"}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        val = await service.fetch_fear_and_greed()
        assert val == 72

    # Network failure triggers fallback to 50
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=Exception("Network down"))):
        val_fallback = await service.fetch_fear_and_greed()
        assert val_fallback == 50


@pytest.mark.anyio
async def test_refresh_market_context_full_flow():
    service = MarketContextService()

    mock_btc = _make_bullish_candles(30, 65000.0)
    mock_eth = _make_bullish_candles(30, 3500.0)

    service.fetch_pair_candles = AsyncMock(side_effect=[mock_btc, mock_eth])
    service.fetch_fear_and_greed = AsyncMock(return_value=68)

    ctx = await service.refresh_market_context()
    assert ctx["btc_trend"] == "BULLISH"
    assert ctx["eth_trend"] == "BULLISH"
    assert ctx["market_regime"] == "RISK_ON"
    assert ctx["fear_and_greed"] == 68
    assert ctx["btc_price"] == 65000.0 + 29 * 200.0


# ── 2. NewsRiskService Tests ──────────────────────────────────────────────────

def test_news_risk_service_keyword_scanning():
    service = NewsRiskService()

    delist_posts = [
        {"title": "Binance to delist SOL pair trading due to low liquidity", "currencies": [{"code": "SOL"}]}
    ]
    res_delist = service._analyze_posts_for_coin("SOL", delist_posts)
    assert res_delist["delisting_risk"] is True
    assert res_delist["sentiment_score"] == 0.0

    hack_posts = [
        {"title": "DeFi Protocol on ETH hacked for $50M in flash loan exploit", "currencies": [{"code": "ETH"}]}
    ]
    res_hack = service._analyze_posts_for_coin("ETH", hack_posts)
    assert res_hack["has_negative_news"] is True
    assert res_hack["delisting_risk"] is False
    assert res_hack["sentiment_score"] <= 0.40

    clean_posts = [
        {"title": "BTC ETF inflows hit record high with institutional adoption", "currencies": [{"code": "BTC"}]}
    ]
    res_clean = service._analyze_posts_for_coin("BTC", clean_posts)
    assert res_clean["has_negative_news"] is False
    assert res_clean["delisting_risk"] is False
    assert res_clean["sentiment_score"] >= 0.70


@pytest.mark.anyio
async def test_news_risk_service_caching():
    service = NewsRiskService(cache_ttl_seconds=180)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"title": "SEC investigation into crypto exchange operations", "currencies": [{"code": "XRP"}]}
        ]
    }

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)) as mock_get:
        news1 = await service.fetch_latest_news()
        assert "XRP" in news1
        assert news1["XRP"]["has_negative_news"] is True
        assert mock_get.call_count == 1

        # Second call should use cache
        news2 = await service.fetch_latest_news()
        assert mock_get.call_count == 1
        assert "XRP" in news2


# ── 3. AsyncRateLimiter Tests ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_async_rate_limiter():
    limiter = AsyncRateLimiter(max_rate=20.0)  # 20 req/s -> 0.05s per req
    start = time.perf_counter()

    for _ in range(4):
        await limiter.acquire()

    elapsed = time.perf_counter() - start
    assert elapsed >= 0.10  # 3 intervals of 0.05s = 0.15s approx


# ── 4. True MTF Indicator Tests ───────────────────────────────────────────────

def test_evaluate_mtf_alignment():
    service = ScannerService(
        bus=MagicMock(),
        signal_repo=MagicMock(),
        event_log_repo=MagicMock(),
        config=get_config(),
    )

    mtf_bullish = {
        "5m": _make_bullish_candles(30),
        "15m": _make_bullish_candles(30),
        "1h": _make_bullish_candles(30),
    }
    is_aligned, details = service.evaluate_mtf_alignment(mtf_bullish)
    assert is_aligned is True
    assert "5m" in details
    assert "15m" in details
    assert "1h" in details
    assert details["15m"]["aligned"] is True

    mtf_bearish_1h = {
        "5m": _make_bullish_candles(30),
        "15m": _make_bullish_candles(30),
        "1h": _make_bearish_candles(30),
    }
    is_aligned_bear, details_bear = service.evaluate_mtf_alignment(mtf_bearish_1h)
    assert is_aligned_bear is False
    assert details_bear["1h"]["aligned"] is False


# ── 5. Confluence Engine Dynamic Sentiment & News Risk Integration ────────────

def test_confluence_engine_rejection_on_delisting():
    engine = ConfluenceEngine(strict_threshold=85, max_signals=2)
    engine.update_market_sentiment("BULLISH", "BULLISH", "RISK_ON", fear_greed=65)

    sig = _make_test_signal("SOL", score=95)
    cand_with_delist = {"coin": "SOL", "news": {"has_negative_news": False, "delisting_risk": True}}

    accepted, results = engine.evaluate_candidates([cand_with_delist], [sig])
    assert len(accepted) == 0
    assert results[0].accepted is False
    assert any("delisting" in r.lower() for r in results[0].rejection_reasons)


def test_confluence_engine_rejection_on_risk_off():
    engine = ConfluenceEngine(strict_threshold=85, max_signals=2)
    # Market Regime is RISK_OFF
    engine.update_market_sentiment("BEARISH", "BEARISH", "RISK_OFF", fear_greed=18)

    sig = _make_test_signal("BTC", score=95)
    cand_clean = {"coin": "BTC", "news": {"has_negative_news": False, "delisting_risk": False}}

    accepted, results = engine.evaluate_candidates([cand_clean], [sig])
    assert len(accepted) == 0
    assert results[0].accepted is False
    assert any("risk_off" in r.lower() for r in results[0].rejection_reasons)


# ── 6. Full ScannerService Poll Integration Test ──────────────────────────────

@pytest.mark.anyio
async def test_scanner_service_poll_with_context_and_news():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    signal_repo = MagicMock(spec=SignalRepository)
    signal_repo.insert = AsyncMock()
    signal_repo.mark_expired = AsyncMock()
    event_log = MagicMock(spec=EventLogRepository)
    event_log.append = AsyncMock()

    config = get_config()
    service = ScannerService(bus, signal_repo, event_log, config)

    # Mock V1 raw response
    mock_v1_raw = [
        {
            "coin": "SOL",
            "pair": "SOL/INR",
            "score": 92,
            "priority": "elite",
            "market_state": "breakout",
            "mtf_alignment": True,
            "risk_level": "low",
        },
        {
            "coin": "HACKED_COIN",
            "pair": "HACKED/INR",
            "score": 90,
            "priority": "elite",
            "market_state": "breakout",
            "mtf_alignment": True,
            "risk_level": "low",
        }
    ]
    service._fetch_v1_signals = AsyncMock(return_value=mock_v1_raw)

    # Mock Macro Context
    service.market_context_service.refresh_market_context = AsyncMock(return_value={
        "btc_trend": "BULLISH",
        "eth_trend": "BULLISH",
        "market_regime": "RISK_ON",
        "fear_and_greed": 65,
    })

    # Mock News Service
    service.news_risk_service.fetch_latest_news = AsyncMock()
    service.news_risk_service.evaluate_coin_news = MagicMock(side_effect=lambda coin: {
        "has_negative_news": (coin == "HACKED_COIN"),
        "delisting_risk": False,
        "sentiment_score": 0.10 if coin == "HACKED_COIN" else 0.90,
    })

    summary = await service.poll()
    assert summary["fetched"] == 2
    # Only SOL should pass; HACKED_COIN rejected by News Layer
    assert summary["new_signals"] == 1

    live_sigs = service.get_live_signals()
    assert len(live_sigs) == 1
    assert live_sigs[0].coin == "SOL"
    assert live_sigs[0].score >= 85
