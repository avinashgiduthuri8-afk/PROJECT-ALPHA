"""
Unit and Integration Tests for V2 Mission Control Dashboard UI and Static Assets.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import uuid
import pytest
import httpx
from fastapi.testclient import TestClient

from v2.app_v2 import app
from v2.core.config import get_config, invalidate_config


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    test_db = str(Path(tempfile.gettempdir()) / f"test_ui_{uuid.uuid4().hex[:6]}.db")
    monkeypatch.setenv("V2_DB_PATH", test_db)
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-ui-key")
    monkeypatch.setenv("DASHBOARD_SECURITY_PASSWORD", "110299")
    invalidate_config()
    yield
    invalidate_config()


def test_serve_dashboard_html():
    """Verify GET / and GET /dashboard render the Mission Control UI HTML."""
    with TestClient(app) as client:
        # 1. Root route
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "PROJECT-ALPHA V2" in resp.text
        assert "MISSION CONTROL" in resp.text
        assert "ai-feed" in resp.text
        assert "health-matrix" in resp.text

        # 2. Dashboard alias route
        resp_dash = client.get("/dashboard")
        assert resp_dash.status_code == 200
        assert "PROJECT-ALPHA V2" in resp_dash.text


def test_static_assets_served():
    """Verify static CSS and JavaScript files are accessible via /v2-static/."""
    with TestClient(app) as client:
        # 1. CSS
        resp_css = client.get("/v2-static/css/dashboard.css")
        assert resp_css.status_code == 200
        assert "--bg-dark" in resp_css.text

        # 2. JavaScript
        resp_js = client.get("/v2-static/js/dashboard.js")
        assert resp_js.status_code == 200
        assert "V2DashboardClient" in resp_js.text


def test_websocket_connection_and_auth():
    """Verify WebSocket /ws/v2/feed handles authentication and ping/pong."""
    with TestClient(app) as client:
        # 1. Unauthorized WebSocket connection
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/v2/feed?api_key=wrong-key") as ws:
                ws.send_text("ping")

        # 2. Authorized WebSocket connection
        with client.websocket_connect("/ws/v2/feed?api_key=test-ui-key") as ws:
            # First frame sent upon connect is the initial telemetry snapshot
            init_frame = ws.receive_text()
            assert "TELEMETRY_SNAPSHOT" in init_frame or "data" in init_frame

            ws.send_text("ping")
            received = []
            for _ in range(5):
                msg = ws.receive_text()
                received.append(msg)
                if "pong" in msg:
                    break
            assert any("pong" in m for m in received), f"Expected pong in received messages, got: {received}"


def test_dashboard_security_elements_rendered():
    """Verify Dashboard HTML contains security PIN overlay, live mode confirmation modal, and mode buttons."""
    """Verify Dashboard HTML contains security PIN overlay, live mode confirmation modal, and mode buttons.
    
    NOTE: After Phase 2 auth hardening, the PIN must NOT appear in HTML source.
    The PIN is validated server-side via /api/v2/auth/verify-password.
    """
    with TestClient(app) as client:
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "dashboardSecurityOverlay" in resp.text
        assert "securityPasswordInput" in resp.text
        # Phase 2: PIN must NOT be in HTML (server-side validation only)
        assert "110299" not in resp.text
        assert "btn-mode-paper" in resp.text
        assert "btn-mode-live" in resp.text
        assert "liveTradeConfirmModal" in resp.text
        assert "liveModePasswordInput" in resp.text


def test_auth_verify_password_endpoint():
    """Verify POST /api/v2/auth/verify-password succeeds only with PIN 110299."""
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-ui-key"}

        # 1. Correct PIN
        resp = client.post("/api/v2/auth/verify-password", json={"password": "110299"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["authorized"] is True

        # 2. Incorrect PIN
        resp_wrong = client.post("/api/v2/auth/verify-password", json={"password": "wrong"}, headers=headers)
        assert resp_wrong.status_code == 401
        data_wrong = resp_wrong.json()
        assert "detail" in data_wrong


def test_set_mode_security_password_protection():
    """Verify switching to LIVE requires PIN 110299, while PAPER is permitted."""
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-ui-key"}

        # 1. Switching to PAPER succeeds without password
        resp_paper = client.post("/api/v2/production/set-mode", json={"mode": "PAPER"}, headers=headers)
        assert resp_paper.status_code == 200
        assert resp_paper.json()["success"] is True
        assert resp_paper.json()["mode"] == "PAPER"

        # 2. Switching to LIVE without password fails
        resp_live_fail = client.post("/api/v2/production/set-mode", json={"mode": "LIVE_MICROCASH"}, headers=headers)
        assert resp_live_fail.status_code == 403
        assert "password required" in resp_live_fail.json()["detail"].lower()

        # 3. Switching to LIVE with wrong password fails
        resp_live_wrong = client.post("/api/v2/production/set-mode", json={"mode": "LIVE_MICROCASH", "password": "999"}, headers=headers)
        assert resp_live_wrong.status_code == 403

        # 4. Switching to LIVE with correct PIN 110299 succeeds
        resp_live_ok = client.post("/api/v2/production/set-mode", json={"mode": "LIVE_MICROCASH", "password": "110299"}, headers=headers)
        assert resp_live_ok.status_code == 200
        assert resp_live_ok.json()["success"] is True
        assert resp_live_ok.json()["mode"] == "LIVE_MICROCASH"

