"""
Phase 8 Production Readiness & Autonomous Deployment Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. Mode Transitions (SHADOW, PAPER, LIVE_MICROCASH).
  2. Sub-account micro-order sizing caps & wallet boundaries.
  3. Shadow Slippage Divergence Tracker & Anomaly Alerting.
  4. Global Kill Switch & Emergency Stop Safeguards.
  5. 24/7 Watchdog Supervisor Health Inspection.
  6. SQLite Persistence & REST API Endpoints (/production/status, /production/set-mode, /production/kill-switch, /production/resume).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import invalidate_config
from v2.repository.db import Database
from v2.repository.production_repo import ProductionRepository
from v2.services.production_service.controller import (
    DeploymentMode,
    ProductionController,
    WALLET_LIMITS_INR,
    MICRO_ORDER_CAPS_INR,
    MINIMUM_NOTIONAL_INR,
)
from v2.services.production_service.service import ProductionService
from v2.services.production_service.watchdog import ProductionWatchdog
from v2.services.shadow_service.tracker import ShadowDivergenceTracker
from v2.app_v2 import app


async def _create_test_production_db(tmp_path):
    db_path = str(tmp_path / f"test_prod_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    conn = db.connection
    prod_repo = ProductionRepository(conn)
    return db, prod_repo


# =============================================================================
# 1. Controller Mode Transitions & Sizing Safety Tests
# =============================================================================

class TestProductionControllerAndSafety:

    @pytest.mark.anyio
    async def test_mode_transitions_and_persistence(self, tmp_path):
        """Verify transitions between SHADOW, PAPER, and LIVE_MICROCASH modes."""
        db, prod_repo = await _create_test_production_db(tmp_path)
        try:
            bus = EventBus()
            controller = ProductionController(production_repo=prod_repo, bus=bus)
            await controller.initialize_state()

            assert controller.mode == DeploymentMode.SHADOW

            # 1. Transition to PAPER
            mode_paper = await controller.set_deployment_mode(DeploymentMode.PAPER)
            assert mode_paper == DeploymentMode.PAPER
            assert controller.mode == DeploymentMode.PAPER

            # 2. Transition to LIVE_MICROCASH
            mode_live = await controller.set_deployment_mode("LIVE_MICROCASH")
            assert mode_live == DeploymentMode.LIVE_MICROCASH

            # Verify persistent DB reload
            controller2 = ProductionController(production_repo=prod_repo, bus=bus)
            await controller2.initialize_state()
            assert controller2.mode == DeploymentMode.LIVE_MICROCASH
        finally:
            await db.close()

    @pytest.mark.anyio
    async def test_order_safety_bounds_and_kill_switch(self, tmp_path):
        """Verify micro-order caps, wallet limits, and kill switch safety rules."""
        db, prod_repo = await _create_test_production_db(tmp_path)
        try:
            bus = EventBus()
            controller = ProductionController(production_repo=prod_repo, bus=bus)

            # 1. Valid micro-order (STE, ₹400)
            valid, msg = controller.validate_order_safety("STE", 400.0, current_wallet_exposure_inr=5000.0)
            assert valid is True

            # 2. Below minimum notional ₹100
            valid_low, msg_low = controller.validate_order_safety("STE", 50.0)
            assert valid_low is False
            assert "below minimum notional" in msg_low

            # 3. Exceeds micro-order cap (STE cap is ₹500)
            valid_cap, msg_cap = controller.validate_order_safety("STE", 700.0)
            assert valid_cap is False
            assert "exceeds micro-order cap" in msg_cap

            # 4. Exceeds sub-account wallet ceiling (VCP ceiling is ₹15,000)
            valid_wall, msg_wall = controller.validate_order_safety("VCP", 300.0, current_wallet_exposure_inr=14900.0)
            assert valid_wall is False
            assert "exceeds wallet ceiling" in msg_wall

            # 5. Global Kill Switch trip
            await controller.trip_kill_switch()
            assert controller.is_kill_switch_tripped is True
            valid_kill, msg_kill = controller.validate_order_safety("STE", 300.0)
            assert valid_kill is False
            assert "kill switch is active" in msg_kill

            # 6. Reset Kill Switch
            await controller.reset_kill_switch()
            assert controller.is_kill_switch_tripped is False
            valid_resume, _ = controller.validate_order_safety("STE", 300.0)
            assert valid_resume is True
        finally:
            await db.close()


# =============================================================================
# 2. Shadow Divergence Tracker Tests
# =============================================================================

class TestShadowDivergenceTracker:

    @pytest.mark.anyio
    async def test_divergence_computation_and_anomaly_alert(self, tmp_path):
        """Verify slippage divergence computation and anomaly alert triggering."""
        db, prod_repo = await _create_test_production_db(tmp_path)
        try:
            bus = EventBus()
            tracker = ShadowDivergenceTracker(production_repo=prod_repo, bus=bus)

            # 1. Normal divergence (0.05% < 0.25%)
            res_normal = await tracker.evaluate_trade_divergence(
                bot_name="STE",
                pair="BTC/INR",
                simulated_entry_price=8000000.0,
                real_orderbook_entry_price=8004000.0,
            )
            assert res_normal["slippage_divergence_pct"] == 0.05
            assert res_normal["is_anomaly"] is False

            # 2. Anomaly divergence (0.50% > 0.25%)
            alert_received = []
            bus.subscribe(EventType.ALERT_GENERATED, lambda et, p: alert_received.append(p))

            res_anomaly = await tracker.evaluate_trade_divergence(
                bot_name="HDA",
                pair="ETH/INR",
                simulated_entry_price=300000.0,
                real_orderbook_entry_price=301500.0,
            )
            assert res_anomaly["slippage_divergence_pct"] == 0.4975 or round(res_anomaly["slippage_divergence_pct"], 2) == 0.50
            assert res_anomaly["is_anomaly"] is True
            assert len(alert_received) == 1
            assert "Shadow Divergence Anomaly" in alert_received[0]["title"]

            # 3. Verify SQLite persistence
            logs = await prod_repo.get_shadow_trade_logs(bot_name="HDA")
            assert len(logs) == 1
            assert logs[0]["bot_name"] == "HDA"
            assert logs[0]["pair"] == "ETH/INR"
        finally:
            await db.close()


# =============================================================================
# 3. 24/7 Watchdog Supervisor Tests
# =============================================================================

class TestProductionWatchdog:

    @pytest.mark.anyio
    async def test_watchdog_health_inspection_and_alerting(self):
        """Verify watchdog inspects sub-services and reports overall status."""
        bus = EventBus()

        mock_healthy_svc = MagicMock()
        mock_healthy_svc._started = True

        mock_unhealthy_svc = MagicMock()
        mock_unhealthy_svc._started = False

        services = {
            "scanner_service": mock_healthy_svc,
            "risk_service": mock_healthy_svc,
            "trading_service": mock_unhealthy_svc,
        }

        alerts = []
        bus.subscribe(EventType.ALERT_GENERATED, lambda et, p: alerts.append(p))

        watchdog = ProductionWatchdog(services=services, bus=bus, check_interval_sec=5.0)
        status = await watchdog.inspect_system_health()

        assert status["overall_status"] == "DEGRADED"
        assert status["unhealthy_count"] == 1
        assert "trading_service" in status["unhealthy_services"]
        assert len(alerts) == 1


# =============================================================================
# 4. REST API Endpoint Tests
# =============================================================================

class TestProductionAPIEndpoints:

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        test_db = str(tmp_path / f"test_api_prod_{uuid.uuid4().hex[:6]}.db")
        monkeypatch.setenv("V2_DB_PATH", test_db)
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-prod-key")
        invalidate_config()
        yield
        invalidate_config()

    def test_production_status_set_mode_and_kill_switch_api(self):
        """Verify GET /production/status, POST /production/set-mode, POST /production/kill-switch, POST /production/resume."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-prod-key"}

            # 1. GET /production/status
            res_status = client.get("/api/v2/production/status", headers=headers)
            assert res_status.status_code == 200
            data_stat = res_status.json()
            assert "deployment_mode" in data_stat
            assert "is_kill_switch_tripped" in data_stat
            assert "wallet_limits_inr" in data_stat

            # 2. POST /production/set-mode -> PAPER
            res_mode = client.post("/api/v2/production/set-mode", json={"mode": "PAPER"}, headers=headers)
            assert res_mode.status_code == 200
            assert res_mode.json()["deployment_mode"] == "PAPER"

            # 3. POST /production/kill-switch
            res_kill = client.post("/api/v2/production/kill-switch", headers=headers)
            assert res_kill.status_code == 200
            assert res_kill.json()["status"] == "KILL_SWITCH_TRIPPED"

            # Check status reflects kill switch
            res_stat2 = client.get("/api/v2/production/status", headers=headers)
            assert res_stat2.json()["is_kill_switch_tripped"] is True

            # 4. POST /production/resume
            res_resume = client.post("/api/v2/production/resume", headers=headers)
            assert res_resume.status_code == 200
            assert res_resume.json()["status"] == "ACTIVE"

            res_stat3 = client.get("/api/v2/production/status", headers=headers)
            assert res_stat3.json()["is_kill_switch_tripped"] is False
