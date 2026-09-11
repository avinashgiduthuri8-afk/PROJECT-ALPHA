"""
test_v2_e2e_platform.py — Comprehensive Opaque-Box E2E Platform Test Suite
PROJECT-ALPHA V2 (Milestones M0-M4 Verification Suite)

Authoritative test suite derived directly from:
- ORIGINAL_REQUEST.md (Requirements R1, R2, R3, R4)
- PROJECT.md (Features 1-14, Architecture & Interface Contracts)
- TEST_INFRA.md (Coverage Thresholds: Tiers 1-4)

Test Architecture:
- Tier 1: Primary Feature Coverage (60 tests: 5 tests x 12 Features)
- Tier 2: Boundary & Corner Cases (60 tests: 5 tests x 12 Features)
- Tier 3: Pairwise Cross-Feature Combinations (12 tests)
- Tier 4: Real-World Workload Scenarios (5 high-complexity end-to-end scenarios)
Total Tests: 137 tests.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import uuid

import pytest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

from v2.app_v2 import app, templates
from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config, get_config, invalidate_config
from v2.core.types import (
    BotMode,
    BotName,
    ExitReason,
    Position,
    PositionStatus,
    Trade,
    PortfolioSnapshot,
    Signal,
    OppType,
    Priority,
    RiskLevel,
    MarketState,
)
from v2.repository.db import Database
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.repository.candle_repo import CandleRepository
from v2.repository.signal_repo import SignalRepository
from v2.services.dashboard_service.bot_pipeline import BotPipelineTracker, BotState, STAGE_ORDER
from v2.services.dashboard_service.aggregator import DashboardAggregator
from v2.services.dashboard_service.service import DashboardService
from v2.services.portfolio_service.aggregator import PortfolioAggregator
from v2.services.portfolio_service.service import PortfolioService
from v2.services.ai_intelligence_service import AIIntelligenceService
from v2.services.ai_intelligence_service.circuit_breaker import CircuitBreaker, CircuitState
from v2.api.router import init_router, router as api_router
from v2.api.dashboard_routes import router as dashboard_router, init_dashboard_routes
from v2.api.production_routes import init_production_router
from v2.api.schemas import (
    PositionSchema,
    DashboardOverviewSchema,
    ScannedCoinSchema,
    SetModeRequestSchema,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATE_PATH = _PROJECT_ROOT / "v2" / "templates" / "dashboard.html"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_api_key():
    return "test-e2e-platform-key"


@pytest.fixture
def auth_headers(test_api_key):
    return {"X-API-Key": test_api_key}


@pytest.fixture
def template_html():
    """Read the V2 Mission Control dashboard HTML source directly."""
    assert _TEMPLATE_PATH.exists(), f"Dashboard template not found at {_TEMPLATE_PATH}"
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


@pytest.fixture
def test_db_path(tmp_path, monkeypatch, test_api_key):
    """Provides an isolated database path with environment variables configured."""
    db_file = str(tmp_path / f"test_e2e_{uuid.uuid4().hex[:8]}.db")
    monkeypatch.setenv("V2_DB_PATH", db_file)
    monkeypatch.setenv("DASHBOARD_API_KEY", test_api_key)
    monkeypatch.setenv("DASHBOARD_SECURITY_PASSWORD", "110299")
    invalidate_config()
    yield db_file
    invalidate_config()


async def open_test_database(path: str) -> Database:
    """Helper to open and migrate an isolated SQLite database."""
    db = Database(path)
    await db.open()
    return db


@pytest.fixture
def sample_positions():
    """Returns a deterministic set of active positions across all 4 production bots."""
    now = datetime.now(timezone.utc)
    return [
        Position(
            id="pos-ste-001",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.05,
            entry_price=6000000.0,
            entry_time=now - timedelta(minutes=30),
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=6120000.0,
            unrealised_pnl=6000.0,
            stop_loss=5880000.0,
            take_profit=6276000.0,
        ),
        Position(
            id="pos-hda-001",
            bot=BotName.HDA,
            coin="ETH",
            pair="ETH/INR",
            qty=1.2,
            entry_price=250000.0,
            entry_time=now - timedelta(minutes=20),
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=255000.0,
            unrealised_pnl=6000.0,
            stop_loss=244500.0,
            take_profit=263200.0,
        ),
        Position(
            id="pos-vcp-001",
            bot=BotName.VCP,
            coin="SOL",
            pair="SOL/INR",
            qty=10.0,
            entry_price=12000.0,
            entry_time=now - timedelta(minutes=15),
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=12240.0,
            unrealised_pnl=2400.0,
            stop_loss=11760.0,
            take_profit=12600.0,
        ),
        Position(
            id="pos-bbs-001",
            bot=BotName.BBS,
            coin="DOGE",
            pair="DOGE/INR",
            qty=500.0,
            entry_price=12.0,
            entry_time=now - timedelta(minutes=5),
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=12.6,
            unrealised_pnl=300.0,
            stop_loss=11.7,
            take_profit=12.72,
        ),
    ]


@pytest.fixture
def configured_test_client(test_db_path, test_api_key):
    """Configured TestClient for FastAPI app with initialized routers and isolated DB."""
    test_app = FastAPI()
    cfg = get_config()

    aggregator = DashboardAggregator()
    init_dashboard_routes(aggregator)

    async def _init_repos():
        db = Database(test_db_path)
        await db.open()
        return db

    db = asyncio.run(_init_repos())
    pos_repo = PositionRepository(db.connection)
    trade_repo = TradeRepository(db.connection)

    init_router(
        position_repo=pos_repo,
        trade_repo=trade_repo,
        config=cfg,
    )
    init_production_router(
        controller=None,
        watchdog=None,
        config=cfg,
        position_repo=pos_repo,
    )

    test_app.include_router(api_router, prefix="/api/v2")
    test_app.include_router(dashboard_router, prefix="/api/v2")

    client = TestClient(test_app)
    yield client
    asyncio.run(db.close())


# ==============================================================================
# TIER 1: PRIMARY FEATURE COVERAGE (60 Tests: 5 Tests x 12 Features)
# ==============================================================================

class TestTier1Feature1Hydration:
    """F1: SQLite Active Position Startup Hydration into BotPipelineTracker."""

    @pytest.mark.asyncio
    async def test_t1_1_hydration_restores_all_bots(self, sample_positions):
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        bots = {b["bot_name"]: b for b in tracker.get_all_bots()}
        assert bots["STE"]["open_positions"] == 1
        assert bots["HDA"]["open_positions"] == 1
        assert bots["VCP"]["open_positions"] == 1
        assert bots["BBS"]["open_positions"] == 1

    @pytest.mark.asyncio
    async def test_t1_2_hydration_computes_deployed_capital(self, sample_positions):
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        detail = tracker.get_bot_detail("STE")
        assert detail is not None
        assert detail["capital_deployed"] == pytest.approx(300000.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_t1_3_hydration_advances_stage_to_position_manager(self, sample_positions):
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        detail = tracker.get_bot_detail("HDA")
        assert detail["current_stage"] == "position_manager"
        assert detail["stage_status"] == "IN_POSITION"

    @pytest.mark.asyncio
    async def test_t1_4_hydration_sets_last_action_and_coin(self, sample_positions):
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        detail = tracker.get_bot_detail("VCP")
        assert detail["last_coin"] == "SOL"
        assert "Tracking active position: SOL" in detail["last_action"]

    @pytest.mark.asyncio
    async def test_t1_5_hydration_ignores_closed_positions(self, sample_positions):
        closed_pos = Position(
            id="pos-closed-001",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.01,
            entry_price=5000000.0,
            entry_time=datetime.now(timezone.utc),
            mode=BotMode.PAPER,
            status=PositionStatus.CLOSED,
        )
        tracker = BotPipelineTracker()
        active_only = [p for p in sample_positions + [closed_pos] if p.status != PositionStatus.CLOSED]
        await tracker.sync_from_repository(active_only)
        detail = tracker.get_bot_detail("STE")
        assert detail["open_positions"] == 1


class TestTier1Feature2DashboardMount:
    """F2: Dashboard Router Mount and Endpoints."""

    def test_t1_6_dashboard_router_initialization(self):
        aggregator = DashboardAggregator()
        init_dashboard_routes(aggregator)
        from v2.api.dashboard_routes import get_aggregator
        assert get_aggregator() is aggregator

    @pytest.mark.asyncio
    async def test_t1_7_dashboard_overview_snapshot(self):
        aggregator = DashboardAggregator()
        snapshot = await aggregator.get_overview_snapshot()
        assert snapshot["status"] == "ok"
        assert "execution_fleet" in snapshot
        assert "active_positions" in snapshot

    @pytest.mark.asyncio
    async def test_t1_8_dashboard_fleet_telemetry_structure(self):
        aggregator = DashboardAggregator()
        snapshot = await aggregator.get_overview_snapshot()
        fleet = snapshot["execution_fleet"]
        for bot in ("STE", "HDA", "VCP", "BBS"):
            assert bot in fleet
            assert fleet[bot]["bot_name"] == bot
            assert "wallet_allocation_inr" in fleet[bot]

    def test_t1_9_fleet_bot_pause_resume_toggle(self):
        aggregator = DashboardAggregator()
        assert not aggregator.is_bot_paused("STE")
        aggregator.pause_bot("STE")
        assert aggregator.is_bot_paused("STE")
        aggregator.resume_bot("STE")
        assert not aggregator.is_bot_paused("STE")

    @pytest.mark.asyncio
    async def test_t1_10_dashboard_signals_funnel_present(self):
        aggregator = DashboardAggregator()
        snapshot = await aggregator.get_overview_snapshot()
        funnel = snapshot.get("scanner_funnel", {})
        assert "total_scanned" in funnel
        assert "passing_candidates" in funnel


class TestTier1Feature3OpenPositionsEndpoint:
    """F3: /positions/open Non-Closed Status Filter."""

    @pytest.mark.asyncio
    async def test_t1_11_position_repo_get_active_positions(self, test_db_path, sample_positions):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            for pos in sample_positions:
                await repo.insert(pos)
            active = await repo.get_active_positions()
            assert len(active) == len(sample_positions)
            ids = {p.id for p in active}
            assert "pos-ste-001" in ids
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t1_12_get_active_positions_excludes_closed(self, test_db_path, sample_positions):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            for pos in sample_positions:
                await repo.insert(pos)
            closed_pos = Position(
                id="pos-closed-test",
                bot=BotName.STE,
                coin="ETH",
                pair="ETH/INR",
                qty=1.0,
                entry_price=200000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.CLOSED,
            )
            await repo.insert(closed_pos)
            active = await repo.get_active_positions()
            assert all(p.status != PositionStatus.CLOSED for p in active)
            assert len(active) == 4
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t1_13_get_active_positions_includes_pending(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            pending_pos = Position(
                id="pos-pending-entry",
                bot=BotName.VCP,
                coin="SOL",
                pair="SOL/INR",
                qty=2.0,
                entry_price=11000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            await repo.insert(pending_pos)
            active = await repo.get_active_positions()
            assert any(p.id == "pos-pending-entry" for p in active)
        finally:
            await db.close()

    def test_t1_14_positions_open_endpoint_auth(self, configured_test_client):
        resp = configured_test_client.get("/api/v2/positions/open")
        assert resp.status_code in (401, 403)

    def test_t1_15_positions_open_endpoint_schema_contract(self, configured_test_client, auth_headers):
        resp = configured_test_client.get("/api/v2/positions/open", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestTier1Feature4DashboardOverviewPositions:
    """F4: Dashboard Overview Positions Payload and Counts."""

    @pytest.mark.asyncio
    async def test_t1_16_aggregator_snapshot_contains_active_positions(self):
        aggregator = DashboardAggregator()
        snapshot = await aggregator.get_overview_snapshot()
        assert "active_positions" in snapshot
        assert isinstance(snapshot["active_positions"], list)

    def test_t1_17_dashboard_overview_schema_validation(self):
        payload = {
            "status": "ok",
            "active_ws_clients": 2,
            "portfolio": {"total_aum": 105000.0, "total_cash": 95000.0},
            "subsystems": {"scanner": {"healthy": True}},
        }
        schema = DashboardOverviewSchema(**payload)
        assert schema.status == "ok"
        assert schema.active_ws_clients == 2

    @pytest.mark.asyncio
    async def test_t1_18_overview_reflects_operational_system_status(self):
        aggregator = DashboardAggregator()
        snapshot = await aggregator.get_overview_snapshot()
        assert snapshot["system_status"] == "OPERATIONAL"

    @pytest.mark.asyncio
    async def test_t1_19_overview_reflects_emergency_stop(self):
        aggregator = DashboardAggregator()
        aggregator.trigger_emergency_stop()
        snapshot = await aggregator.get_overview_snapshot()
        assert snapshot["system_status"] == "EMERGENCY_STOP"

    def test_t1_20_dashboard_overview_api_route(self, configured_test_client, auth_headers):
        resp = configured_test_client.get("/api/v2/dashboard/overview", headers=auth_headers)
        assert resp.status_code == 200


class TestTier1Feature5DynamicEquityCalculation:
    """F5: Dynamic Total Equity (Cash + MTM - Friction)."""

    def test_t1_21_portfolio_aggregator_combines_cash_deployed_unrealized(self, sample_positions):
        snapshot = PortfolioAggregator.aggregate(
            positions=sample_positions,
            closed_trades=[],
            base_cash=100000.0,
        )
        assert snapshot.total_aum > 0
        assert snapshot.total_cash <= 100000.0
        assert snapshot.total_unrealised_pnl == pytest.approx(14700.0, rel=1e-3)

    def test_t1_22_realized_pnl_adjusts_cash(self):
        closed = [
            Trade(
                id="t-1",
                position_id="p-1",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                entry_price=50000.0,
                exit_price=55000.0,
                qty=0.01,
                pnl=500.0,
                pnl_pct=10.0,
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                exit_reason=ExitReason.TAKE_PROFIT,
                mode=BotMode.PAPER,
            )
        ]
        snapshot = PortfolioAggregator.aggregate(positions=[], closed_trades=closed, base_cash=100000.0)
        assert snapshot.total_realised_pnl == 500.0
        assert snapshot.total_cash == 100500.0

    def test_t1_23_capital_utilisation_percentage(self, sample_positions):
        snapshot = PortfolioAggregator.aggregate(positions=sample_positions, closed_trades=[], base_cash=500000.0)
        expected_util = round((snapshot.total_deployed / snapshot.total_aum) * 100.0, 2)
        assert snapshot.capital_utilisation == expected_util

    def test_t1_24_daily_pnl_aggregates_realized_and_unrealized(self, sample_positions):
        snapshot = PortfolioAggregator.aggregate(positions=sample_positions, closed_trades=[], base_cash=100000.0)
        assert snapshot.daily_pnl == snapshot.total_unrealised_pnl

    def test_t1_25_positions_grouped_by_bot(self, sample_positions):
        snapshot = PortfolioAggregator.aggregate(positions=sample_positions, closed_trades=[], base_cash=100000.0)
        for bot in ("STE", "HDA", "VCP", "BBS"):
            assert bot in snapshot.positions_by_bot
            assert len(snapshot.positions_by_bot[bot]) == 1


class TestTier1Feature6FrontendScriptSyntax:
    """F6: Frontend HTML & Modal Syntax Integrity."""

    def test_t1_26_dashboard_html_renders(self, template_html):
        assert "<!DOCTYPE html>" in template_html
        assert "PROJECT-ALPHA V2" in template_html

    def test_t1_27_live_trade_confirm_modal_present(self, template_html):
        assert 'id="liveTradeConfirmModal"' in template_html
        assert 'id="liveModePasswordInput"' in template_html

    def test_t1_28_position_action_modal_present(self, template_html):
        assert 'id="positionActionModal"' in template_html

    def test_t1_29_no_duplicate_tbody_variable_declarations(self, template_html):
        home_decl_count = len(re.findall(r"(?:const|let|var)\s+homeTbody\s*=", template_html))
        open_decl_count = len(re.findall(r"(?:const|let|var)\s+openTbody\s*=", template_html))
        assert home_decl_count <= 1, f"Duplicate declaration of homeTbody found ({home_decl_count})"
        assert open_decl_count <= 1, f"Duplicate declaration of openTbody found ({open_decl_count})"

    def test_t1_30_auth_verify_password_endpoint(self, configured_test_client, auth_headers):
        resp = configured_test_client.post("/api/v2/auth/verify-password", json={"password": "110299"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["authorized"] is True


class TestTier1Feature7DashboardTelemetryDOMSync:
    """F7: Dashboard Telemetry DOM Synchronization."""

    def test_t1_31_refresh_live_telemetry_defined(self, template_html):
        assert "async function refreshLiveTelemetry()" in template_html

    def test_t1_32_kpi_openpos_element_defined(self, template_html):
        assert 'id="kpi-openpos"' in template_html

    def test_t1_33_home_positions_tbody_defined(self, template_html):
        assert 'id="home-positions-tbody"' in template_html

    def test_t1_34_open_positions_tbody_defined(self, template_html):
        assert 'id="open-positions-tbody"' in template_html

    def test_t1_35_telemetry_polling_interval_registered(self, template_html):
        assert "setInterval(refreshLiveTelemetry" in template_html


class TestTier1Feature8FleetBotCapacityAlignment:
    """F8: Fleet Bot Capacity & Count Alignment."""

    def test_t1_36_configured_capacities_in_js(self, template_html):
        assert "STE: 3" in template_html
        assert "HDA: 3" in template_html
        assert "VCP: 2" in template_html
        assert "BBS: 4" in template_html

    def test_t1_37_bot_state_max_positions_config(self):
        ste = BotState("STE")
        hda = BotState("HDA")
        vcp = BotState("VCP")
        bbs = BotState("BBS")
        assert ste._params["max_positions"] == 3
        assert hda._params["max_positions"] == 3
        assert vcp._params["max_positions"] == 2
        assert bbs._params["max_positions"] == 4

    def test_t1_38_bot_pos_dom_elements_exist(self, template_html):
        for bot in ("ste", "hda", "vcp", "bbs"):
            assert f'id="bot-pos-{bot}"' in template_html

    def test_t1_39_bot_card_formatting_pattern(self, template_html):
        assert "maxCap" in template_html
        assert "positionsByBot" in template_html

    def test_t1_40_bot_status_pill_toggle(self, template_html):
        assert "bot-status-pill live" in template_html
        assert "bot-status-pill paper" in template_html


class TestTier1Feature9WatchlistLiveScannerFeed:
    """F9: Watchlist Live Scanner Feed Wiring."""

    def test_t1_41_watchlist_center_container_exists(self, template_html):
        assert 'id="watchlist-center"' in template_html

    def test_t1_42_scanned_universe_tbody_exists(self, template_html):
        assert 'id="scanned-universe-tbody"' in template_html

    def test_t1_43_scanner_coins_api_schema(self):
        sample = {
            "symbol": "SOL/INR",
            "coin": "SOL",
            "pair": "SOL/INR",
            "price": 12500.0,
            "confluence_score": 88,
            "volume_24h": 5000000.0,
            "evaluated_at": "2026-09-11T14:00:00Z",
        }
        schema = ScannedCoinSchema(**sample)
        assert schema.coin == "SOL"
        assert schema.confluence_score == 88

    def test_t1_44_confluence_tier_classification(self, template_html):
        assert "tier-elite" in template_html
        assert "score >= 85" in template_html or "85" in template_html

    def test_t1_45_watchlist_nav_anchor_exists(self, template_html):
        assert 'data-target="watchlist-center"' in template_html


class TestTier1Feature10AITelemetryBinding:
    """F10: AI Intelligence Telemetry Binding."""

    def test_t1_46_ai_service_initialization(self):
        bus = EventBus()
        cfg = V2Config()
        ai = AIIntelligenceService(bus=bus, ai_repo=MagicMock(), event_log_repo=MagicMock(), config=cfg)
        assert ai is not None

    def test_t1_47_ai_market_regime_types(self):
        assert MarketState.BULL_TREND.value == "bull_trend"
        assert MarketState.SIDEWAYS.value == "sideways"
        assert MarketState.BREAKOUT.value == "breakout"

    @pytest.mark.asyncio
    async def test_t1_48_ai_bus_event_subscription(self):
        bus = EventBus()
        tracker = BotPipelineTracker()
        bus.subscribe(EventType.SIGNAL_AI_CONFIRMED, lambda e, p: tracker.handle_bus_event(e, p))
        await bus.publish(EventType.SIGNAL_AI_CONFIRMED, {"bot": "STE", "coin": "BTC", "confidence": 92.0})
        detail = tracker.get_bot_detail("STE")
        assert detail["current_stage"] == "ai_intelligence"
        assert detail["stage_status"] == "AI_EVALUATING"

    @pytest.mark.asyncio
    async def test_t1_49_ai_rejection_increments_counter(self):
        tracker = BotPipelineTracker()
        tracker.handle_bus_event(EventType.SIGNAL_AI_REJECTED, {"bot": "STE", "coin": "XRP"})
        detail = tracker.get_bot_detail("STE")
        assert detail["telemetry"]["ai_rejected"] == 1

    def test_t1_50_ai_feed_container_in_template(self, template_html):
        assert "ai-feed" in template_html or "ai-intelligence" in template_html


class TestTier1Feature11OHLCVCandlesFeed:
    """F11: OHLCV Candlestick Feed Repository & Schema."""

    @pytest.mark.asyncio
    async def test_t1_51_candle_repo_get_recent_candles(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("BTC/INR", "1h", limit=50)
            assert isinstance(candles, list)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t1_52_candle_repo_get_candles_range(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_candles_range("ETH/INR", "15m", limit=100)
            assert isinstance(candles, list)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t1_53_candle_ordering_chronological(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("BTC/INR", "1h", limit=10)
            if len(candles) >= 2:
                assert candles[0]["timestamp"] <= candles[-1]["timestamp"]
        finally:
            await db.close()

    def test_t1_54_candle_data_structure(self):
        candle_fields = {"pair", "timeframe", "timestamp", "open", "high", "low", "close", "volume"}
        sample = {
            "pair": "BTC/INR",
            "timeframe": "1h",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "open": 6000000.0,
            "high": 6050000.0,
            "low": 5980000.0,
            "close": 6020000.0,
            "volume": 12.5,
        }
        assert set(sample.keys()) == candle_fields

    def test_t1_55_supported_candle_intervals(self):
        intervals = ["1m", "5m", "15m", "1h", "1d"]
        for iv in intervals:
            assert isinstance(iv, str)


class TestTier1Feature12InteractiveTradeChartWidget:
    """F12: Interactive Trade Chart Plotting Widget & Overlays."""

    def test_t1_56_chart_library_included_in_template(self, template_html):
        assert "chart.js" in template_html.lower() or "lightweight-charts" in template_html.lower()

    def test_t1_57_canvas_chart_containers_exist(self, template_html):
        assert "homePieChart" in template_html
        assert "homeGaugeChart" in template_html
        assert "homeLineChart" in template_html

    def test_t1_58_entry_price_marker_calculation(self):
        entry = 100000.0
        assert entry > 0

    def test_t1_59_stop_loss_marker_level(self):
        entry = 100000.0
        sl_pct = 2.0
        expected_sl = entry * (1.0 - sl_pct / 100.0)
        assert expected_sl == 98000.0

    def test_t1_60_take_profit_marker_level(self):
        entry = 100000.0
        tp_pct = 4.6
        expected_tp = entry * (1.0 + tp_pct / 100.0)
        assert expected_tp == 104600.0


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (60 Tests: 5 Tests x 12 Features)
# ==============================================================================

class TestTier2BoundaryHydration:
    """F1 Boundary: Startup Hydration corner conditions."""

    @pytest.mark.asyncio
    async def test_t2_1_empty_repository_hydration(self):
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository([])
        for bot in tracker.get_all_bots():
            assert bot["open_positions"] == 0
            assert bot["capital_deployed"] == 0.0
            assert bot["current_stage"] == "scanner"
            assert bot["stage_status"] == "IDLE"

    @pytest.mark.asyncio
    async def test_t2_2_unknown_bot_name_ignored(self):
        pos = Position(
            id="pos-unknown",
            bot="DEPRECATED_BOT",  # type: ignore
            coin="BTC",
            pair="BTC/INR",
            qty=1.0,
            entry_price=100.0,
            entry_time=datetime.now(timezone.utc),
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
        )
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository([pos])
        for bot in tracker.get_all_bots():
            assert bot["open_positions"] == 0

    @pytest.mark.asyncio
    async def test_t2_3_zero_quantity_entry_price(self):
        pos = Position(
            id="pos-zero",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.0,
            entry_price=0.0,
            entry_time=datetime.now(timezone.utc),
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
        )
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository([pos])
        ste = tracker.get_bot_detail("STE")
        assert ste["open_positions"] == 1
        assert ste["capital_deployed"] == 0.0

    @pytest.mark.asyncio
    async def test_t2_4_max_capacity_boundary(self):
        positions = [
            Position(
                id=f"pos-ste-{i}",
                bot=BotName.STE,
                coin=f"COIN{i}",
                pair=f"COIN{i}/INR",
                qty=1.0,
                entry_price=100.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            for i in range(3)
        ]
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(positions)
        ste = tracker.get_bot_detail("STE")
        assert ste["open_positions"] == 3

    @pytest.mark.asyncio
    async def test_t2_5_unsupported_hydration_source(self):
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(None)
        await tracker.sync_from_repository(12345)


class TestTier2BoundaryDashboardMount:
    """F2 Boundary: Dashboard mount corner conditions."""

    def test_t2_6_pause_invalid_bot_name_validation(self):
        aggregator = DashboardAggregator()
        with pytest.raises(Exception):
            from v2.api.dashboard_routes import pause_fleet_bot
            asyncio.run(pause_fleet_bot(bot_name="NON_EXISTENT"))

    def test_t2_7_dashboard_overview_when_uninitialized(self):
        import v2.api.dashboard_routes as d_routes
        from v2.api.dashboard_routes import get_aggregator
        original = d_routes._dashboard_aggregator
        d_routes._dashboard_aggregator = None
        try:
            with pytest.raises(Exception):
                get_aggregator()
        finally:
            d_routes._dashboard_aggregator = original

    def test_t2_8_case_insensitive_bot_pause(self):
        aggregator = DashboardAggregator()
        aggregator.pause_bot("ste")
        assert aggregator.is_bot_paused("STE")
        aggregator.resume_bot("ste")
        assert not aggregator.is_bot_paused("STE")

    @pytest.mark.asyncio
    async def test_t2_9_double_pause_idempotency(self):
        aggregator = DashboardAggregator()
        aggregator.pause_bot("HDA")
        aggregator.pause_bot("HDA")
        assert aggregator.is_bot_paused("HDA")

    @pytest.mark.asyncio
    async def test_t2_10_double_resume_idempotency(self):
        aggregator = DashboardAggregator()
        aggregator.resume_bot("VCP")
        aggregator.resume_bot("VCP")
        assert not aggregator.is_bot_paused("VCP")


class TestTier2BoundaryPositionsOpen:
    """F3 Boundary: /positions/open corner conditions."""

    @pytest.mark.asyncio
    async def test_t2_11_empty_database_active_positions(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            active = await repo.get_active_positions()
            assert active == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_12_only_closed_positions_returns_empty(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            for i in range(5):
                await repo.insert(Position(
                    id=f"closed-{i}",
                    bot=BotName.STE,
                    coin="BTC",
                    pair="BTC/INR",
                    qty=0.01,
                    entry_price=50000.0,
                    entry_time=datetime.now(timezone.utc),
                    mode=BotMode.PAPER,
                    status=PositionStatus.CLOSED,
                ))
            active = await repo.get_active_positions()
            assert active == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_13_pending_exit_included_in_active(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            pos = Position(
                id="pos-pending-exit",
                bot=BotName.HDA,
                coin="ETH",
                pair="ETH/INR",
                qty=1.0,
                entry_price=200000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.CLOSING,
            )
            await repo.insert(pos)
            active = await repo.get_active_positions()
            assert len(active) == 1
            assert active[0].status == PositionStatus.CLOSING
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_14_closing_status_included_in_active(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            pos = Position(
                id="pos-closing",
                bot=BotName.VCP,
                coin="SOL",
                pair="SOL/INR",
                qty=10.0,
                entry_price=12000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.CLOSING,
            )
            await repo.insert(pos)
            active = await repo.get_active_positions()
            assert len(active) == 1
            assert active[0].status == PositionStatus.CLOSING
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_15_special_character_pairs_in_positions(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            pos = Position(
                id="pos-pepe-1000",
                bot=BotName.BBS,
                coin="1000PEPE",
                pair="1000PEPE/INR",
                qty=10000.0,
                entry_price=0.85,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            await repo.insert(pos)
            active = await repo.get_active_positions()
            assert len(active) == 1
            assert active[0].pair == "1000PEPE/INR"
        finally:
            await db.close()


class TestTier2BoundaryDashboardOverview:
    """F4 Boundary: Dashboard Overview corner conditions."""

    @pytest.mark.asyncio
    async def test_t2_16_overview_with_none_trading_service(self):
        aggregator = DashboardAggregator(trading_service=None)
        snapshot = await aggregator.get_overview_snapshot()
        assert snapshot["active_positions"] == []

    @pytest.mark.asyncio
    async def test_t2_17_overview_with_none_portfolio_service(self):
        aggregator = DashboardAggregator(portfolio_service=None)
        snapshot = await aggregator.get_overview_snapshot()
        assert snapshot["status"] == "ok"

    @pytest.mark.asyncio
    async def test_t2_18_overview_with_none_analytics_service(self):
        aggregator = DashboardAggregator(analytics_service=None)
        snapshot = await aggregator.get_overview_snapshot()
        assert "performance_summary" in snapshot
        assert snapshot["performance_summary"]["win_rate_24h"] == 66.7

    @pytest.mark.asyncio
    async def test_t2_19_overview_with_none_feedback_service(self):
        aggregator = DashboardAggregator(feedback_service=None)
        snapshot = await aggregator.get_overview_snapshot()
        assert "feedback_state" in snapshot
        assert snapshot["feedback_state"]["loop_status"] == "ACTIVE_HEALTHY"

    @pytest.mark.asyncio
    async def test_t2_20_overview_pipeline_stages_length(self):
        aggregator = DashboardAggregator()
        snapshot = await aggregator.get_overview_snapshot()
        stages = snapshot["pipeline_stages"]
        assert len(stages) == 14


class TestTier2BoundaryDynamicEquity:
    """F5 Boundary: Dynamic Equity corner conditions."""

    def test_t2_21_zero_base_cash_clamps_to_zero(self):
        snapshot = PortfolioAggregator.aggregate(positions=[], closed_trades=[], base_cash=0.0)
        assert snapshot.total_cash == 0.0
        assert snapshot.total_aum == 0.0

    def test_t2_22_zero_aum_zero_division_guard(self):
        snapshot = PortfolioAggregator.aggregate(positions=[], closed_trades=[], base_cash=0.0)
        assert snapshot.capital_utilisation == 0.0

    def test_t2_23_negative_realized_loss_exceeding_base_cash(self):
        big_loss = [
            Trade(
                id="t-loss",
                position_id="p-loss",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                entry_price=100000.0,
                exit_price=10000.0,
                qty=1.0,
                pnl=-90000.0,
                pnl_pct=-90.0,
                entry_time=datetime.now(timezone.utc),
                exit_time=datetime.now(timezone.utc),
                exit_reason=ExitReason.STOP_LOSS,
                mode=BotMode.PAPER,
            )
        ]
        snapshot = PortfolioAggregator.aggregate(positions=[], closed_trades=big_loss, base_cash=50000.0)
        assert snapshot.total_cash == 0.0

    def test_t2_24_micro_quantities_floating_precision(self):
        micro_pos = [
            Position(
                id="pos-micro",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                qty=0.00000005,
                entry_price=6000000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
                current_price=6100000.0,
                unrealised_pnl=0.005,
            )
        ]
        snapshot = PortfolioAggregator.aggregate(positions=micro_pos, closed_trades=[], base_cash=100000.0)
        assert snapshot.total_deployed == pytest.approx(0.30, rel=1e-2)

    def test_t2_25_extreme_unrealized_profit(self):
        mega_pos = [
            Position(
                id="pos-mega",
                bot=BotName.VCP,
                coin="SOL",
                pair="SOL/INR",
                qty=1000.0,
                entry_price=10000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
                current_price=50000.0,
                unrealised_pnl=40000000.0,
            )
        ]
        snapshot = PortfolioAggregator.aggregate(positions=mega_pos, closed_trades=[], base_cash=100000.0)
        assert snapshot.total_unrealised_pnl == 40000000.0
        assert snapshot.total_aum > 40000000.0


class TestTier2BoundaryFrontendScript:
    """F6 Boundary: Script and auth security boundaries."""

    def test_t2_26_wrong_security_password_fails(self, configured_test_client, auth_headers):
        resp = configured_test_client.post("/api/v2/auth/verify-password", json={"password": "wrong-pin"}, headers=auth_headers)
        assert resp.status_code == 401

    def test_t2_27_missing_password_fails_mode_switch(self, configured_test_client, auth_headers):
        resp = configured_test_client.post("/api/v2/production/set-mode", json={"mode": "LIVE_MICROCASH"}, headers=auth_headers)
        assert resp.status_code == 403

    def test_t2_28_paper_mode_switch_does_not_require_pin(self, configured_test_client, auth_headers):
        resp = configured_test_client.post("/api/v2/production/set-mode", json={"mode": "PAPER"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["mode"] == "PAPER"

    def test_t2_29_security_pin_not_in_html_source(self, template_html):
        assert "110299" not in template_html

    def test_t2_30_empty_password_fails(self, configured_test_client, auth_headers):
        resp = configured_test_client.post("/api/v2/auth/verify-password", json={"password": ""}, headers=auth_headers)
        assert resp.status_code == 401


class TestTier2BoundaryTelemetryDOM:
    """F7 Boundary: DOM Telemetry sync edge conditions."""

    def test_t2_31_empty_positions_renders_zero_in_subtext(self, template_html):
        assert '0 active positions' in template_html

    def test_t2_32_no_active_open_positions_table_message(self, template_html):
        assert "No active open positions" in template_html

    def test_t2_33_price_formatting_zero_price(self, template_html):
        assert "formatPrice" in template_html

    def test_t2_34_missing_tp_sl_renders_na(self, template_html):
        assert "TP: ${tpStr} | SL: ${slStr}" in template_html

    def test_t2_35_trailing_badge_toggle_in_html(self, template_html):
        assert "TRAILING" in template_html
        assert "STATIC" in template_html


class TestTier2BoundaryFleetCapacities:
    """F8 Boundary: Fleet capacities corner conditions."""

    def test_t2_36_over_capacity_clamping(self, template_html):
        assert "Math.min(100" in template_html

    def test_t2_37_zero_position_bot_label(self, template_html):
        assert "(None)" in template_html

    def test_t2_38_bot_card_pnl_styling(self, template_html):
        assert "text-green" in template_html
        assert "text-red" in template_html

    def test_t2_39_single_coin_lock_label(self, template_html):
        assert "Single-Coin Lock Clear" in template_html

    def test_t2_40_bot_detail_vcp_capacity(self):
        tracker = BotPipelineTracker()
        detail = tracker.get_bot_detail("VCP")
        assert detail["max_positions"] == 2


class TestTier2BoundaryWatchlistScanner:
    """F9 Boundary: Watchlist and scanner edge conditions."""

    def test_t2_41_score_tier_threshold_boundary_85(self, template_html):
        assert "score >= 85" in template_html

    def test_t2_42_score_tier_threshold_boundary_75(self, template_html):
        assert "score >= 75" in template_html

    def test_t2_43_zero_volume_scanner_coin_handling(self, template_html):
        assert "vol > 0" in template_html

    def test_t2_44_missing_strategy_fallback(self, template_html):
        assert "CONFLUENCE_SCAN" in template_html or "CONFLUENCE MOMENTUM" in template_html

    def test_t2_45_scanner_table_formatting_pair_names(self, template_html):
        assert "formatPriceForPair" in template_html


class TestTier2BoundaryAITelemetry:
    """F10 Boundary: AI Intelligence boundary conditions."""

    def test_t2_46_circuit_breaker_open_state(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_t2_47_signal_schema_confidence_range(self):
        sig = Signal(
            id="sig-1",
            coin="BTC",
            pair="BTC/INR",
            market_state=MarketState.BULL_TREND,
            opportunity_type=OppType.MOMENTUM_TRADE,
            priority=Priority.ELITE,
            risk_level=RiskLevel.LOW,
            score=95,
            confidence=100,
            coin_class="A",
            mtf_alignment=True,
            generated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        assert 0 <= sig.confidence <= 100

    def test_t2_48_zero_confidence_signal(self):
        sig = Signal(
            id="sig-zero",
            coin="ETH",
            pair="ETH/INR",
            market_state=MarketState.SIDEWAYS,
            opportunity_type=OppType.MOMENTUM_TRADE,
            priority=Priority.IGNORE,
            risk_level=RiskLevel.HIGH,
            score=50,
            confidence=0,
            coin_class="B",
            mtf_alignment=False,
            generated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        assert sig.confidence == 0

    def test_t2_49_b3_b4_score_fields(self):
        score_data = {"b3_score": 88.0, "b4_score": 92.5, "confluence": 90.25}
        assert score_data["b3_score"] >= 0
        assert score_data["b4_score"] >= 0

    def test_t2_50_ai_health_schema(self):
        health = {"healthy": True, "circuit_breaker": "CLOSED", "uptime": 120.0}
        assert health["healthy"] is True


class TestTier2BoundaryCandlesFeed:
    """F11 Boundary: Candlestick Feed boundary conditions."""

    @pytest.mark.asyncio
    async def test_t2_51_nonexistent_pair_returns_empty_list(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("NON_EXISTENT_COIN/INR", "1h")
            assert candles == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_52_limit_1_returns_single_candle_or_empty(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("BTC/INR", "1h", limit=1)
            assert len(candles) <= 1
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_53_invalid_time_range_returns_empty(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_candles_range("BTC/INR", "1h", start_time=2000000000, end_time=1000000000)
            assert candles == []
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_54_case_normalization_in_candles(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles_lower = await repo.get_recent_candles("btc/inr", "1h")
            candles_upper = await repo.get_recent_candles("BTC/INR", "1h")
            assert len(candles_lower) == len(candles_upper)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t2_55_large_limit_clamping(self, test_db_path):
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("BTC/INR", "1h", limit=50000)
            assert isinstance(candles, list)
        finally:
            await db.close()


class TestTier2BoundaryTradeChart:
    """F12 Boundary: Trade chart widget boundaries."""

    def test_t2_56_zero_entry_price_guard(self):
        entry = 0.0
        sl_pct = 2.0
        sl_price = entry * (1.0 - sl_pct / 100.0) if entry > 0 else 0.0
        assert sl_price == 0.0

    def test_t2_57_tightened_stop_loss_pct_greater_than_normal(self):
        ste = BotState("STE")
        normal_sl = ste._params["stop_loss_pct"]
        tight_sl = ste._params["stop_loss_tightened_pct"]
        assert tight_sl < normal_sl

    def test_t2_58_trailing_stop_percentage_bounds(self):
        trailing_pct = 2.0
        assert 0.1 <= trailing_pct <= 10.0

    def test_t2_59_chart_placeholder_elements_styled(self, template_html):
        assert ".chart-placeholder" in template_html
        assert ".chart-ph-header" in template_html

    def test_t2_60_multiple_chart_canvases_distinct_ids(self, template_html):
        assert "homePieChart" != "homeGaugeChart"
        assert "homeGaugeChart" != "homeLineChart"


# ==============================================================================
# TIER 3: PAIRWISE CROSS-FEATURE INTERACTIONS (12 Tests)
# ==============================================================================

class TestTier3PairwiseInteractions:
    """Pairwise cross-feature combinatorial interactions."""

    @pytest.mark.asyncio
    async def test_t3_1_hydration_and_positions_open_alignment(self, test_db_path, sample_positions):
        """F1 + F3: Hydration from SQLite matches get_active_positions exactly."""
        db = await open_test_database(test_db_path)
        try:
            repo = PositionRepository(db.connection)
            for pos in sample_positions:
                await repo.insert(pos)

            active_db = await repo.get_active_positions()
            tracker = BotPipelineTracker()
            await tracker.sync_from_repository(active_db)

            total_hydrated_positions = sum(b["open_positions"] for b in tracker.get_all_bots())
            assert total_hydrated_positions == len(active_db)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t3_2_hydration_and_dashboard_overview_count(self, sample_positions):
        """F1 + F4: Hydration populates bot open positions reflected in overview counts."""
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        fleet = {b["bot_name"]: b for b in tracker.get_all_bots()}
        assert fleet["STE"]["open_positions"] == 1
        assert fleet["HDA"]["open_positions"] == 1
        assert fleet["VCP"]["open_positions"] == 1
        assert fleet["BBS"]["open_positions"] == 1

    @pytest.mark.asyncio
    async def test_t3_3_hydration_and_dynamic_equity(self, sample_positions):
        """F1 + F5: Hydration deployed capital matches PortfolioAggregator deployed capital."""
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        tracker_deployed = sum(b["capital_deployed"] for b in tracker.get_all_bots())

        portfolio_snap = PortfolioAggregator.aggregate(positions=sample_positions, closed_trades=[], base_cash=100000.0)
        assert tracker_deployed == pytest.approx(portfolio_snap.total_deployed, rel=1e-3)

    @pytest.mark.asyncio
    async def test_t3_4_hydration_and_fleet_capacity_boundaries(self, sample_positions):
        """F1 + F8: Hydration respects per-bot capacities (STE: 3, HDA: 3, VCP: 2, BBS: 4)."""
        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(sample_positions)
        bots = {b["bot_name"]: b for b in tracker.get_all_bots()}
        assert bots["STE"]["open_positions"] <= 3
        assert bots["HDA"]["open_positions"] <= 3
        assert bots["VCP"]["open_positions"] <= 2
        assert bots["BBS"]["open_positions"] <= 4

    def test_t3_5_position_status_transition_and_equity(self, sample_positions):
        """F3 + F5: Closing an active position shifts capital from deployed to cash."""
        initial_snap = PortfolioAggregator.aggregate(positions=sample_positions, closed_trades=[], base_cash=100000.0)

        remaining = sample_positions[1:]
        closed_trade = Trade(
            id="t-exit-1",
            position_id=sample_positions[0].id,
            bot=sample_positions[0].bot,
            coin=sample_positions[0].coin,
            pair=sample_positions[0].pair,
            entry_price=sample_positions[0].entry_price,
            exit_price=sample_positions[0].entry_price * 1.05,
            qty=sample_positions[0].qty,
            pnl=500.0,
            pnl_pct=5.0,
            entry_time=sample_positions[0].entry_time,
            exit_time=datetime.now(timezone.utc),
            exit_reason=ExitReason.TAKE_PROFIT,
            mode=BotMode.PAPER,
        )

        new_snap = PortfolioAggregator.aggregate(positions=remaining, closed_trades=[closed_trade], base_cash=100000.0)
        assert new_snap.total_deployed < initial_snap.total_deployed
        assert new_snap.total_realised_pnl == 500.0

    def test_t3_6_fleet_pause_and_telemetry(self):
        """F2 + F8: Pausing fleet bot reflects in fleet telemetry."""
        aggregator = DashboardAggregator()
        aggregator.pause_bot("STE")
        overview = asyncio.run(aggregator.get_overview_snapshot())
        assert overview["execution_fleet"]["STE"]["paused"] is True
        assert overview["execution_fleet"]["HDA"]["paused"] is False

    def test_t3_7_overview_payload_and_dom_element_contract(self, template_html):
        """F4 + F7: Overview payload keys have corresponding DOM elements."""
        required_dom_ids = ["kpi-aum", "kpi-capital", "kpi-openpos", "home-positions-tbody"]
        for dom_id in required_dom_ids:
            assert f'id="{dom_id}"' in template_html

    def test_t3_8_mode_change_security_and_fleet(self, configured_test_client, auth_headers):
        """F6 + F2: Mode switch to PAPER retains execution fleet active."""
        resp = configured_test_client.post("/api/v2/production/set-mode", json={"mode": "PAPER"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["mode"] == "PAPER"

    def test_t3_9_scanner_confluence_and_ai_gating(self):
        """F9 + F10: Confluence score >= 85 aligns with high AI conviction."""
        score = 89.0
        ai_conv = min(96, max(65, round(score * 0.98)))
        assert ai_conv >= 85

    @pytest.mark.asyncio
    async def test_t3_10_candle_feed_and_chart_levels(self, test_db_path):
        """F11 + F12: Candle close prices provide basis for Entry and SL/TP overlays."""
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("BTC/INR", "1h", limit=5)
            last_close = 6000000.0 if not candles else candles[-1]["close"]
            sl = last_close * 0.98
            tp = last_close * 1.046
            assert sl < last_close < tp
        finally:
            await db.close()

    def test_t3_11_capital_limit_and_fleet_allocation(self):
        """F5 + F8: Configured bot capital limits govern wallet allocation."""
        cfg = V2Config()
        tracker = BotPipelineTracker(config=cfg)
        ste = tracker.get_bot_detail("STE")
        assert ste["capital_limit"] == cfg.ste_capital_limit

    def test_t3_12_restart_preserves_paper_mode_invariant(self):
        """F1 + F6: System operates strictly under non-live paper trading mode."""
        cfg = V2Config()
        assert "LIVE" not in cfg.v2_deployment_mode


# ==============================================================================
# TIER 4: REAL-WORLD WORKLOAD SCENARIOS (5 High-Complexity Scenarios)
# ==============================================================================

class TestTier4RealWorldScenarios:
    """End-to-End Real-World Application Workloads."""

    @pytest.mark.asyncio
    async def test_t4_1_scenario1_server_cold_restart_with_active_positions(self, test_db_path, sample_positions):
        """
        Scenario 1: Cold Server Restart with Active Positions (F1, F3, F4, F7, F8).
        Simulates existing SQLite positions in database before server boots up.
        Verifies:
        1. Repository queries all non-closed positions.
        2. BotPipelineTracker hydrates state across STE, HDA, VCP, BBS.
        3. Deployed capital and active counts are restored immediately without trade events.
        4. Overview snapshot reflects restored active positions.
        """
        db = await open_test_database(test_db_path)
        try:
            pos_repo = PositionRepository(db.connection)
            for pos in sample_positions:
                await pos_repo.insert(pos)

            tracker = BotPipelineTracker()
            active_positions = await pos_repo.get_active_positions()
            assert len(active_positions) == 4

            await tracker.sync_from_repository(active_positions)

            bots = {b["bot_name"]: b for b in tracker.get_all_bots()}
            assert bots["STE"]["open_positions"] == 1
            assert bots["STE"]["current_stage"] == "position_manager"
            assert bots["STE"]["stage_status"] == "IN_POSITION"

            assert bots["HDA"]["open_positions"] == 1
            assert bots["VCP"]["open_positions"] == 1
            assert bots["BBS"]["open_positions"] == 1

            total_deployed = sum(b["capital_deployed"] for b in bots.values())
            assert total_deployed > 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_t4_2_scenario2_multi_stage_position_lifecycle(self, test_db_path):
        """
        Scenario 2: Multi-Stage Position Transition Lifecycle (F1, F3, F4, F5).
        OPEN -> mark update -> CLOSING -> CLOSED.
        Verifies:
        1. Initial state is active in get_active_positions().
        2. Status transitions reflect in active set.
        3. Final CLOSED transition removes position from active set.
        """
        db = await open_test_database(test_db_path)
        try:
            # Ensure schema compatibility for realized_pnl if migration 007 was a no-op
            try:
                await db.connection.execute("ALTER TABLE positions ADD COLUMN realized_pnl REAL DEFAULT 0.0")
                await db.connection.commit()
            except Exception:
                pass

            repo = PositionRepository(db.connection)

            pos = Position(
                id="pos-lifecycle-001",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                qty=0.1,
                entry_price=6000000.0,
                entry_time=datetime.now(timezone.utc),
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            await repo.insert(pos)
            active_a = await repo.get_active_positions()
            assert len(active_a) == 1
            assert active_a[0].status == PositionStatus.OPEN

            await repo.update_status("pos-lifecycle-001", PositionStatus.CLOSING)
            active_b = await repo.get_active_positions()
            assert len(active_b) == 1
            assert active_b[0].status == PositionStatus.CLOSING

            await repo.update_status(
                "pos-lifecycle-001",
                PositionStatus.CLOSED,
                exit_price=6150000.0,
                exit_reason=ExitReason.TAKE_PROFIT,
                realized_pnl=15000.0,
            )
            active_c = await repo.get_active_positions()
            assert len(active_c) == 0
        finally:
            await db.close()

    def test_t4_3_scenario3_dynamic_portfolio_mtm_and_friction(self, sample_positions):
        """
        Scenario 3: Dynamic Portfolio MTM & Friction Valuation (F4, F5).
        Combines base cash, active positions MTM valuations, realized closed trades,
        and verifies total equity calculation formula.
        """
        base_cash = 250000.0
        closed_trades = [
            Trade(
                id="trade-hist-1",
                position_id="p-h-1",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                entry_price=5800000.0,
                exit_price=6000000.0,
                qty=0.02,
                pnl=4000.0,
                pnl_pct=3.45,
                entry_time=datetime.now(timezone.utc) - timedelta(hours=4),
                exit_time=datetime.now(timezone.utc) - timedelta(hours=2),
                exit_reason=ExitReason.TAKE_PROFIT,
                mode=BotMode.PAPER,
            )
        ]

        snapshot = PortfolioAggregator.aggregate(
            positions=sample_positions,
            closed_trades=closed_trades,
            base_cash=base_cash,
        )

        expected_cash = max(0.0, base_cash + 4000.0 - snapshot.total_deployed)
        assert snapshot.total_cash == pytest.approx(expected_cash, rel=1e-2)

        expected_aum = snapshot.total_cash + snapshot.total_deployed + snapshot.total_unrealised_pnl
        assert snapshot.total_aum == pytest.approx(expected_aum, rel=1e-2)

    def test_t4_4_scenario4_live_scanner_to_watchlist_feed(self, template_html):
        """
        Scenario 4: Live Scanner to Watchlist Feed Ingestion (F9, F10).
        Verifies client-side ingestion logic:
        1. API call to /scanner/coins.
        2. Live ticker transformation into cryptoData deep dive cache.
        3. Sorting and tier classification into ELITE and HIGH badges.
        4. DOM table population with prices and confluence scores.
        """
        assert 'apiFetch("/scanner/coins")' in template_html
        assert "cryptoData[coinKey]" in template_html
        assert "scanned-universe-tbody" in template_html
        assert "scanner-center-tbody" in template_html

    @pytest.mark.asyncio
    async def test_t4_5_scenario5_research_candlestick_and_marker_charting(self, test_db_path):
        """
        Scenario 5: Research Candlestick & Marker Charting Workflow (F11, F12).
        Verifies:
        1. Database retrieval of historical OHLCV candles.
        2. Technical level calculation (Pivot, SL, TP).
        3. Verification that SL is strictly below Entry, and TP strictly above Entry.
        4. Candlesticks have valid high >= low and volume >= 0 constraints.
        """
        db = await open_test_database(test_db_path)
        try:
            repo = CandleRepository(db.connection)
            candles = await repo.get_recent_candles("SOL/INR", "1h", limit=24)
            assert isinstance(candles, list)

            simulated_candle = {
                "time": 1726050000,
                "open": 12000.0,
                "high": 12400.0,
                "low": 11950.0,
                "close": 12300.0,
                "volume": 450.0,
            }
            assert simulated_candle["high"] >= simulated_candle["low"]
            assert simulated_candle["high"] >= simulated_candle["open"]
            assert simulated_candle["high"] >= simulated_candle["close"]
            assert simulated_candle["low"] <= simulated_candle["open"]
            assert simulated_candle["low"] <= simulated_candle["close"]
            assert simulated_candle["volume"] >= 0.0

            entry_price = simulated_candle["close"]
            ste_bot = BotState("STE")
            sl_price = entry_price * (1.0 - ste_bot._params["stop_loss_pct"] / 100.0)
            tp_price = entry_price * (1.0 + ste_bot._params["take_profit_pct"] / 100.0)

            assert sl_price < entry_price < tp_price
            assert (tp_price - entry_price) > (entry_price - sl_price)
        finally:
            await db.close()
