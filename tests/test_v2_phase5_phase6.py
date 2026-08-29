"""
Comprehensive Unit and Integration Tests for Phase 5 (Trading Execution & Bot Adapters)
and Phase 6 (Shadow Mode Engine & Decision Divergence Tracking) — Production Fleet Edition.
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
    ShadowTrade,
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
from v2.services.trading_service import (
    TradingService,
    STEAdapter,
    HDAAdapter,
    VCPAdapter,
    BBSAdapter,
    StrategyAdapterFactory,
)
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
        pair=f"{coin}/INR",
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
        raw_payload={"coin": coin, "price": 12500.0},
    )


# ── 1. Bot Adapter Strategy Tests ─────────────────────────────────────────────

def test_ste_adapter_calculations():
    adapter = STEAdapter()
    order = adapter.calculate_order(
        coin="SOL",
        pair="SOL/INR",
        approved_amount=500.0,
        current_price=100.0,
        ai_adjustments={"tighten_stop": False},
    )
    assert order["bot"] == BotName.STE
    assert order["qty"] == 5.0
    assert order["stop_loss"] == 98.0   # -2.0%
    assert order["take_profit"] == 104.6 # +4.6%

    # Tightened stop
    order_tight = adapter.calculate_order(
        coin="SOL",
        pair="SOL/INR",
        approved_amount=500.0,
        current_price=100.0,
        ai_adjustments={"tighten_stop": True},
    )
    assert order_tight["stop_loss"] == 98.8  # -1.2%


def test_hda_adapter_calculations():
    adapter = HDAAdapter()
    order = adapter.calculate_order(
        coin="ETH",
        pair="ETH/INR",
        approved_amount=1000.0,
        current_price=2000.0,
        ai_adjustments={"tighten_stop": False},
    )
    assert order["bot"] == BotName.HDA
    assert order["stop_loss"] == 1956.0  # -2.2%
    assert order["take_profit"] == 2105.6 # +5.28%


def test_vcp_adapter_calculations():
    adapter = VCPAdapter()
    order = adapter.calculate_order(
        coin="AVAX",
        pair="AVAX/INR",
        approved_amount=500.0,
        current_price=2800.0,
        ai_adjustments={},
    )
    assert order["bot"] == BotName.VCP
    assert order["stop_loss"] == 2744.0  # -2.0%
    assert order["take_profit"] == 2940.0 # +5.0%


def test_bbs_adapter_calculations():
    adapter = BBSAdapter()
    order = adapter.calculate_order(
        coin="DOGE",
        pair="DOGE/INR",
        approved_amount=400.0,
        current_price=16.50,
        ai_adjustments={},
    )
    assert order["bot"] == BotName.BBS
    assert order["qty"] >= 1.0
    assert order["stop_loss"] < 16.50
    assert order["take_profit"] > 16.50


def test_strategy_adapter_factory():
    ste = StrategyAdapterFactory.get_adapter(BotName.STE)
    assert isinstance(ste, STEAdapter)

    hda = StrategyAdapterFactory.get_adapter("HDA")
    assert isinstance(hda, HDAAdapter)

    with pytest.raises(ValueError, match="InvalidStrategyError"):
        StrategyAdapterFactory.get_adapter("VGX")

    with pytest.raises(ValueError, match="InvalidStrategyError"):
        StrategyAdapterFactory.get_adapter("PMB")


# ── 2. Capital Guard & Circuit Breaker Tests ──────────────────────────────────

def test_capital_guard_limits():
    cfg = V2Config(
        ste_capital_limit=500.0,
        total_capital_limit=1000.0,
        v2_max_positions_ste=2,
    )
    guard = CapitalGuard(cfg)

    # 1. Allowed trade
    d1 = guard.check_trade(
        bot=BotName.STE,
        requested_amount=200.0,
        current_bot_deployed=200.0,
        total_deployed=200.0,
        current_bot_positions=1,
    )
    assert d1.allowed is True
    assert d1.code == "ALLOWED"

    # 2. Blocked by max positions
    d2 = guard.check_trade(
        bot=BotName.STE,
        requested_amount=100.0,
        current_bot_deployed=200.0,
        total_deployed=200.0,
        current_bot_positions=2,
    )
    assert d2.allowed is False
    assert d2.code == "BLOCKED_MAX_POSITIONS"

    # 3. Blocked by per-bot capital limit
    d3 = guard.check_trade(
        bot=BotName.STE,
        requested_amount=400.0,
        current_bot_deployed=200.0,
        total_deployed=200.0,
        current_bot_positions=1,
    )
    assert d3.allowed is False
    assert d3.code == "BLOCKED_BOT_CAPITAL"

    # 4. Blocked by total portfolio capital limit
    d4 = guard.check_trade(
        bot=BotName.STE,
        requested_amount=200.0,
        current_bot_deployed=200.0,
        total_deployed=900.0,
        current_bot_positions=1,
    )
    assert d4.allowed is False
    assert d4.code == "BLOCKED_TOTAL_CAPITAL"


def test_circuit_breaker_trips_and_resets():
    cfg = V2Config(v2_max_consecutive_losses=3, v2_max_drawdown_pct=10.0)
    breaker = CircuitBreaker(cfg)

    assert breaker.is_open is False

    breaker.record_trade_result(bot=BotName.STE, pnl=-50.0)
    breaker.record_trade_result(bot=BotName.STE, pnl=-50.0)
    assert breaker.is_open is False

    breaker.record_trade_result(bot=BotName.STE, pnl=-50.0)
    assert breaker.is_open is True

    breaker.reset()
    assert breaker.is_open is False


# ── 3. Shadow Repository CRUD Tests ───────────────────────────────────────────

@pytest.mark.anyio
async def test_shadow_repository_crud(tmp_path):
    db_path = str(tmp_path / f"test_shadow_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    try:
        conn = db.connection
        sig_repo = SignalRepository(conn)
        repo = ShadowRepository(conn)
        now = datetime.now(timezone.utc)

        sig = make_test_signal(coin="SOL")
        await sig_repo.insert(sig)

        trade = ShadowTrade(
            id=str(uuid.uuid4()),
            signal_id=sig.id,
            bot=BotName.STE,
            coin="SOL",
            pair="SOL/INR",
            entry_price=100.0,
            qty=2.0,
            amount=200.0,
            stop_loss=98.0,
            take_profit=104.6,
            ai_recommendation="APPROVE",
            created_at=now,
            status="OPEN",
        )
        await repo.insert_shadow_trade(trade)

        opens = await repo.get_open_shadow_trades()
        assert len(opens) == 1
        assert opens[0].coin == "SOL"

        # Update exit
        trade.status = "CLOSED"
        trade.simulated_exit_price = 104.6
        trade.exit_reason = "TAKE_PROFIT"
        trade.simulated_pnl = 9.2
        trade.simulated_pnl_pct = 4.6
        trade.closed_at = datetime.now(timezone.utc)
        await repo.update_shadow_trade(trade)

        all_trades = await repo.get_recent_shadow_trades()
        assert len(all_trades) == 1
        assert all_trades[0].status == "CLOSED"
        assert all_trades[0].simulated_pnl == 9.2
    finally:
        await db.close()


# ── 4. End-to-End Trading & Risk Service Integration ──────────────────────────

@pytest.mark.anyio
async def test_risk_and_trading_service_flow(tmp_path):
    db_path = str(tmp_path / f"test_flow_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    risk_service = None
    shadow_service = None
    trading_service = None
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
            ste_capital_limit=10000.0,
            total_capital_limit=50000.0,
            v2_default_trade_amount_ste=500.0,
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

        sig = make_test_signal(coin="SOL")
        await sig_repo.insert(sig)

        # 1. Publish SIGNAL_AI_CONFIRMED (from Phase 4 AI layer)
        await bus.publish(
            EventType.SIGNAL_AI_CONFIRMED,
            {
                "signal_id": sig.id,
                "coin": "SOL",
                "pair": "SOL/INR",
                "recommendation": "APPROVE",
                "confidence_score": 85,
                "suggested_adjustments": {"size_multiplier": 1.0, "tighten_stop": False},
                "price": 100.0,
                "bot": "STE",
            },
        )
        await asyncio.sleep(0.2)

        assert len(approved_events) == 1
        assert approved_events[0]["coin"] == "SOL"
        assert approved_events[0]["approved_amount"] == 500.0

        assert len(executed_events) == 1
        assert executed_events[0]["coin"] == "SOL"

        # Verify live position opened
        open_pos = await pos_repo.get_open()
        assert len(open_pos) == 1
        assert open_pos[0].coin == "SOL"

        # 2. Check position exit trigger (Price drops to SL)
        closed_trades = await trading_service.check_open_position_exits({"SOL": 97.0})
        assert len(closed_trades) == 1
        assert closed_trades[0].coin == "SOL"
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
            bot=BotName.STE,
            coin="SOL",
            pair="SOL/INR",
            qty=10.0,
            entry_price=100.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=105.0,
            unrealised_pnl=50.0,
            stop_loss=98.0,
            take_profit=104.6,
        )
        await pos_repo.insert(pos)

        snapshot = await port_service.capture_and_publish_snapshot()
        assert snapshot.total_deployed == 1000.0
        assert snapshot.total_unrealised_pnl == 50.0
        assert snapshot.total_cash == 99000.0
        assert snapshot.total_aum == 100050.0
        assert len(snapshot.positions_by_bot[BotName.STE.value]) == 1
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

        app = FastAPI()
        init_router(
            bus=bus,
            signal_repo=sig_repo,
            ai_repo=AIAnalysisRepository(conn),
            position_repo=pos_repo,
            trade_repo=trade_repo,
            shadow_repo=shadow_repo,
            metrics_repo=metrics_repo,
            event_log_repo=event_log,
            config=cfg,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            shadow_service=shadow_svc,
        )
        app.include_router(api_router, prefix="/api/v2")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-secret-key"},
        ) as client:
            r_positions = await client.get("/api/v2/trading/positions")
            assert r_positions.status_code == 200

            r_portfolio = await client.get("/api/v2/portfolio/snapshot")
            assert r_portfolio.status_code == 200

            r_shadow = await client.get("/api/v2/shadow/summary")
            assert r_shadow.status_code == 200
    finally:
        await db.close()
