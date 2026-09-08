import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from v2.core.config import get_config
from v2.api.auth import require_api_key

app = FastAPI()

@app.get("/protected", dependencies=[Depends(require_api_key)])
async def protected_route():
    return {"status": "ok"}

def test_missing_production_api_key_fails_closed(monkeypatch):
    """When dashboard_api_key is None or empty, request fails closed with 500."""
    cfg = get_config()
    monkeypatch.setattr(cfg, "dashboard_api_key", None)
    with TestClient(app) as client:
        r = client.get("/protected", headers={"X-API-Key": "some-key"})
        assert r.status_code == 500
        assert "not configured" in r.json()["detail"].lower()

def test_dev_key_not_accepted_in_production(monkeypatch):
    """alpha-dev-key is not accepted when expected key is alpha-prod-key."""
    cfg = get_config()
    monkeypatch.setattr(cfg, "dashboard_api_key", "alpha-prod-key")
    with TestClient(app) as client:
        r = client.get("/protected", headers={"X-API-Key": "alpha-dev-key"})
        assert r.status_code == 401
        assert "invalid" in r.json()["detail"].lower()

def test_valid_production_key_accepted(monkeypatch):
    """Valid configured production key is accepted."""
    cfg = get_config()
    monkeypatch.setattr(cfg, "dashboard_api_key", "my-secret-prod-key-99")
    with TestClient(app) as client:
        r = client.get("/protected", headers={"X-API-Key": "my-secret-prod-key-99"})
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

def test_invalid_key_rejected(monkeypatch):
    """Invalid provided key is rejected with 401."""
    cfg = get_config()
    monkeypatch.setattr(cfg, "dashboard_api_key", "my-secret-prod-key-99")
    with TestClient(app) as client:
        r = client.get("/protected", headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401

def test_protected_production_endpoint_requires_auth(monkeypatch):
    """Missing X-API-Key header or query parameter is rejected with 401."""
    cfg = get_config()
    monkeypatch.setattr(cfg, "dashboard_api_key", "my-secret-prod-key-99")
    with TestClient(app) as client:
        r = client.get("/protected")
        assert r.status_code == 401

