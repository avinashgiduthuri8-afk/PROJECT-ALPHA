"""
Tests for canonical PROJECT-ALPHA entrypoint app.py.
Verifies canonical routes as primary and backward-compatible v2 routes as secondary.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from fastapi.testclient import TestClient

from app import app
from core.config import get_config, invalidate_config


@pytest.fixture(autouse=True)
def isolate_canonical_test_env(monkeypatch, tmp_path):
    """Ensure clean test environment isolated from other tests."""
    monkeypatch.setenv("DEPLOYMENT_MODE", "SHADOW")
    monkeypatch.setenv("V2_DEPLOYMENT_MODE", "SHADOW")
    monkeypatch.setenv("TRADING_ENABLED", "false")
    monkeypatch.setenv("V2_TRADING_ENABLED", "false")
    monkeypatch.setenv("DASHBOARD_API_KEY", "alpha-prod-key")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_canonical_app.db"))
    monkeypatch.setenv("V2_DB_PATH", str(tmp_path / "test_canonical_app.db"))
    invalidate_config()
    cfg = get_config()
    cfg.deployment_mode = "SHADOW"
    cfg.trading_enabled = False
    yield
    invalidate_config()


def test_canonical_and_legacy_routes():
    """Verify canonical app serves both primary canonical routes and legacy fallbacks."""
    cfg = get_config()
    api_key = cfg.dashboard_api_key or "alpha-prod-key"
    headers = {"X-API-Key": api_key}

    with TestClient(app) as client:
        # 1. Dashboard UI (Canonical vs Backward-compatible)
        res_root = client.get("/")
        assert res_root.status_code == 200
        assert "<html" in res_root.text.lower()

        res_dash = client.get("/dashboard")
        assert res_dash.status_code == 200
        assert "<html" in res_dash.text.lower()

        res_v2_dash = client.get("/v2/dashboard")
        assert res_v2_dash.status_code == 200
        assert "<html" in res_v2_dash.text.lower()

        # 2. Static Assets (Canonical vs Backward-compatible)
        res_css = client.get("/static/css/dashboard.css")
        assert res_css.status_code == 200

        res_v2_css = client.get("/v2-static/css/dashboard.css")
        assert res_v2_css.status_code == 200

        # 3. Canonical API Routes (/api/*)
        res_health = client.get("/api/monitoring/health", headers=headers)
        assert res_health.status_code == 200
        assert "status" in res_health.json()

        res_pipeline = client.get("/api/pipeline/stages", headers=headers)
        assert res_pipeline.status_code == 200
        stages = res_pipeline.json()
        assert len(stages) == 14

        res_overview = client.get("/api/dashboard/overview", headers=headers)
        assert res_overview.status_code == 200

        # 4. Backward-Compatible API Routes (/api/v2/*)
        res_legacy_health = client.get("/api/v2/monitoring/health", headers=headers)
        assert res_legacy_health.status_code == 200
        assert "status" in res_legacy_health.json()

        res_legacy_pipeline = client.get("/api/v2/pipeline/stages", headers=headers)
        assert res_legacy_pipeline.status_code == 200
        assert len(res_legacy_pipeline.json()) == 14

        res_legacy_overview = client.get("/api/v2/dashboard/overview", headers=headers)
        assert res_legacy_overview.status_code == 200

        # 5. WebSocket Connections (Canonical and Legacy)
        with client.websocket_connect(f"/ws/feed?api_key={api_key}") as ws:
            pass

        with client.websocket_connect(f"/ws?api_key={api_key}") as ws:
            pass

        with client.websocket_connect(f"/ws/v2/feed?api_key={api_key}") as ws:
            pass
