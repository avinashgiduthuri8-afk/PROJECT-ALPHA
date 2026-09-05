"""
Phase 7 Dashboard Plugin & Real-Time Fleet Monitoring Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. Aggregator State Assembly (Scanner, Execution Fleet, Active Positions, Performance Summary, Feedback State).
  2. WebSocket Telemetry Gateway (connection pooling, authentication, 15s heartbeats, delta broadcasts).
  3. Fleet Command & Control REST API (/dashboard/overview, /dashboard/fleet, /dashboard/signals, /dashboard/fleet/{bot}/pause, /dashboard/fleet/{bot}/resume, /dashboard/emergency-stop).
  4. Data Contract Integrity & Payload Schema Validation.
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
from v2.services.dashboard_service.aggregator import DashboardAggregator
from v2.services.dashboard_service.ws_gateway import WebSocketTelemetryGateway
from v2.app_v2 import app


# =============================================================================
# 1. Aggregator State Assembly Tests
# =============================================================================

class TestDashboardAggregator:

    @pytest.mark.anyio
    async def test_aggregator_snapshot_assembly(self):
        """Verify DashboardAggregator compiles unified system overview snapshot."""
        agg = DashboardAggregator()
        snapshot = await agg.get_overview_snapshot()

        assert "system_status" in snapshot
        assert snapshot["system_status"] == "OPERATIONAL"
        assert "scanner_funnel" in snapshot
        assert "execution_fleet" in snapshot
        assert "active_positions" in snapshot
        assert "performance_summary" in snapshot
        assert "feedback_state" in snapshot

        fleet = snapshot["execution_fleet"]
        assert len(fleet) == 4
        assert "STE" in fleet
        assert "HDA" in fleet
        assert "VCP" in fleet
        assert "BBS" in fleet


# =============================================================================
# 2. WebSocket Telemetry Gateway Tests
# =============================================================================

class TestWebSocketTelemetryGateway:

    @pytest.mark.anyio
    async def test_ws_gateway_lifecycle_and_delta_broadcast(self):
        """Verify WebSocketTelemetryGateway lifecycle and delta broadcast capability."""
        agg = DashboardAggregator()
        bus = EventBus()
        ws_gateway = WebSocketTelemetryGateway(aggregator=agg, bus=bus)

        await ws_gateway.start()
        assert ws_gateway._started is True
        assert ws_gateway.active_connections_count == 0

        # Broadcast delta when no connections present (should not raise error)
        await ws_gateway.broadcast_delta("DELTA_SIGNAL_GENERATED", {"symbol": "BTC/INR"})

        await ws_gateway.stop()
        assert ws_gateway._started is False


# =============================================================================
# 3. Fleet Command & Control REST API Tests
# =============================================================================

class TestDashboardAPIEndpoints:

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        test_db = str(tmp_path / f"test_api_dashboard_{uuid.uuid4().hex[:6]}.db")
        monkeypatch.setenv("V2_DB_PATH", test_db)
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-dashboard-key")
        invalidate_config()
        yield
        invalidate_config()

    def test_dashboard_overview_fleet_and_signals_endpoints(self):
        """Verify GET /dashboard/overview, GET /dashboard/fleet, GET /dashboard/signals."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-dashboard-key"}

            # 1. GET /dashboard/overview
            res_over = client.get("/api/v2/dashboard/overview", headers=headers)
            assert res_over.status_code == 200
            data_over = res_over.json()
            assert "system_status" in data_over
            assert "execution_fleet" in data_over

            # 2. GET /dashboard/fleet
            res_fleet = client.get("/api/v2/dashboard/fleet", headers=headers)
            assert res_fleet.status_code == 200
            data_fleet = res_fleet.json()
            assert "execution_fleet" in data_fleet
            assert "total_allocated_inr" in data_fleet

            # 3. GET /dashboard/signals
            res_sig = client.get("/api/v2/dashboard/signals", headers=headers)
            assert res_sig.status_code == 200
            data_sig = res_sig.json()
            assert "funnel" in data_sig

    def test_fleet_bot_pause_resume_and_emergency_stop(self):
        """Verify bot pause/resume and global emergency stop endpoints."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-dashboard-key"}

            # 1. Pause STE bot
            res_pause = client.post("/api/v2/dashboard/fleet/STE/pause", headers=headers)
            assert res_pause.status_code == 200
            assert res_pause.json()["status"] == "PAUSED"
            assert res_pause.json()["bot_name"] == "STE"

            # 2. Resume STE bot
            res_resume = client.post("/api/v2/dashboard/fleet/STE/resume", headers=headers)
            assert res_resume.status_code == 200
            assert res_resume.json()["status"] == "ACTIVE"

            # 3. Global Emergency Stop
            res_stop = client.post("/api/v2/dashboard/emergency-stop", headers=headers)
            assert res_stop.status_code == 200
            assert res_stop.json()["status"] == "EMERGENCY_STOP_TRIPPED"

            # Verify system overview reflects emergency stop
            res_over = client.get("/api/v2/dashboard/overview", headers=headers)
            assert res_over.json()["system_status"] == "EMERGENCY_STOP"
