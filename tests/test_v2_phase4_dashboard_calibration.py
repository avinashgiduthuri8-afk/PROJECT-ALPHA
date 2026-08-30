"""
PROJECT-ALPHA — Phase 4 Test Suite:
  - WebSocket Telemetry Stream Expansion (/ws/v2/feed)
  - FastAPI Analytics Endpoints (/api/v2/analytics/win-rates, /coins, /funnel)
  - Dynamic Win-Rate Feedback Calibration Worker
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config, get_config
from v2.core.types import MarketState, Priority, RiskLevel, Signal, OppType
from v2.services.dashboard_service.service import DashboardService, DashboardAnalyticsService
from v2.services.dashboard_service.websocket import WebSocketManager
from v2.services.scanner_service.calibration_worker import CalibrationWorker
from v2.services.scanner_service.confluence_engine import ConfluenceEngine
from v2.services.scanner_service.service import ScannerService
from v2.api.router import router as api_router, init_router
from v2.api.websocket import router as ws_router, init_websocket


def _make_test_signal(
    coin: str = "SOL",
    score: int = 90,
    priority: Priority = Priority.ELITE,
) -> Signal:
    now = datetime.now(timezone.utc)
    return Signal(
        id=f"sig_{coin}_1",
        coin=coin,
        pair=f"{coin}/INR",
        market_state=MarketState.BREAKOUT,
        opportunity_type=OppType.MOMENTUM_TRADE,
        priority=priority,
        risk_level=RiskLevel.LOW,
        score=score,
        confidence=90,
        coin_class="A",
        mtf_alignment=True,
        generated_at=now,
        expires_at=now,
    )


def _build_test_app(dash_svc: DashboardService, cfg: V2Config) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v2")
    app.include_router(ws_router)
    init_websocket(dash_svc.ws_manager, dashboard_service=dash_svc)
    init_router(
        config=cfg,
        dashboard_service=dash_svc,
    )
    return app


# ── 1. Analytics Service & Endpoints Tests ────────────────────────────────────

def test_dashboard_analytics_service_win_rates():
    analytics = DashboardAnalyticsService()
    res = analytics.get_win_rates()
    assert "time_horizons" in res
    assert "1h" in res["time_horizons"]
    assert "4h" in res["time_horizons"]
    assert "24h" in res["time_horizons"]
    assert "3d" in res["time_horizons"]
    assert "7d" in res["time_horizons"]
    assert "tier_accuracy" in res
    assert "overall_win_rate" in res


def test_dashboard_analytics_service_coin_performance():
    analytics = DashboardAnalyticsService()
    res = analytics.get_coin_performance()
    assert "total_coins" in res
    assert "coins" in res
    assert "best_performing" in res
    assert "worst_performing" in res
    assert isinstance(res["coins"], list)


def test_dashboard_analytics_service_funnel():
    analytics = DashboardAnalyticsService()
    res = analytics.get_funnel_metrics()
    assert "layers" in res
    assert len(res["layers"]) == 5
    assert res["dispatched_signals_count"] >= 0
    assert "final_conversion_pct" in res


# ── 2. Dynamic Calibration Worker Tests ───────────────────────────────────────

@pytest.mark.anyio
async def test_calibration_worker_tightens_on_low_win_rate():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    confluence = ConfluenceEngine(strict_threshold=85, max_signals=2)
    worker = CalibrationWorker(
        bus=bus,
        confluence_engine=confluence,
        interval_seconds=900,
        base_threshold=85,
        tightened_threshold=90,
    )

    # Mock low win-rate history (< 50%)
    mock_history = [
        {"timestamp": datetime.now(timezone.utc).isoformat(), "outcome": "loss", "return_pct": -2.0}
        for _ in range(10)
    ]
    mock_coins = {
        "DOGE": {"total_signals": 10, "win_rate_pct": 20.0, "avg_return_pct": -3.0},
        "BTC": {"total_signals": 10, "win_rate_pct": 80.0, "avg_return_pct": 2.0},
    }

    with patch("v2.services.scanner_service.calibration_worker._safe_load_json") as mock_load:
        def fake_load(path: Path):
            if "signal_history" in path.name:
                return mock_history
            if "coin_performance" in path.name:
                return mock_coins
            if "tier_accuracy" in path.name:
                return {"ELITE": {"total_signals": 10, "winning_signals": 0}}
            return None

        mock_load.side_effect = fake_load

        payload = await worker.run_calibration_cycle()
        assert payload["strict_threshold"] == 90
        assert payload["tightening_active"] is True
        assert confluence.strict_threshold == 90
        assert "DOGE" in confluence.coin_penalties
        assert confluence.coin_penalties["DOGE"] <= -15
        assert "BTC" not in confluence.coin_penalties
        assert bus.publish.called


@pytest.mark.anyio
async def test_calibration_worker_recovery_on_high_win_rate():
    confluence = ConfluenceEngine(strict_threshold=90, max_signals=2)
    worker = CalibrationWorker(
        confluence_engine=confluence,
        base_threshold=85,
        tightened_threshold=90,
    )

    # Mock high win-rate history (> 75%)
    mock_history = [
        {"timestamp": datetime.now(timezone.utc).isoformat(), "outcome": "win", "return_pct": 3.0}
        for _ in range(10)
    ]

    with patch("v2.services.scanner_service.calibration_worker._safe_load_json") as mock_load:
        def fake_load(path: Path):
            if "signal_history" in path.name:
                return mock_history
            return None

        mock_load.side_effect = fake_load

        payload = await worker.run_calibration_cycle()
        assert payload["strict_threshold"] == 85
        assert payload["tightening_active"] is False
        assert confluence.strict_threshold == 85


def test_confluence_engine_applies_coin_penalties():
    engine = ConfluenceEngine(strict_threshold=85, max_signals=2)
    engine.update_market_sentiment("BULLISH", "BULLISH", "RISK_ON", fear_greed=65)
    engine.coin_penalties = {"AVOID_COIN": -25}

    sig_good = _make_test_signal("BTC", score=95)
    sig_bad = _make_test_signal("AVOID_COIN", score=95)

    accepted, results = engine.evaluate_candidates(
        [{"coin": "BTC"}, {"coin": "AVOID_COIN"}],
        [sig_good, sig_bad],
    )

    assert any(s.coin == "BTC" for s in accepted)
    assert not any(s.coin == "AVOID_COIN" for s in accepted)
    bad_res = next(r for r in results if r.signal.coin == "AVOID_COIN")
    assert bad_res.accepted is False
    assert any("Calibration" in reason for reason in bad_res.rejection_reasons)


# ── 3. FastAPI Analytics REST Endpoints Integration ───────────────────────────

@pytest.mark.anyio
async def test_analytics_rest_api_endpoints():
    cfg = get_config()
    bus = MagicMock(spec=EventBus)
    dash_svc = DashboardService(bus=bus, config=cfg)
    app = _build_test_app(dash_svc, cfg)

    client = TestClient(app)
    headers = {"X-API-Key": cfg.dashboard_api_key}

    # 1. Win Rates Endpoint
    resp_wr = client.get("/api/v2/analytics/win-rates", headers=headers)
    assert resp_wr.status_code == 200
    data_wr = resp_wr.json()
    assert "time_horizons" in data_wr
    assert "tier_accuracy" in data_wr
    assert "overall_win_rate" in data_wr

    # 2. Coins Endpoint
    resp_coins = client.get("/api/v2/analytics/coins", headers=headers)
    assert resp_coins.status_code == 200
    data_coins = resp_coins.json()
    assert "total_coins" in data_coins
    assert "coins" in data_coins
    assert "best_performing" in data_coins

    # 3. Funnel Endpoint
    resp_funnel = client.get("/api/v2/analytics/funnel", headers=headers)
    assert resp_funnel.status_code == 200
    data_funnel = resp_funnel.json()
    assert "layers" in data_funnel
    assert len(data_funnel["layers"]) == 5
    assert "final_conversion_pct" in data_funnel


# ── 4. WebSocket Telemetry Stream Integration ─────────────────────────────────

@pytest.mark.anyio
async def test_websocket_feed_unauthorized_rejection():
    from v2.api.websocket import websocket_feed

    cfg = get_config()
    bus = MagicMock(spec=EventBus)
    dash_svc = DashboardService(bus=bus, config=cfg)
    init_websocket(dash_svc.ws_manager, dashboard_service=dash_svc)

    mock_ws = AsyncMock()
    mock_ws.headers = {}

    with patch("v2.api.websocket.get_config") as mock_cfg:
        cfg_obj = MagicMock()
        cfg_obj.dashboard_api_key = "secret-production-key"
        mock_cfg.return_value = cfg_obj

        await websocket_feed(mock_ws, api_key="wrong_key")
        assert mock_ws.close.called
        assert mock_ws.close.call_args[1]["code"] == 1008


@pytest.mark.anyio
async def test_websocket_feed_telemetry_snapshot():
    from v2.api.websocket import websocket_feed

    cfg = get_config()
    bus = MagicMock(spec=EventBus)
    dash_svc = DashboardService(bus=bus, config=cfg)
    init_websocket(dash_svc.ws_manager, dashboard_service=dash_svc)

    mock_ws = AsyncMock()
    mock_ws.headers = {"X-API-Key": cfg.dashboard_api_key}
    # Simulate first receiving ping, then close
    mock_ws.receive_text = AsyncMock(side_effect=["ping", "close"])

    await websocket_feed(mock_ws, api_key=None)

    assert mock_ws.accept.called
    assert mock_ws.send_text.called

    # Verify that one of the sent frames contains TELEMETRY_SNAPSHOT
    sent_frames = [call.args[0] for call in mock_ws.send_text.call_args_list if call.args]
    telemetry_frame = next((json.loads(f) for f in sent_frames if "TELEMETRY_SNAPSHOT" in f), None)
    assert telemetry_frame is not None
    data = telemetry_frame["data"]
    assert "funnel_metrics" in data
    assert "market_regime" in data
    assert "fleet_telemetry" in data
    assert "system_health" in data
    assert data["system_health"]["candle_cache_ready"] is True
