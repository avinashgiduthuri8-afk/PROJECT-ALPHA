"""
Tests for canonical PROJECT-ALPHA entrypoint app.py.
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
from core.config import get_config


def test_canonical_app_startup_and_endpoints():
    """Verify canonical app boots correctly and serves dashboard and API routes."""
    cfg = get_config()
    with TestClient(app) as client:
        # Dashboard UI
        res_dash = client.get("/dashboard")
        assert res_dash.status_code == 200
        assert "<html" in res_dash.text.lower()

        # Monitoring health route
        headers = {"X-API-Key": cfg.dashboard_api_key or "alpha-prod-key"}
        res_health = client.get("/api/v2/monitoring/health", headers=headers)
        assert res_health.status_code == 200
        assert "status" in res_health.json()

        # Pipeline stages route
        res_pipeline = client.get("/api/v2/pipeline/stages", headers=headers)
        assert res_pipeline.status_code == 200
        stages = res_pipeline.json()
        assert len(stages) == 14

