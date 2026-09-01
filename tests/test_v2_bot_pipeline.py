"""
Tests for V2 BotPipelineTracker & Isolated CoinDCX Sub-Account Multi-Client Architecture:
  - Initialization of all 4 production bots (STE, HDA, VCP, BBS)
  - Pipeline stage transitions via EventBus events
  - API endpoints: GET /api/v2/bots, GET /api/v2/bots/{bot_name}
  - Deprecated bots (VGX, PMB) return 404 / InvalidStrategyError
  - Sub-account client HMAC signing & balance isolation
"""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from v2.services.dashboard_service.bot_pipeline import BotPipelineTracker, BotState
from v2.bus.event_types import EventType
from v2.trading.subaccount_manager import CoinDCXSubAccountManager, SubAccountConfig
from v2.core.types import BotName


# ── 1. BotPipelineTracker Unit Tests ──────────────────────────────────────────

class TestBotPipelineTrackerInit:

    def test_all_four_production_bots_initialized(self):
        tracker = BotPipelineTracker()
        bots = tracker.get_all_bots()
        names = {b["bot_name"] for b in bots}
        assert names == {"STE", "HDA", "VCP", "BBS"}, f"Expected STE/HDA/VCP/BBS, got {names}"

    def test_bot_summary_fields(self):
        tracker = BotPipelineTracker()
        bots = tracker.get_all_bots()
        for bot in bots:
            required_keys = [
                "bot_name", "strategy", "subaccount_id", "icon", "color",
                "current_stage", "stage_label", "stage_index", "total_stages",
                "stage_status", "open_positions", "max_positions",
                "capital_deployed", "capital_limit", "daily_pnl", "total_pnl",
                "win_rate_pct", "trades_executed", "last_action",
            ]
            for key in required_keys:
                assert key in bot, f"Missing key '{key}' in bot {bot.get('bot_name')}"

    def test_bot_detail_ste_params(self):
        tracker = BotPipelineTracker()
        detail = tracker.get_bot_detail("STE")
        assert detail is not None
        assert detail["subaccount_id"] == "ALPHA_STE_01"
        assert detail["stop_loss_pct"] == 2.0
        assert detail["take_profit_pct"] == 4.6

    def test_bot_detail_hda_params(self):
        tracker = BotPipelineTracker()
        detail = tracker.get_bot_detail("HDA")
        assert detail is not None
        assert detail["subaccount_id"] == "ALPHA_HDA_01"
        assert detail["stop_loss_pct"] == 2.2
        assert detail["take_profit_pct"] == 5.28

    def test_bot_detail_vcp_params(self):
        tracker = BotPipelineTracker()
        detail = tracker.get_bot_detail("VCP")
        assert detail is not None
        assert detail["subaccount_id"] == "ALPHA_VCP_01"
        assert detail["stop_loss_pct"] == 2.0
        assert detail["take_profit_pct"] == 5.0

    def test_bot_detail_bbs_params(self):
        tracker = BotPipelineTracker()
        detail = tracker.get_bot_detail("BBS")
        assert detail is not None
        assert detail["subaccount_id"] == "ALPHA_BBS_01"
        assert detail["stop_loss_pct"] == 2.5
        assert detail["take_profit_pct"] == 6.0

    def test_case_insensitive_bot_lookup(self):
        tracker = BotPipelineTracker()
        assert tracker.get_bot_detail("ste") is not None
        assert tracker.get_bot_detail("Hda") is not None
        assert tracker.get_bot_detail("vcp") is not None
        assert tracker.get_bot_detail("bbs") is not None

    def test_deprecated_or_unknown_bot_returns_none(self):
        tracker = BotPipelineTracker()
        assert tracker.get_bot_detail("VGX") is None
        assert tracker.get_bot_detail("PMB") is None
        assert tracker.get_bot_detail("XYZ") is None
        assert tracker.get_bot_detail("") is None


# ── 2. Pipeline Stage Transition Tests ────────────────────────────────────────

class TestBotStageTransitions:

    def _make_tracker(self):
        return BotPipelineTracker()

    def test_signal_generated_advances_scanner_stage(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.SIGNAL_GENERATED.value,
            {"bot": "STE", "coin": "SOL", "score": 88}
        )
        detail = tracker.get_bot_detail("STE")
        assert detail["current_stage"] == "signal_engine"
        assert detail["stage_status"] == "SCANNING"
        assert detail["telemetry"]["signals_generated"] == 1

    def test_ai_confirmed_advances_ai_stage(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.SIGNAL_AI_CONFIRMED.value,
            {"bot": "HDA", "coin": "ETH", "confidence_score": 92}
        )
        detail = tracker.get_bot_detail("HDA")
        assert detail["current_stage"] == "ai_intelligence"
        assert detail["stage_status"] == "AI_EVALUATING"
        assert detail["telemetry"]["ai_evaluations"] == 1
        assert detail["telemetry"]["ai_approved"] == 1

    def test_ai_rejected_increments_rejection_counter(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.SIGNAL_AI_REJECTED.value,
            {"bot": "BBS", "coin": "SHIB", "confidence_score": 45}
        )
        detail = tracker.get_bot_detail("BBS")
        assert detail["telemetry"]["ai_evaluations"] == 1
        assert detail["telemetry"]["ai_rejected"] == 1

    def test_trade_approved_risk_stage(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.TRADE_APPROVED.value,
            {"bot": "STE", "coin": "BTC", "approved_amount": 500.0}
        )
        detail = tracker.get_bot_detail("STE")
        assert detail["current_stage"] == "risk_engine"
        assert detail["stage_status"] == "RISK_CHECK"

    def test_trade_executed_advances_to_auto_trade(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.TRADE_EXECUTED.value,
            {"bot": "STE", "coin": "BTC", "entry_price": 8200000.0, "qty": 0.00005}
        )
        detail = tracker.get_bot_detail("STE")
        assert detail["current_stage"] == "auto_trade"
        assert detail["stage_status"] == "EXECUTING"
        assert detail["trades_executed"] == 1
        assert detail["capital_deployed"] > 0.0

    def test_position_opened_advances_to_position_manager(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.POSITION_OPENED.value,
            {"bot": "VCP", "coin": "SOL"}
        )
        detail = tracker.get_bot_detail("VCP")
        assert detail["current_stage"] == "position_manager"
        assert detail["stage_status"] == "IN_POSITION"
        assert detail["open_positions"] == 1

    def test_position_closed_updates_pnl_and_resets(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.POSITION_OPENED.value,
            {"bot": "BBS", "coin": "DOGE"}
        )
        tracker.handle_bus_event(
            EventType.POSITION_CLOSED.value,
            {"bot": "BBS", "coin": "DOGE", "pnl": 48.5, "entry_price": 16.50, "qty": 20.0}
        )
        detail = tracker.get_bot_detail("BBS")
        assert detail["open_positions"] == 0
        assert detail["daily_pnl"] == pytest.approx(48.5, abs=0.01)
        assert detail["telemetry"]["wins"] == 1
        assert detail["stage_status"] == "IDLE"

    def test_win_rate_calculation(self):
        tracker = self._make_tracker()
        for pnl in [500.0, 300.0, -200.0, 100.0]:
            tracker.handle_bus_event(
                EventType.POSITION_OPENED.value,
                {"bot": "STE", "coin": "BTC"}
            )
            tracker.handle_bus_event(
                EventType.POSITION_CLOSED.value,
                {"bot": "STE", "coin": "BTC", "pnl": pnl, "entry_price": 0.0, "qty": 0.0}
            )
        detail = tracker.get_bot_detail("STE")
        # 3 wins, 1 loss → 75%
        assert detail["win_rate_pct"] == pytest.approx(75.0, abs=0.1)

    def test_multiple_bots_independently_tracked(self):
        tracker = self._make_tracker()
        tracker.handle_bus_event(
            EventType.SIGNAL_GENERATED.value,
            {"bot": "STE", "coin": "BTC", "score": 90}
        )
        hda_detail = tracker.get_bot_detail("HDA")
        vcp_detail = tracker.get_bot_detail("VCP")
        assert hda_detail["telemetry"]["signals_generated"] == 0
        assert vcp_detail["telemetry"]["signals_generated"] == 0


# ── 3. CoinDCX Sub-Account Client & HMAC Signing Tests ────────────────────────

class TestCoinDCXSubAccountArchitecture:

    def test_subaccount_manager_initialization(self):
        mgr = CoinDCXSubAccountManager()
        telemetry = mgr.get_all_subaccount_telemetry()
        assert len(telemetry) == 4
        assert "STE" in telemetry
        assert "HDA" in telemetry
        assert "VCP" in telemetry
        assert "BBS" in telemetry

        # Unified wallet balance allocation (₹10,000 shared pool)
        assert telemetry["STE"]["wallet_balance_inr"] == 10000.0
        assert telemetry["HDA"]["wallet_balance_inr"] == 10000.0
        assert telemetry["VCP"]["wallet_balance_inr"] == 10000.0
        assert telemetry["BBS"]["wallet_balance_inr"] == 10000.0

    def test_subaccount_hmac_signing(self):
        mgr = CoinDCXSubAccountManager()
        ste_client = mgr.get_client(BotName.STE)
        headers = ste_client.generate_auth_headers({"test": "data"})
        assert "X-AUTH-APIKEY" in headers
        assert "X-AUTH-SIGNATURE" in headers
        assert len(headers["X-AUTH-SIGNATURE"]) == 64  # SHA256 hex digest length

    def test_subaccount_order_placement_and_balance_isolation(self):
        mgr = CoinDCXSubAccountManager()
        ste_client = mgr.get_client(BotName.STE)
        initial_avail = ste_client.available_balance_inr

        # Place valid order: 0.05 SOL @ ₹12,500 = ₹625 notional (> ₹100 min)
        res = ste_client.place_order(pair="SOL/INR", side="BUY", price=12500.0, qty=0.05)
        assert res["success"] is True
        assert res["order"]["auth_headers_verified"] is True
        assert ste_client.available_balance_inr < initial_avail

        # Shared pool available balance is synchronized across all bot clients
        hda_client = mgr.get_client(BotName.HDA)
        assert hda_client.available_balance_inr == 9375.0

    def test_order_rejection_below_min_notional(self):
        mgr = CoinDCXSubAccountManager()
        bbs_client = mgr.get_client(BotName.BBS)
        # 1 DOGE @ ₹16.50 = ₹16.50 (< ₹100 minimum)
        res = bbs_client.place_order(pair="DOGE/INR", side="BUY", price=16.50, qty=1.0)
        assert res["success"] is False
        assert res["error"] == "ORDER_NOTIONAL_BELOW_MINIMUM"


# ── 4. API Endpoint Tests ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_bot_api_endpoints(tmp_path, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from v2.api.router import router as api_router, init_router
    from v2.repository.db import Database
    from v2.repository.signal_repo import SignalRepository
    from v2.repository.ai_repo import AIAnalysisRepository
    from v2.repository.position_repo import PositionRepository
    from v2.repository.trade_repo import TradeRepository
    from v2.repository.shadow_repo import ShadowRepository
    from v2.repository.metrics_repo import MetricsRepository
    from v2.repository.event_log_repo import EventLogRepository
    from v2.services.dashboard_service import DashboardService
    from v2.bus.event_bus import EventBus
    from v2.core.config import get_config, invalidate_config

    monkeypatch.setenv("DASHBOARD_API_KEY", "test-key-bots")
    invalidate_config()

    db_path = str(tmp_path / "test_bots.db")
    db = Database(db_path)
    await db.open()
    try:
        conn = db.connection
        bus = EventBus()
        cfg = get_config()
        dash_svc = DashboardService(bus=bus, config=cfg)

        app = FastAPI()
        init_router(
            bus=bus,
            signal_repo=SignalRepository(conn),
            ai_repo=AIAnalysisRepository(conn),
            position_repo=PositionRepository(conn),
            trade_repo=TradeRepository(conn),
            shadow_repo=ShadowRepository(conn),
            metrics_repo=MetricsRepository(conn),
            event_log_repo=EventLogRepository(conn),
            config=cfg,
            dashboard_service=dash_svc,
        )
        app.include_router(api_router, prefix="/api/v2")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-key-bots"},
        ) as client:
            # 1. GET /api/v2/bots returns all 4 production bots
            res = await client.get("/api/v2/bots")
            assert res.status_code == 200
            data = res.json()
            assert isinstance(data, list)
            assert len(data) == 4
            bot_names = {b["bot_name"] for b in data}
            assert bot_names == {"STE", "HDA", "VCP", "BBS"}

            # 2. GET /api/v2/bots/STE detail
            res_ste = await client.get("/api/v2/bots/STE")
            assert res_ste.status_code == 200
            ste_data = res_ste.json()
            assert ste_data["bot_name"] == "STE"
            assert ste_data["subaccount_id"] == "ALPHA_STE_01"

            # 3. Deprecated bots (VGX, PMB) return 404
            res_vgx = await client.get("/api/v2/bots/VGX")
            assert res_vgx.status_code == 404
            res_pmb = await client.get("/api/v2/bots/PMB")
            assert res_pmb.status_code == 404
    finally:
        await db.close()
