"""
Regression test for PROJECT-ALPHA V2:
Verifies the complete pipeline:
  Candles -> Native Candidate Generation -> Confluence Engine -> Signal
  -> AI Intelligence -> Risk Engine -> Trading Service -> Paper Position
  -> Bot Pipeline Stage Update.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import AsyncMock

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.bus.subscribers import register_all
from v2.core.config import V2Config
from v2.core.types import BotName, BotMode, MarketState, OppType, Priority, RiskLevel, Signal
import uuid
from v2.repository.candle_repo import CandleRepository
from v2.repository.signal_repo import SignalRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.ai_repo import AIAnalysisRepository
from v2.repository.db import Database
from v2.services.scanner_service.service import ScannerService
from v2.services.ai_intelligence_service.service import AIIntelligenceService
from v2.services.risk_service.service import RiskService
from v2.services.trading_service.service import TradingService
from v2.services.dashboard_service.bot_pipeline import BotPipelineTracker


import tempfile
from pathlib import Path


@pytest.mark.anyio
async def test_complete_signal_to_paper_trade_pipeline():
    test_db = Path(tempfile.gettempdir()) / f"test_pipe_{uuid.uuid4().hex}.db"
    db = Database(str(test_db))
    await db.open()
    conn = db.connection

    # Repositories
    candle_repo = CandleRepository(conn)
    signal_repo = SignalRepository(conn)
    position_repo = PositionRepository(conn)
    trade_repo = TradeRepository(conn)
    event_log_repo = EventLogRepository(conn)
    ai_repo = AIAnalysisRepository(conn)

    # Seed 15m and 1d bullish breakout candles for BTC/INR
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    step_15m = 15 * 60 * 1000
    base_price = 7800000.0

    candles_15m = []
    price = base_price
    for i in range(30):
        ts = now_ms - (30 - i) * step_15m
        if i % 2 == 0 and i > 0:
            price -= 1500.0  # healthy pullback
        else:
            price += 2000.0  # upward continuation
        vol = 25.0 if i >= 27 else 10.0
        candles_15m.append({
            "pair": "BTC/INR",
            "timeframe": "15m",
            "timestamp": ts,
            "open": price - 500.0,
            "high": price + 1000.0,
            "low": price - 1000.0,
            "close": price,
            "volume": vol,
        })
    await candle_repo.upsert_candles(candles_15m)

    step_1d = 24 * 60 * 60 * 1000
    candles_1d = []
    p_1d = base_price
    for i in range(10):
        ts = now_ms - (10 - i) * step_1d
        if i % 3 == 0 and i > 0:
            p_1d -= 5000.0
        else:
            p_1d += 12000.0
        candles_1d.append({
            "pair": "BTC/INR",
            "timeframe": "1d",
            "timestamp": ts,
            "open": p_1d - 2000.0,
            "high": p_1d + 5000.0,
            "low": p_1d - 3000.0,
            "close": p_1d,
            "volume": 100.0,
        })
    await candle_repo.upsert_candles(candles_1d)

    # EventBus and Services
    bus = EventBus()
    config = V2Config(
        v2_deployment_mode="SHADOW",
        v2_ai_enabled=True,
        v2_ai_confidence_threshold=60,
        order_size_inr=200.0,
        enforce_single_coin_lock=True,
    )

    scanner_service = ScannerService(
        config=config,
        bus=bus,
        signal_repo=signal_repo,
        event_log_repo=event_log_repo,
        candle_repo=candle_repo,
    )

    ai_service = AIIntelligenceService(
        config=config,
        bus=bus,
        ai_repo=ai_repo,
        signal_repo=signal_repo,
        event_log_repo=event_log_repo,
    )

    risk_service = RiskService(
        bus=bus,
        position_repo=position_repo,
        trade_repo=trade_repo,
        event_log_repo=event_log_repo,
        config=config,
    )

    trading_service = TradingService(
        bus=bus,
        position_repo=position_repo,
        trade_repo=trade_repo,
        event_log_repo=event_log_repo,
        config=config,
    )

    bot_tracker = BotPipelineTracker()

    # Wire bus
    register_all(
        bus=bus,
        ai_service=ai_service,
        risk_service=risk_service,
        trading_service=trading_service,
    )

    async def _on_bot_event(et: EventType, p: dict) -> None:
        bot_tracker.handle_bus_event(et.value, p)

    bus.subscribe(EventType.SIGNAL_GENERATED, _on_bot_event)
    bus.subscribe(EventType.SIGNAL_AI_CONFIRMED, _on_bot_event)
    bus.subscribe(EventType.TRADE_APPROVED, _on_bot_event)
    bus.subscribe(EventType.TRADE_EXECUTED, _on_bot_event)
    bus.subscribe(EventType.POSITION_OPENED, _on_bot_event)

    # Override external network calls for deterministic local testing
    scanner_service._fetch_watchlist_coins = AsyncMock(return_value=["BTC"])
    scanner_service._fetch_coindcx_candles = AsyncMock(return_value=[])
    scanner_service._news_risk_service.fetch_latest_news = AsyncMock()
    scanner_service.bootstrap_candles = AsyncMock()
    scanner_service._candle_flusher_loop = AsyncMock()
    scanner_service._calibration_worker.start = AsyncMock()
    scanner_service._calibration_worker.stop = AsyncMock()
    scanner_service._market_context_service.refresh_market_context = AsyncMock(return_value={
        "btc_trend": "BULLISH",
        "eth_trend": "BULLISH",
        "market_regime": "RISK_ON",
        "fear_and_greed": 65,
    })

    await scanner_service.start()
    await ai_service.start()
    await trading_service.start()

    # Trigger poll
    summary = await scanner_service.poll()

    assert summary["fetched"] == 1
    assert summary["new_signals"] == 1, f"Expected 1 high-conviction signal, got {summary}"

    # Verify signal persisted in repository
    all_signals = await signal_repo.get_by_coin("BTC")
    assert len(all_signals) == 1
    btc_sig = all_signals[0]
    assert btc_sig.mtf_alignment is True
    assert btc_sig.market_state in (MarketState.BREAKOUT, MarketState.BULL_TREND)

    # Let event loop process downstream events
    await asyncio.sleep(0.5)

    # Verify AI evaluation persisted
    ai_analysis = await ai_repo.get_by_signal_id(btc_sig.id)
    assert ai_analysis is not None
    assert ai_analysis.recommendation.value in ("APPROVE", "SCALE_DOWN")

    # Verify Paper Position opened in PositionRepository
    open_positions = await position_repo.get_open()
    assert len(open_positions) == 1, f"Expected 1 open position, got {open_positions}"
    pos = open_positions[0]
    assert pos.coin == "BTC"
    assert pos.mode == BotMode.PAPER
    assert pos.entry_price > 7800000.0  # Real price, not 100.0
    assert pos.qty > 0.0

    # Verify Bot Tracker updated beyond IDLE
    target_bot = btc_sig.source_bot or "HDA"
    bot_state = bot_tracker.get_bot_detail(target_bot)
    assert bot_state is not None
    assert bot_state["signals_generated"] >= 1
    assert bot_state["telemetry"]["ai_evaluations"] >= 1
    assert bot_state["open_positions"] >= 1
    assert bot_state["current_stage"] == "position_manager"
    assert bot_state["stage_status"] == "IN_POSITION"

    # Cleanup
    await scanner_service.stop()
    await ai_service.stop()
    await trading_service.stop()
    await db.close()
