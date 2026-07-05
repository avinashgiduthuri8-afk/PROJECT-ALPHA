"""
test_mutating_endpoint_auth.py — Auth enforcement for the four mutating endpoints.

Test plan (per bug spec):
  1. Request without X-API-Key header  → 401
  2. Request with wrong key            → 401
  3. Request with correct key          → success (not 401/403)
  4. DASHBOARD_API_KEY unset at startup → all four endpoints return 401
     regardless of header sent.
"""
from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CORRECT_KEY = "test-secret-key"

_MUTATING_ENDPOINTS: list[tuple[str, dict]] = [
    ("/api/watchlist/add",    {"json": {"coin": "BTC"}}),
    ("/api/watchlist/remove", {"json": {"coin": "BTC"}}),
    ("/api/scanner/refresh",  {}),
    ("/api/v1/alerts/push",   {"params": {"level": "INFO", "source": "test", "message": "hi"}}),
]


def _make_client(api_key: str | None) -> TestClient:
    """Return a TestClient for app.py with DASHBOARD_API_KEY set to *api_key*
    (or absent when *api_key* is None).  Each call reloads the module so the
    conditional branch inside require_api_key is re-evaluated."""
    env_patch: dict[str, str] = {"SESSION_SECRET": "test-session-secret"}
    if api_key is not None:
        env_patch["DASHBOARD_API_KEY"] = api_key
    else:
        # Ensure the key is absent even if conftest set a default.
        env_patch.pop("DASHBOARD_API_KEY", None)

    with patch.dict(os.environ, env_patch, clear=False):
        # Remove the key from os.environ when testing the "unset" scenario.
        if api_key is None:
            os.environ.pop("DASHBOARD_API_KEY", None)
        import app as app_mod
        importlib.reload(app_mod)
        # raise_server_exceptions=False so 4xx/5xx come back as responses,
        # not as Python exceptions raised inside the test.
        client = TestClient(app_mod.app, raise_server_exceptions=False)
        return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client_with_key():
    """TestClient where DASHBOARD_API_KEY IS set."""
    with patch.dict(os.environ, {"DASHBOARD_API_KEY": _CORRECT_KEY, "SESSION_SECRET": "test-session-secret"}):
        import app as app_mod
        importlib.reload(app_mod)
        with TestClient(app_mod.app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture(scope="module")
def client_no_key():
    """TestClient where DASHBOARD_API_KEY is NOT set.

    Does NOT use the context manager so the app lifespan (which spawns
    background tasks via anyio) never starts.  Auth is enforced by a FastAPI
    dependency that runs before any route handler, so the lifespan is
    irrelevant for these tests and skipping it avoids the known anyio /
    asyncio event-loop conflict that appears on teardown of module-scoped
    TestClients that reload app.py.
    """
    env = os.environ.copy()
    env.pop("DASHBOARD_API_KEY", None)
    env["SESSION_SECRET"] = "test-session-secret"
    with patch.dict(os.environ, env, clear=True):
        import app as app_mod
        importlib.reload(app_mod)
        yield TestClient(app_mod.app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Test plan item 1 — No header sent → 401
# ---------------------------------------------------------------------------

class TestNoHeader:
    """All four mutating endpoints must return 401 when no X-API-Key is sent."""

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_no_header_returns_401(self, client_with_key, path, kwargs):
        resp = client_with_key.post(path, **kwargs)
        assert resp.status_code == 401, (
            f"POST {path} without header: expected 401, got {resp.status_code}. Body: {resp.text}"
        )

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_no_header_returns_json_error_body(self, client_with_key, path, kwargs):
        resp = client_with_key.post(path, **kwargs)
        body = resp.json()
        # FastAPI wraps HTTPException detail under "detail"
        assert "detail" in body, f"Expected 'detail' key in error body, got: {body}"


# ---------------------------------------------------------------------------
# Test plan item 2 — Wrong key → 401
# ---------------------------------------------------------------------------

class TestWrongKey:
    """All four mutating endpoints must return 401 when an invalid key is sent."""

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_wrong_key_returns_401(self, client_with_key, path, kwargs):
        resp = client_with_key.post(
            path, headers={"X-API-Key": "definitely-wrong"}, **kwargs
        )
        assert resp.status_code == 401, (
            f"POST {path} with wrong key: expected 401, got {resp.status_code}. Body: {resp.text}"
        )

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_wrong_key_error_body_structure(self, client_with_key, path, kwargs):
        resp = client_with_key.post(
            path, headers={"X-API-Key": "definitely-wrong"}, **kwargs
        )
        body = resp.json()
        assert "detail" in body
        detail = body["detail"]
        assert isinstance(detail, dict), f"Expected dict detail, got: {detail}"
        assert detail.get("error") == "unauthorized"


# ---------------------------------------------------------------------------
# Test plan item 3 — Correct key → success (not 401/403)
# ---------------------------------------------------------------------------

class TestCorrectKey:
    """All four mutating endpoints must accept a valid X-API-Key."""

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_correct_key_not_401(self, client_with_key, path, kwargs):
        resp = client_with_key.post(
            path, headers={"X-API-Key": _CORRECT_KEY}, **kwargs
        )
        assert resp.status_code not in (401, 403), (
            f"POST {path} with correct key: got unexpected {resp.status_code}. Body: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Test plan item 4 — DASHBOARD_API_KEY unset → 401 regardless of header
# ---------------------------------------------------------------------------

class TestKeyUnset:
    """When DASHBOARD_API_KEY is absent at startup, every mutating endpoint
    must return 401 — even if the caller supplies a header."""

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_unset_key_no_header_returns_401(self, client_no_key, path, kwargs):
        resp = client_no_key.post(path, **kwargs)
        assert resp.status_code == 401, (
            f"POST {path} (key unset, no header): expected 401, got {resp.status_code}. Body: {resp.text}"
        )

    @pytest.mark.parametrize("path,kwargs", _MUTATING_ENDPOINTS)
    def test_unset_key_with_header_still_returns_401(self, client_no_key, path, kwargs):
        """Sending any header must not bypass the unset-key denial."""
        resp = client_no_key.post(
            path, headers={"X-API-Key": "any-value-at-all"}, **kwargs
        )
        assert resp.status_code == 401, (
            f"POST {path} (key unset, header present): expected 401, got {resp.status_code}. Body: {resp.text}"
        )
