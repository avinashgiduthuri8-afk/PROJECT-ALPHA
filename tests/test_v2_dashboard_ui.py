"""
Unit and Integration Tests for V2 Mission Control Dashboard UI and Static Assets.
"""

from __future__ import annotations

import uuid
import pytest
import httpx
from fastapi.testclient import TestClient

from v2.app_v2 import app
from v2.core.config import get_config, invalidate_config


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    test_db = str(tmp_path / f"test_ui_{uuid.uuid4().hex[:6]}.db")
    monkeypatch.setenv("V2_DB_PATH", test_db)
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-ui-key")
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
