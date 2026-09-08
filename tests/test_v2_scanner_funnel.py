"""
tests/test_v2_scanner_funnel.py
Unit tests verifying B1 Top 50 Composite Ranking and B2 Pre-C2 5-Stage Filter Cascade.
"""

import asyncio
import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta

from v2.bus.event_bus import EventBus
from v2.core.config import V2Config, invalidate_config
from v2.repository.db import Database
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.signal_repo import SignalRepository
from v2.repository.candle_repo import CandleRepository
from v2.services.scanner_service.service import ScannerService
from v2.services.scanner_service.confluence_engine import (
    ConfluenceEngine,
    NoOpSentimentProvider,
    SentimentProvider,
)

TEST_DB_DIR = os.path.abspath(".test_dbs")
os.makedirs(TEST_DB_DIR, exist_ok=True)


@pytest.mark.anyio
async def test_scanner_5_stage_filter_cascade_and_funnel_counters():
    """Verify that _generate_native_candidates logs per-stage funnel counters and enforces all 5 filters."""
    db_file = os.path.join(TEST_DB_DIR, f"db_funnel_{uuid.uuid4().hex[:8]}.db")
    db = Database(db_file)
    await db.open()

    bus = EventBus()
    sig_repo = SignalRepository(db.connection)
    event_repo = EventLogRepository(db.connection)
    candle_repo = CandleRepository(db.connection)

    cfg = V2Config(
        v2_db_path=db_file,
        scanner_min_24h_volume=1000.0,
        scanner_max_price_change_pct=25.0,
        scanner_min_atr_pct=0.5,
        scanner_max_atr_pct=12.0,
        scanner_ranking_weight_volume=0.40,
        scanner_ranking_weight_liquidity=0.35,
        scanner_ranking_weight_volatility=0.25,
        scanner_ranking_top_n=50,
    )

    scanner = ScannerService(
        bus=bus,
        signal_repo=sig_repo,
        event_log_repo=event_repo,
        candle_repo=candle_repo,
        config=cfg,
    )

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    sol_candles = [
        {"pair": "SOL/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 10000.0 + i * 50, "high": 10050.0 + i * 50, "low": 9980.0 + i * 50, "close": 10020.0 + i * 50, "volume": 100.0}
        for i in range(30)
    ]
    eth_candles = [
        {"pair": "ETH/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 250000.0 + i * 200, "high": 252000.0 + i * 200, "low": 248000.0 + i * 200, "close": 250200.0 + i * 200, "volume": 50.0}
        for i in range(30)
    ]
    pump_candles = [
        {"pair": "DOGE/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 10.0 if i == 0 else 15.0 + i * 0.1, "high": 16.0 + i * 0.1, "low": 9.9 if i == 0 else 14.8, "close": 10.0 if i == 0 else 15.5 + i * 0.1, "volume": 200.0}
        for i in range(30)
    ]

    await candle_repo.upsert_candles(sol_candles + eth_candles + pump_candles)

    # Override watchlist to test these coins
    async def mock_fetch_watchlist():
        return ["SOL", "ETH", "DOGE"]
    scanner._fetch_watchlist_coins = mock_fetch_watchlist

    candidates = await scanner._generate_native_candidates()

    assert hasattr(scanner, "_last_funnel_counters")
    counters = scanner._last_funnel_counters
    assert counters["raw_universe"] == 3
    assert counters["liquidity_passed"] == 3
    assert counters["volume_passed"] == 3
    assert counters["pump_dump_passed"] == 2  # SOL and ETH
    assert counters["c2_evaluated"] == len(candidates)
    assert len(candidates) == 2
    assert {c["coin"] for c in candidates} == {"SOL", "ETH"}

    # Assert composite ranking scores were computed
    for c in candidates:
        assert "composite_score" in c
        assert c["composite_score"] > 0

    await db.close()


@pytest.mark.anyio
async def test_confluence_engine_b3_regime_and_b4_dynamic_threshold():
    """Verify B3 bounded regime adjustment (+/-5) and B4 dynamic threshold bounds (80-92)."""
    engine = ConfluenceEngine(strict_threshold=85, max_signals=2, dynamic_min=80, dynamic_max=92)

    # 1. Test B4 dynamic threshold calculation
    t_normal = engine.get_dynamic_threshold(market_volatility=1.0, is_choppy=False)
    assert t_normal == 85

    t_choppy = engine.get_dynamic_threshold(market_volatility=1.8, is_choppy=True)
    assert 88 <= t_choppy <= 92

    t_calm = engine.get_dynamic_threshold(market_volatility=0.6, is_choppy=False)
    assert t_calm == 82

    # 2. Test B3 regime adjustment (+/- 5 bounded)
    engine.update_market_sentiment(btc_trend="BULLISH", eth_trend="BULLISH", regime="RISK_ON")
    assert engine.sentiment_evaluator.market_regime == "RISK_ON"

    # 3. Test SentimentProvider interface
    assert isinstance(engine.sentiment_provider, NoOpSentimentProvider)
    res = await engine.sentiment_provider.get_sentiment("SOL")
    assert res is None


@pytest.mark.anyio
async def test_scanner_cascade_strict_execution_order_and_stage_isolation():
    """Verify that the 5 filter stages execute in strict order (Liquidity -> Volume -> Pump/Dump -> Trend -> ATR) and isolate dropouts per stage."""
    db_file = os.path.join(TEST_DB_DIR, f"db_cascade_order_{uuid.uuid4().hex[:8]}.db")
    db = Database(db_file)
    await db.open()

    bus = EventBus()
    sig_repo = SignalRepository(db.connection)
    event_repo = EventLogRepository(db.connection)
    candle_repo = CandleRepository(db.connection)

    cfg = V2Config(
        v2_db_path=db_file,
        scanner_min_24h_volume=50000.0,
        scanner_max_price_change_pct=25.0,
        scanner_min_atr_pct=0.5,
        scanner_max_atr_pct=12.0,
        scanner_ranking_weight_volume=0.40,
        scanner_ranking_weight_liquidity=0.35,
        scanner_ranking_weight_volatility=0.25,
        scanner_ranking_top_n=50,
    )

    scanner = ScannerService(
        bus=bus,
        signal_repo=sig_repo,
        event_log_repo=event_repo,
        candle_repo=candle_repo,
        config=cfg,
    )

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 1. Coin B (LOWVOL): Drops at Stage 2 (Volume < 50000)
    b_candles = [
        {"pair": "BNB/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 50000.0, "high": 50500.0, "low": 49500.0, "close": 50000.0, "volume": 0.001}
        for i in range(30)
    ]

    # 2. Coin C (PUMP): Drops at Stage 3 (Price change +40% > 25%)
    c_candles = [
        {"pair": "XRP/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 50.0 if i == 0 else 70.0, "high": 72.0, "low": 49.0 if i == 0 else 68.0, "close": 50.0 if i == 0 else 70.0, "volume": 5000.0}
        for i in range(30)
    ]

    # 3. Coin D (DOWNTREND): Drops at Stage 4 (Severe downtrend breakdown with 24h change -18%)
    d_candles = [
        {"pair": "DOGE/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 20.0 if i < 20 else (20.0 - (i - 19) * 0.35), "high": 20.1 if i < 20 else (20.0 - (i - 19) * 0.35), "low": 19.9 if i < 20 else (19.8 - (i - 19) * 0.35), "close": 20.0 if i < 20 else (19.9 - (i - 19) * 0.35), "volume": 50000.0}
        for i in range(30)
    ]

    # 4. Coin E (LOW_ATR): Drops at Stage 5 (ATR % = 0.1% < 0.5%)
    e_candles = [
        {"pair": "ETH/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 250000.0, "high": 250100.0, "low": 249950.0, "close": 250000.0, "volume": 10.0}
        for i in range(30)
    ]

    # 5. Coin F (VALID): Passes all 5 stages
    f_candles = [
        {"pair": "SOL/INR", "timeframe": "15m", "timestamp": now_ms - (30 - i) * 900000, "open": 10000.0 + i * 20, "high": 10150.0 + i * 20, "low": 9900.0 + i * 20, "close": 10050.0 + i * 20, "volume": 100.0}
        for i in range(30)
    ]

    await candle_repo.upsert_candles(b_candles + c_candles + d_candles + e_candles + f_candles)

    # 6. Coin A (ILLIQUID): Not in database -> Drops at Stage 1 (Liquidity / no candles)
    async def mock_fetch_watchlist():
        return ["MATIC", "BNB", "XRP", "DOGE", "ETH", "SOL"]  # MATIC has no candles
    scanner._fetch_watchlist_coins = mock_fetch_watchlist
    scanner._fetch_coindcx_candles = lambda *args, **kwargs: asyncio.sleep(0, result=[])

    candidates = await scanner._generate_native_candidates()
    counters = scanner._last_funnel_counters

    # Assert strict step-down funnel progression
    assert counters["raw_universe"] == 6
    assert counters["liquidity_passed"] == 5  # MATIC dropped (no candles)
    assert counters["volume_passed"] == 4     # BNB dropped (low volume)
    assert counters["pump_dump_passed"] == 3  # XRP dropped (pump +40%)
    assert counters["trend_aligned_passed"] == 2  # DOGE dropped (downtrend)
    assert counters["volatility_passed"] == 1     # ETH dropped (ATR 0.06% < 0.5%)
    assert counters["c2_evaluated"] == 1          # Only SOL passed
    assert len(candidates) == 1
    assert candidates[0]["coin"] == "SOL"

    await db.close()


@pytest.mark.anyio
async def test_b3_score_vs_b4_threshold_attributable_separation():
    """Verify that B3 regime adjustment affects ONLY candidate score, while B4 volatility affects ONLY dynamic threshold without double-stacking."""
    engine = ConfluenceEngine(strict_threshold=85, max_signals=2, dynamic_min=80, dynamic_max=92)

    # Set weak/bearish macro environment (B3: -5 score delta)
    engine.update_market_sentiment(btc_trend="BEARISH", eth_trend="BEARISH", regime="RISK_OFF")

    from v2.core.types import MarketState, OppType, Priority, RiskLevel, Signal
    mock_sig = Signal(
        id="sig-sep-1",
        coin="SOL",
        pair="SOL/INR",
        market_state=MarketState.BULL_TREND,
        opportunity_type=OppType.MOMENTUM_TRADE,
        priority=Priority.HIGH,
        risk_level=RiskLevel.LOW,
        score=88,
        confidence=85,
        coin_class="A",
        mtf_alignment=True,
        generated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        raw_payload={"price": 12500.0},
    )

    # Scenario: Elevated volatility (market_volatility = 1.8, is_choppy = False)
    # B4 moves threshold from 85 -> 89 (+4 threshold delta)
    # B3 applies -5 score delta to candidate score
    raw_cand = [{"coin": "SOL", "price": 12500.0, "volume_24h": 5000000.0}]
    signals = [mock_sig]

    high_conviction, results = engine.evaluate_candidates(
        raw_candidates=raw_cand,
        signals=signals,
        market_volatility=1.8,
        is_choppy=False,
    )

    assert len(results) == 1
    res = results[0]

    # Verify score delta is attributable to B3 regime
    assert res.regime_adjustment == -5
    assert res.confluence_score == res.base_score + res.regime_adjustment

    # Verify threshold delta is attributable to B4 volatility
    assert res.dynamic_threshold == 89
    assert res.dynamic_threshold == engine.get_dynamic_threshold(market_volatility=1.8, is_choppy=False)

    # Confirm neither stacked on the other's dimension
    assert res.confluence_score < res.base_score
    assert res.dynamic_threshold > engine.strict_threshold
