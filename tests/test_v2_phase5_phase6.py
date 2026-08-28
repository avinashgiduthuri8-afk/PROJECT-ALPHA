"""
Comprehensive Unit and Integration Tests for Phase 5 (Trading Execution & Bot Adapters)
and Phase 6 (Shadow Mode Engine & Decision Divergence Tracking).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import uuid
import pytest

import httpx
from fastapi import FastAPI

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config, get_config, invalidate_config
from v2.core.types import (
    AIRecommendation,
    BotMode,
    BotName,
    ExitReason,
    MarketState,
    OppType,
    Position,
    PositionStatus,
    Priority,
    RiskLevel,
    Signal,
    Trade,
)
from v2.repository.db import Database
from v2.repository.signal_repo import SignalRepository
from v2.repository.ai_repo import AIAnalysisRepository
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.repository.shadow_repo import ShadowRepository
from v2.repository.metrics_repo import MetricsRepository
from v2.repository.event_log_repo import EventLogRepository

from v2.services.risk_service import RiskService, CapitalGuard, CircuitBreaker
from v2.services.portfolio_service import PortfolioService, PortfolioAggregator
from v2.services.trading_service import TradingService, MTBAdapter, PMBAdapter, VGXAdapter
from v2.services.shadow_service import ShadowService, ShadowEngine, DivergenceTracker
from v2.api.router import router as api_router, init_router


def make_test_signal(
    coin: str = "SOL",
    score: int = 85,
    market_state: MarketState = MarketState.BULL_TREND,
    opp_type: OppType = OppType.MOMENTUM_TRADE,
) -> Signal:
    now = datetime.now(timezone.utc)
    return Signal(
        id=str(uuid.uuid4()),
        coin=coin,
        pair=f"B-{coin}_USDT",
        market_state=market_state,
        opportunity_type=opp_type,
        priority=Priority.HIGH,
        risk_level=RiskLevel.LOW,
        score=score,
        confidence=80,
        coin_class="A",
        mtf_alignment=True,
        generated_at=now,
        expires_at=now + timedelta(seconds=300),
        source_bot="scanner_v1",
        raw_payload={"coin": coin, "price": 140.0},
    )


# ── 1. Bot Adapter Strategy Tests ─────────────────────────────────────────────

def test_mtb_adapter_calculations():
    adapter = MTBAdapter()
    order = adapter.calculate_order(
        coin="SOL",
        pair="B-SOL_USDT",
        approved_amount=200.0,
        current_price=100.0,
        ai_adjustments={"tighten_stop": False},
    )
    assert order["bot"] == BotName.MTB
    assert order["qty"] == 2.0
    assert order["stop_loss"] == 98.0   # -2.0%
    assert order["take_profit"] == 104.5 # +4.5%

    # Tightened stop
    order_tight = adapter.calculate_order(
        coin="SOL",
        pair="B-SOL_USDT",
        approved_amount=200.0,
        current_price=100.0,
        ai_adjustments={"tighten_stop": True},
    )
    assert order_tight["stop_loss"] == 98.8  # -1.2%


def test_pmb_adapter_calculations():
    adapter = PMBAdapter()
    order = adapter.calculate_order(
        coin="ETH",
        pair="B-ETH_USDT",
        approved_amount=100.0,
        current_price=2000.0,
        ai_adjustments={"tighten_stop": False},
    )
    assert order["bot"] == BotName.PMB
    assert order["stop_loss"] == 1950.0  # -2.5%
    assert order["take_profit"] == 2070.0 # +3.5%


def test_vgx_adapter_calculations():
    adapter = VGXAdapter()
    order = adapter.calculate_order(
        coin="BTC",
        pair="B-BTC_USDT",
        approved_amount=500.0,
        current_price=50000.0,
        ai_adjustments={},
    )
    assert order["bot"] == BotName.VGX
    assert order["stop_loss"] == 48000.0  # -4.0%
    assert order["take_profit"] == 51000.0 # +2.0%


# ── 2. Capital Guard & Circuit Breaker Tests ──────────────────────────────────

def test_capital_guard_limits():
    cfg = V2Config(
        mtb_capital_limit=500.0,
        total_capital_limit=1000.0,
        v2_max_positions_mtb=2,
    )
    guard = CapitalGuard(cfg)

    # 1. Allowed trade
    d1 = guard.check_trade(
        bot=BotName.MTB,
        requested_amount=200.0,
        current_bot_deployed=200.0,
        total_deployed=200.0,
        current_bot_positions=1,
    )
    assert d1.allowed is True
    assert d1.code == "ALLOWED"

    # 2. Blocked by max positions
    d2 = guard.check_trade(
        bot=BotName.MTB,
        requested_amount=100.0,
        current_bot_deployed=200.0,
        total_deployed=200.0,
        current_bot_positions=2,
    )
    assert d2.allowed is False
    assert d2.code == "BLOCKED_MAX_POSITIONS"

    # 3. Blocked by per-bot capital limit
    d3 = guard.check_trade(
        bot=BotName.MTB,
        requested_amount=400.0,
        current_bot_deployed=200.0,
        total_deployed=200.0,
        current_bot_positions=1,
    )
    assert d3.allowed is False
    assert d3.code == "BLOCKED_BOT_CAPITAL"

    # 4. Blocked by total portfolio capital limit
    d4 = guard.check_trade(
        bot=BotName.MTB,
        requested_amount=200.0,
        current_bot_deployed=200.0,
        total_deployed=900.0,
        current_bot_positions=1,
    )
    assert d4.allowed is False
    assert d4.code == "BLOCKED_TOTAL_CAPITAL"


def test_circuit_breaker_trips_and_resets():
    cfg = V2Config(v2_max_consecutive_losses=3)
    breaker = CircuitBreaker(cfg)

    assert breaker.is_open is False
    breaker.record_trade_result(BotName.MTB, -10.0)
    breaker.record_trade_result(BotName.MTB, -15.0)
    assert breaker.is_open is False

    # 3rd consecutive loss trips breaker
    breaker.record_trade_result(BotName.MTB, -20.0)
    assert breaker.is_open is True

    dec = breaker.check_breaker(BotName.MTB, 100.0)
    assert dec.allowed is False
    assert dec.code == "BLOCKED_CIRCUIT_BREAKER"

    # Reset
    breaker.reset()
    assert breaker.is_open is False
    assert breaker.check_breaker(BotName.MTB, 100.0).allowed is True


# ── 3. Database Migration 003 & Shadow Repository Tests ───────────────────────

@pytest.mark.anyio
async def test_shadow_repository_crud(tmp_path):
    db_path = str(tmp_path / f"test_shadow_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    try:
        conn = db.connection
        sig_repo = SignalRepository(conn)
        shadow_repo = ShadowRepository(conn)

        sig = make_test_signal(coin="SOL")
        await sig_repo.insert(sig)

        shadow_trade = ShadowEngine(
            bus=EventBus(),
            shadow_repo=shadow_repo,
            event_log_repo=EventLogRepository(conn),
            config=V2Config(v2_db_path=db_path),
        )

        trade = await shadow_trade.record_approved_trade(
            signal_id=sig.id,
            bot=BotName.MTB,
            coin="SOL",
            pair="B-SOL_USDT",
            entry_price=100.0,
            qty=2.0,
            amount=200.0,
            stop_loss=98.0,
            take_profit=104.5,
            ai_recommendation="APPROVE",
        )

        assert trade.id is not None
        assert trade.status == "OPEN"

        # Check open trades query
        open_trades = await shadow_repo.get_open_shadow_trades()
        assert len(open_trades) == 1
        assert open_trades[0].coin == "SOL"

        # Simulate price tick hitting Take Profit (105.0 >= 104.5)
        closed = await shadow_trade.evaluate_prices({"SOL": 105.0})
        assert len(closed) == 1
        assert closed[0].status == "CLOSED_TP"
        assert closed[0].simulated_pnl == 9.0  # (104.5 - 100) * 2.0
        assert closed[0].exit_reason == "TAKE_PROFIT"

        # Divergence tracking
        tracker = DivergenceTracker(
            bus=EventBus(),
            shadow_repo=shadow_repo,
            event_log_repo=EventLogRepository(conn),
        )
        div = await tracker.record_divergence(
            signal_id=sig.id,
            bot=BotName.MTB,
            coin="SOL",
            v1_action="EXECUTED",
            v2_action="AI_REJECTED",
            divergence_type="AI_FILTERED",
            reason="Bearish divergence on RSI",
            v1_pnl=-5.0,
            v2_simulated_pnl=0.0,
        )
        assert div.id is not None

        summary = await shadow_repo.get_divergence_summary()
        assert summary["total_divergences"] == 1
        assert summary["total_shadow_trades"] == 1
        assert summary["winning_shadow_trades"] == 1
        assert summary["simulated_win_rate_pct"] == 100.0
    finally:
        await db.close()


# ── 4. RiskService + TradingService Event Bus Flow ────────────────────────────

@pytest.mark.anyio
async def test_risk_and_trading_service_flow(tmp_path):
    db_path = str(tmp_path / f"test_flow_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    risk_service = None
    trading_service = None
    shadow_service = None
    try:
        conn = db.connection
        bus = EventBus()
        sig_repo = SignalRepository(conn)
        pos_repo = PositionRepository(conn)
        trade_repo = TradeRepository(conn)
        shadow_repo = ShadowRepository(conn)
        event_log = EventLogRepository(conn)

        cfg = V2Config(
            v2_db_path=db_path,
            v2_shadow_mode=True,
            v2_trading_enabled=True,
            mtb_capital_limit=1000.0,
            total_capital_limit=5000.0,
            v2_default_trade_amount_mtb=200.0,
        )

        risk_service = RiskService(bus, pos_repo, trade_repo, event_log, cfg)
        shadow_service = ShadowService(bus, shadow_repo, event_log, cfg)
        trading_service = TradingService(bus, pos_repo, trade_repo, event_log, cfg, shadow_service.engine)

        await risk_service.start()
        await shadow_service.start()
        await trading_service.start()

        approved_events = []
        executed_events = []
        async def on_appr(et, p): approved_events.append(p)
        async def on_exec(et, p): executed_events.append(p)
        bus.subscribe(EventType.TRADE_APPROVED, on_appr)
        bus.subscribe(EventType.TRADE_EXECUTED, on_exec)

        sig = make_test_signal(coin="AVAX")
        await sig_repo.insert(sig)

        # 1. Publish SIGNAL_AI_CONFIRMED (from Phase 4 AI layer)
        await bus.publish(
            EventType.SIGNAL_AI_CONFIRMED,
            {
                "signal_id": sig.id,
                "coin": "AVAX",
                "pair": "B-AVAX_USDT",
                "recommendation": "APPROVE",
                "confidence_score": 85,
                "suggested_adjustments": {"size_multiplier": 1.0, "tighten_stop": False},
                "price": 30.0,
            },
        )
        await asyncio.sleep(0.05)

        assert len(approved_events) == 1
        assert approved_events[0]["coin"] == "AVAX"
        assert approved_events[0]["approved_amount"] == 200.0

        assert len(executed_events) == 1
        assert executed_events[0]["coin"] == "AVAX"

        # Verify live position opened
        open_pos = await pos_repo.get_open()
        assert len(open_pos) == 1
        assert open_pos[0].coin == "AVAX"

        # 2. Check position exit trigger (Price drops to SL)
        closed_trades = await trading_service.check_open_position_exits({"AVAX": 29.0})
        assert len(closed_trades) == 1
        assert closed_trades[0].coin == "AVAX"
        assert closed_trades[0].exit_reason == ExitReason.STOP_LOSS

        # Verify position closed
        open_pos_after = await pos_repo.get_open()
        assert len(open_pos_after) == 0

    finally:
        if trading_service: await trading_service.stop()
        if shadow_service: await shadow_service.stop()
        if risk_service: await risk_service.stop()
        await db.close()


# ── 5. Portfolio Aggregator & Service Tests ───────────────────────────────────

@pytest.mark.anyio
async def test_portfolio_service_aggregation(tmp_path):
    db_path = str(tmp_path / f"test_port_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    port_service = None
    try:
        conn = db.connection
        bus = EventBus()
        pos_repo = PositionRepository(conn)
        trade_repo = TradeRepository(conn)
        metrics_repo = MetricsRepository(conn)
        cfg = V2Config(v2_db_path=db_path)

        port_service = PortfolioService(bus, pos_repo, trade_repo, metrics_repo, cfg)
        await port_service.start()

        now = datetime.now(timezone.utc)
        pos = Position(
            id=str(uuid.uuid4()),
            bot=BotName.MTB,
            coin="NEAR",
            pair="B-NEAR_USDT",
            qty=100.0,
            entry_price=5.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=5.5,
            unrealised_pnl=50.0,
            stop_loss=4.9,
            take_profit=5.3,
        )
        await pos_repo.insert(pos)

        snapshot = await port_service.capture_and_publish_snapshot()
        assert snapshot.total_deployed == 500.0
        assert snapshot.total_unrealised_pnl == 50.0
        assert snapshot.total_cash == 99500.0
        assert snapshot.total_aum == 100050.0
        assert len(snapshot.positions_by_bot[BotName.MTB.value]) == 1
    finally:
        if port_service: await port_service.stop()
        await db.close()


# ── 6. FastAPI Endpoints Tests (Phase 5 & 6) ──────────────────────────────────

@pytest.mark.anyio
async def test_api_endpoints_phase5_phase6(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-secret-key")
    invalidate_config()

    db_path = str(tmp_path / f"test_api_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    risk_svc = None
    port_svc = None
    shadow_svc = None
    try:
        conn = db.connection
        bus = EventBus()
        sig_repo = SignalRepository(conn)
        pos_repo = PositionRepository(conn)
        trade_repo = TradeRepository(conn)
        shadow_repo = ShadowRepository(conn)
        metrics_repo = MetricsRepository(conn)
        event_log = EventLogRepository(conn)
        cfg = get_config()

        risk_svc = RiskService(bus, pos_repo, trade_repo, event_log, cfg)
        port_svc = PortfolioService(bus, pos_repo, trade_repo, metrics_repo, cfg)
        shadow_svc = ShadowService(bus, shadow_repo, event_log, cfg)
        trading_svc = TradingService(bus, pos_repo, trade_repo, event_log, cfg, shadow_svc.engine)

        await risk_svc.start()
        await port_svc.start()
        await shadow_svc.start()
        await trading_svc.start()

        # Seed data
        sig = make_test_signal(coin="DOT")
        await sig_repo.insert(sig)
        await shadow_svc.engine.record_approved_trade(
            signal_id=sig.id,
            bot=BotName.MTB,
            coin="DOT",
            pair="B-DOT_USDT",
            entry_price=10.0,
            qty=20.0,
            amount=200.0,
            stop_loss=9.8,
            take_profit=10.45,
        )

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v2")
        init_router(
            scanner_service=None,
            scheduler=None,
            config=cfg,
            ai_service=None,
            ai_repo=None,
            signal_repo=sig_repo,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            trading_service=trading_svc,
            shadow_service=shadow_svc,
            shadow_repo=shadow_repo,
            position_repo=pos_repo,
            trade_repo=trade_repo,
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"X-API-Key": "test-secret-key"}

            # 1. GET /api/v2/risk/state
            resp = await client.get("/api/v2/risk/state", headers=headers)
            assert resp.status_code == 200
            risk_data = resp.json()
            assert risk_data["circuit_breaker_open"] is False

            # 2. GET /api/v2/portfolio/snapshot
            resp = await client.get("/api/v2/portfolio/snapshot", headers=headers)
            assert resp.status_code == 200
            port_data = resp.json()
            assert port_data["total_aum"] > 0.0

            # 3. GET /api/v2/shadow/trades
            resp = await client.get("/api/v2/shadow/trades", headers=headers)
            assert resp.status_code == 200
            shadow_trades = resp.json()
            assert len(shadow_trades) == 1
            assert shadow_trades[0]["coin"] == "DOT"

            # 4. GET /api/v2/shadow/summary
            resp = await client.get("/api/v2/shadow/summary", headers=headers)
            assert resp.status_code == 200
            summary = resp.json()
            assert summary["total_shadow_trades"] == 1

            # 5. GET /api/v2/trading/positions
            resp = await client.get("/api/v2/trading/positions", headers=headers)
            assert resp.status_code == 200

            # 6. GET /api/v2/trading/trades
            resp = await client.get("/api/v2/trading/trades", headers=headers)
            assert resp.status_code == 200
    finally:
        if trading_svc: await trading_svc.stop()
        if shadow_svc: await shadow_svc.stop()
        if port_svc: await port_svc.stop()
        if risk_svc: await risk_svc.stop()
        await db.close()
        invalidate_config()
