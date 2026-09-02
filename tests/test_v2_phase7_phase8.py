"""
Comprehensive Unit and Integration Tests for Phase 7 (Notification Service & Telegram Dispatcher)
and Phase 8 (WebSocket Real-Time Push Feed & Observability Engine).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from fastapi import FastAPI
from starlette.websockets import WebSocketDisconnect

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

from v2.services.scanner_service import ScannerService
from v2.services.ai_intelligence_service import AIIntelligenceService
from v2.services.risk_service import RiskService
from v2.services.portfolio_service import PortfolioService
from v2.services.trading_service import TradingService
from v2.services.shadow_service import ShadowService
from v2.services.notification_service import (
    NotificationService,
    TelegramClient,
    format_signal_ai_alert,
    format_trade_approved_alert,
    format_trade_denied_alert,
    format_position_opened_alert,
    format_position_closed_alert,
    format_circuit_breaker_alert,
    format_divergence_alert,
    format_generic_alert,
)
from v2.services.dashboard_service import DashboardService, WebSocketManager
from v2.monitoring import HealthChecker, MetricsCollector, AlertManager
from v2.api.router import router as api_router, init_router
from v2.api.websocket import router as ws_router, init_websocket


# ── 1. Notification Formatter Tests ───────────────────────────────────────────

def test_notification_formatters():
    ai_alert = format_signal_ai_alert({
        "coin": "SOL",
        "recommendation": "APPROVE",
        "confidence_score": 88,
        "trend_evaluation": "Ascending 4h trend",
        "setup_quality": "Breakout",
        "supporting_factors": ["High volume", "RSI divergence"],
        "risk_factors": ["Macro resistance"],
    })
    assert "SOL" in ai_alert
    assert "APPROVE" in ai_alert
    assert "88%" in ai_alert

    trade_appr = format_trade_approved_alert({
        "coin": "BTC",
        "bot": "MTB",
        "approved_amount": 200.0,
        "ai_adjustments": {"size_multiplier": 1.0},
    })
    assert "BTC" in trade_appr
    assert "200.00" in trade_appr

    trade_denied = format_trade_denied_alert({
        "coin": "DOGE",
        "bot": "MTB",
        "code": "BLOCKED_BOT_CAPITAL",
        "reason": "Max capital limit reached",
    })
    assert "DOGE" in trade_denied
    assert "BLOCKED_BOT_CAPITAL" in trade_denied

    pos_opened = format_position_opened_alert({
        "coin": "ETH",
        "bot": "STE",
        "entry_price": 2500.0,
        "qty": 0.1,
        "stop_loss": 2450.0,
        "take_profit": 2600.0,
    })
    assert "ETH" in pos_opened
    assert "2500.00" in pos_opened
    assert "2600.00" in pos_opened

    pos_closed = format_position_closed_alert({
        "coin": "ETH",
        "bot": "STE",
        "pnl": 15.50,
        "pnl_pct": 2.4,
        "exit_reason": "TAKE_PROFIT",
        "exit_price": 2600.0,
    })
    assert "ETH" in pos_closed
    assert "+₹15.50" in pos_closed
    assert "TAKE_PROFIT" in pos_closed

    cb_alert = format_circuit_breaker_alert({"reason": "Max consecutive losses exceeded"})
    assert "CIRCUIT BREAKER TRIGGERED" in cb_alert

    div_alert = format_divergence_alert({
        "coin": "AVAX",
        "bot": "MTB",
        "divergence_type": "AI_FILTERED",
        "reason": "AI blocked trade with bearish divergence",
    })
    assert "AVAX" in div_alert
    assert "AI_FILTERED" in div_alert


# ── 2. Telegram Client Mock & NotificationService Tests ───────────────────────

@pytest.mark.anyio
async def test_telegram_client_mock():
    client = TelegramClient(bot_token="test-bot-token", chat_id="12345678")
    assert client.is_configured is True

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        sent = await client.send_message("<b>Hello Test</b>")
        assert sent is True
        assert mock_post.called


@pytest.mark.anyio
async def test_notification_service_event_subscriptions():
    bus = EventBus()
    cfg = V2Config(alert_bot_token="fake-token", alert_chat_id="fake-chat")
    telegram = TelegramClient(bot_token="fake-token", chat_id="fake-chat")

    sent_messages = []
    async def mock_send(text, parse_mode="HTML", max_retries=2):
        sent_messages.append(text)
        return True

    telegram.send_message = mock_send

    service = NotificationService(bus=bus, config=cfg, telegram_client=telegram)
    await service.start()

    # 1. Publish SIGNAL_AI_CONFIRMED
    await bus.publish(
        EventType.SIGNAL_AI_CONFIRMED,
        {
            "coin": "MATIC",
            "recommendation": "APPROVE",
            "confidence_score": 85,
            "trend_evaluation": "Bull trend",
            "setup_quality": "Breakout",
        },
    )
    await asyncio.sleep(0.05)
    assert len(sent_messages) == 1
    assert "MATIC" in sent_messages[0]

    # 2. Publish CIRCUIT_BREAKER_TRIGGERED
    await bus.publish(
        EventType.CIRCUIT_BREAKER_TRIGGERED,
        {"reason": "Consecutive drawdown threshold hit"},
    )
    await asyncio.sleep(0.05)
    assert len(sent_messages) == 2
    assert "CIRCUIT BREAKER" in sent_messages[1]

    health = service.get_health()
    assert health["healthy"] is True
    assert health["total_dispatched"] == 2

    await service.stop()


# ── 3. WebSocket Manager & Dashboard Service Tests ────────────────────────────

@pytest.mark.anyio
async def test_websocket_manager_broadcast():
    ws_mgr = WebSocketManager()
    assert ws_mgr.active_count == 0

    mock_ws = AsyncMock()
    await ws_mgr.connect(mock_ws)
    assert ws_mgr.active_count == 1

    await ws_mgr.broadcast("signal.generated", {"coin": "LINK", "score": 90})
    assert mock_ws.send_text.called

    ws_mgr.disconnect(mock_ws)
    assert ws_mgr.active_count == 0


@pytest.mark.anyio
async def test_dashboard_service_overview(tmp_path):
    db_path = str(tmp_path / f"test_dash_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    try:
        conn = db.connection
        bus = EventBus()
        pos_repo = PositionRepository(conn)
        trade_repo = TradeRepository(conn)
        shadow_repo = ShadowRepository(conn)
        metrics_repo = MetricsRepository(conn)
        event_log = EventLogRepository(conn)
        cfg = V2Config(v2_db_path=db_path)

        risk_svc = RiskService(bus, pos_repo, trade_repo, event_log, cfg)
        port_svc = PortfolioService(bus, pos_repo, trade_repo, metrics_repo, cfg)
        shadow_svc = ShadowService(bus, shadow_repo, event_log, cfg)

        dash_svc = DashboardService(
            bus=bus,
            config=cfg,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            shadow_service=shadow_svc,
        )
        await dash_svc.start()

        overview = await dash_svc.get_overview()
        assert overview["status"] == "ok"
        assert "portfolio" in overview
        assert "risk" in overview
        assert "shadow" in overview

        await dash_svc.stop()
    finally:
        await db.close()


# ── 4. Monitoring & Observability Tests ────────────────────────────────────────

def test_metrics_collector():
    collector = MetricsCollector()
    collector.increment("signals_scanned", 5)
    collector.record_latency("ai_evaluation", 250.0)
    collector.record_latency("ai_evaluation", 350.0)

    data = collector.get_metrics()
    assert data["counters"]["signals_scanned"] == 5
    assert data["latencies"]["ai_evaluation"]["count"] == 2
    assert data["latencies"]["ai_evaluation"]["avg_ms"] == 300.0


@pytest.mark.anyio
async def test_health_checker_and_alert_manager(tmp_path):
    db_path = str(tmp_path / f"test_health_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    try:
        conn = db.connection
        bus = EventBus()
        pos_repo = PositionRepository(conn)
        trade_repo = TradeRepository(conn)
        shadow_repo = ShadowRepository(conn)
        metrics_repo = MetricsRepository(conn)
        event_log = EventLogRepository(conn)
        cfg = V2Config(v2_db_path=db_path)

        risk_svc = RiskService(bus, pos_repo, trade_repo, event_log, cfg)
        port_svc = PortfolioService(bus, pos_repo, trade_repo, metrics_repo, cfg)
        shadow_svc = ShadowService(bus, shadow_repo, event_log, cfg)
        notif_svc = NotificationService(bus, cfg)

        await risk_svc.start()
        await port_svc.start()
        await shadow_svc.start()
        await notif_svc.start()

        health_checker = HealthChecker(
            db=db,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            shadow_service=shadow_svc,
            notification_service=notif_svc,
        )

        health_report = health_checker.check_health()
        assert health_report["status"] in ("healthy", "degraded")
        assert "database" in health_report["services"]

        alert_mgr = AlertManager(bus=bus, health_checker=health_checker)
        await alert_mgr.evaluate_thresholds()

        await notif_svc.stop()
        await shadow_svc.stop()
        await port_svc.stop()
        await risk_svc.stop()
    finally:
        await db.close()


# ── 5. FastAPI Endpoints Tests (Phase 7 & Phase 8) ────────────────────────────

@pytest.mark.anyio
async def test_api_endpoints_phase7_phase8(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-secret-key")
    invalidate_config()

    db_path = str(tmp_path / f"test_api_p78_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    try:
        conn = db.connection
        bus = EventBus()
        pos_repo = PositionRepository(conn)
        trade_repo = TradeRepository(conn)
        shadow_repo = ShadowRepository(conn)
        metrics_repo = MetricsRepository(conn)
        event_log = EventLogRepository(conn)
        cfg = get_config()

        risk_svc = RiskService(bus, pos_repo, trade_repo, event_log, cfg)
        port_svc = PortfolioService(bus, pos_repo, trade_repo, metrics_repo, cfg)
        shadow_svc = ShadowService(bus, shadow_repo, event_log, cfg)
        notif_svc = NotificationService(bus, cfg)
        dash_svc = DashboardService(
            bus=bus,
            config=cfg,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            shadow_service=shadow_svc,
        )
        metrics_collector = MetricsCollector()
        health_checker = HealthChecker(
            db=db,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            shadow_service=shadow_svc,
            notification_service=notif_svc,
        )

        await risk_svc.start()
        await port_svc.start()
        await shadow_svc.start()
        await notif_svc.start()
        await dash_svc.start()

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v2")
        init_websocket(dash_svc.ws_manager)
        init_router(
            scanner_service=None,
            scheduler=None,
            config=cfg,
            ai_service=None,
            ai_repo=None,
            signal_repo=None,
            risk_service=risk_svc,
            portfolio_service=port_svc,
            trading_service=None,
            shadow_service=shadow_svc,
            shadow_repo=shadow_repo,
            position_repo=pos_repo,
            trade_repo=trade_repo,
            notification_service=notif_svc,
            dashboard_service=dash_svc,
            health_checker=health_checker,
            metrics_collector=metrics_collector,
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"X-API-Key": "test-secret-key"}

            # 1. GET /api/v2/dashboard/overview
            resp = await client.get("/api/v2/dashboard/overview", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

            # 2. GET /api/v2/monitoring/metrics
            metrics_collector.increment("orders_simulated", 3)
            resp = await client.get("/api/v2/monitoring/metrics", headers=headers)
            assert resp.status_code == 200
            m_data = resp.json()
            assert m_data["counters"]["orders_simulated"] == 3

            # 3. GET /api/v2/monitoring/health
            resp = await client.get("/api/v2/monitoring/health", headers=headers)
            assert resp.status_code == 200
            h_data = resp.json()
            assert "status" in h_data

            # 4. POST /api/v2/notifications/test
            resp = await client.post(
                "/api/v2/notifications/test",
                headers=headers,
                json={"message": "Verification test alert"},
            )
            assert resp.status_code == 200
            n_data = resp.json()
            assert n_data["ok"] is True

        await dash_svc.stop()
        await notif_svc.stop()
        await shadow_svc.stop()
        await port_svc.stop()
        await risk_svc.stop()
    finally:
        await db.close()
        invalidate_config()
