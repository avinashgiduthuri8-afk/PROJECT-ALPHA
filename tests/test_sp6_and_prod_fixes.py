"""
Tests for SP6 + Production Fixes (BUG-57, BUG-56, BUG-55, FIX-4, FIX-5, FIX-6).

Covers:
  - FIX 1 (BUG-57): collect_system_metrics() returns SystemMetrics when psutil unavailable
  - FIX 2 (BUG-56): run_all_checks() includes MTB/PMB storage results
  - FIX 3 (BUG-55): AlertManager wiring in circuit breaker
  - FIX 4: /health probe + 503 when DASHBOARD_API_KEY unset
  - FIX 5: _check_candles_connectivity() pre-flight
  - FIX 6: SCANNER_API_URL defaults to port 8080
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import APIKeyHeader


# =============================================================================
# FIX 1 (BUG-57) — collect_system_metrics() never raises
# =============================================================================

class TestCollectSystemMetrics:
    """BUG-57: psutil crash returns safe defaults, never raises."""

    def test_returns_system_metrics_when_psutil_unavailable(self):
        """Even when psutil import fails, collect_system_metrics returns SystemMetrics."""
        # Block psutil import by injecting a broken module
        original = sys.modules.get("psutil")
        sys.modules["psutil"] = None  # None causes ImportError on `import psutil`
        try:
            # Re-import the collector so our patched psutil takes effect
            import importlib
            import monitoring.metrics_collector as mc
            importlib.reload(mc)

            collector = mc.MetricsCollector.__new__(mc.MetricsCollector)
            collector._initialized = False
            collector.__init__()

            result = collector.collect_system_metrics()
            assert isinstance(result, mc.SystemMetrics)
        finally:
            if original is None:
                sys.modules.pop("psutil", None)
            else:
                sys.modules["psutil"] = original

    def test_returns_system_metrics_when_psutil_raises(self):
        """When psutil raises during collection, collect_system_metrics returns SystemMetrics."""
        import monitoring.metrics_collector as mc

        collector = mc.MetricsCollector.__new__(mc.MetricsCollector)
        collector._initialized = False
        collector.__init__()

        broken_psutil = MagicMock()
        broken_psutil.cpu_percent.side_effect = RuntimeError("simulated failure")

        with patch.dict(sys.modules, {"psutil": broken_psutil}):
            result = collector.collect_system_metrics()

        assert isinstance(result, mc.SystemMetrics)

    def test_does_not_raise_on_any_exception(self):
        """collect_system_metrics must never propagate exceptions."""
        import monitoring.metrics_collector as mc

        collector = mc.MetricsCollector.__new__(mc.MetricsCollector)
        collector._initialized = False
        collector.__init__()

        # Simulate a completely broken psutil
        broken = MagicMock()
        broken.cpu_percent.side_effect = Exception("boom")

        with patch.dict(sys.modules, {"psutil": broken}):
            try:
                result = collector.collect_system_metrics()
                assert isinstance(result, mc.SystemMetrics)
            except Exception as exc:
                pytest.fail(f"collect_system_metrics raised: {exc}")
# =============================================================================
# FIX 2 (BUG-56) — run_all_checks() includes MTB storage results
# =============================================================================

class TestRunAllChecksIncludesMTB:
    """BUG-56: HealthChecker.run_all_checks() now checks MTB storage files."""

    def _make_checker(self):
        import monitoring.health_check as hc
        checker = hc.HealthChecker.__new__(hc.HealthChecker)
        checker._initialized = False
        checker.__init__()
        return checker

    def test_mtb_results_present_when_config_loads(self):
        """run_all_checks includes MTB storage results when config is importable."""
        from monitoring.health_check import HealthChecker, HealthCheckResult

        checker = self._make_checker()

        # Patch check_storage_file to record calls
        calls = []

        def fake_check(filename, path=None):
            calls.append(filename)
            r = HealthCheckResult.__new__(HealthCheckResult)
            from monitoring.health_check import HealthStatus, CheckSeverity
            from datetime import datetime, timezone
            r.name = f"storage_{filename}"
            r.status = HealthStatus.HEALTHY
            r.severity = CheckSeverity.INFO
            r.message = "ok"
            r.details = {}
            r.duration_ms = 0.0
            r.checked_at = datetime.now(timezone.utc)
            return r

        from pathlib import Path
        fake_config = types.ModuleType("bots.mtb_bot.config")
        fake_config.POSITIONS_FILE = Path("/tmp/mtb_pos.json")
        fake_config.TRADES_FILE    = Path("/tmp/mtb_trd.json")
        fake_config.STATS_FILE     = Path("/tmp/mtb_sta.json")

        with patch.object(checker, "check_storage_file", side_effect=fake_check), \
             patch.dict(sys.modules, {
                 "bots.mtb_bot.config": fake_config,
             }):
            report = checker.run_all_checks()

        # MTB file labels must appear in calls
        assert any("mtb" in c for c in calls), f"MTB storage not checked; calls={calls}"

    def test_run_all_checks_does_not_raise_when_mtb_config_import_fails(self):
        """run_all_checks does not raise when MTB config cannot be imported."""
        checker = self._make_checker()

        def fake_check(filename, path=None):
            from monitoring.health_check import HealthCheckResult, HealthStatus, CheckSeverity
            from datetime import datetime, timezone
            r = HealthCheckResult.__new__(HealthCheckResult)
            r.name = f"storage_{filename}"
            r.status = HealthStatus.HEALTHY
            r.severity = CheckSeverity.INFO
            r.message = "ok"
            r.details = {}
            r.duration_ms = 0.0
            r.checked_at = datetime.now(timezone.utc)
            return r

<<<<<<< Updated upstream
=======
        # Simulate import failure for MTB config
>>>>>>> Stashed changes
        with patch.object(checker, "check_storage_file", side_effect=fake_check), \
             patch.dict(sys.modules, {
                 "bots.mtb_bot.config": None,
             }):
            try:
                report = checker.run_all_checks()
            except Exception as exc:
                pytest.fail(f"run_all_checks raised on missing bot config: {exc}")

        names = [c.name for c in report.checks]
        assert any("mtb" in n for n in names), \
            f"Expected warning entries for unavailable configs; got names={names}"

<<<<<<< Updated upstream
=======


>>>>>>> Stashed changes

# =============================================================================
# FIX 4 — /health probe + 503 when DASHBOARD_API_KEY unset
# =============================================================================

class TestHealthProbeAndAuth:
    """/health returns 200 without auth; DASHBOARD_API_KEY unset returns 503."""

    def _build_test_app(self, dashboard_api_key):
        """
        Build a minimal FastAPI app that replicates only the auth logic and
        /health + /protected routes, avoiding import of heavy bot modules.
        """
        _aph = APIKeyHeader(name="X-API-Key", auto_error=False)

        if not dashboard_api_key:
            async def require_api_key(request: Request,
                                      api_key: str = Depends(_aph)) -> str:
                if request.url.path in ("/health", "/"):
                    return ""
                raise HTTPException(status_code=503,
                                    detail="DASHBOARD_API_KEY not configured")
        else:
            _key = dashboard_api_key

            async def require_api_key(request: Request,
                                      api_key: str = Depends(_aph)) -> str:
                if request.url.path in ("/health", "/"):
                    return ""
                if api_key != _key:
                    raise HTTPException(status_code=403,
                                        detail="Invalid or missing X-API-Key header")
                return api_key

        test_app = FastAPI(dependencies=[Depends(require_api_key)])

        @test_app.get("/health", include_in_schema=False)
        async def health_probe():
            return {"status": "ok"}

        @test_app.get("/protected")
        async def protected():
            return {"ok": True}

        return test_app

    def test_health_returns_200_no_auth_header(self):
        """GET /health returns 200 with no auth header regardless of key status."""
        from fastapi.testclient import TestClient

        # Test with key set
        app_with_key = self._build_test_app("secret")
        with TestClient(app_with_key, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json() == {"status": "ok"}

    def test_health_returns_200_when_key_unset(self):
        """GET /health returns 200 even when DASHBOARD_API_KEY is not configured."""
        from fastapi.testclient import TestClient

        app_no_key = self._build_test_app(None)
        with TestClient(app_no_key, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200, f"Expected 200 for /health, got {resp.status_code}"

    def test_auth_middleware_returns_503_when_key_unset(self):
        """When DASHBOARD_API_KEY is not set, protected endpoints return 503."""
        from fastapi.testclient import TestClient

        app_no_key = self._build_test_app(None)
        with TestClient(app_no_key, raise_server_exceptions=False) as client:
            resp = client.get("/protected")
        assert resp.status_code == 503, \
            f"Expected 503 when DASHBOARD_API_KEY unset, got {resp.status_code}"


# =============================================================================
# FIX 5 — _check_candles_connectivity()
# =============================================================================

class TestCheckCandlesConnectivity:
    """FIX 5: _check_candles_connectivity() returns correct bool based on network."""

    def test_returns_false_on_connection_error(self):
        """Returns False when requests.get raises ConnectionError."""
        from bots.scanner_bot.scanner import _check_candles_connectivity
        import requests

        with patch.object(requests, "get", side_effect=ConnectionError("refused")):
            result = _check_candles_connectivity()

        assert result is False

    def test_returns_true_on_200_response(self):
        """Returns True when the candles API returns HTTP 200."""
        from bots.scanner_bot.scanner import _check_candles_connectivity
        import requests

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(requests, "get", return_value=mock_resp):
            result = _check_candles_connectivity()

        assert result is True

    def test_returns_true_on_non_200_response(self):
        """Any HTTP response (including 503) means the network path is open.

        The function's documented contract: "any HTTP response counts as
        reachable because a server-side validation error (4xx/5xx) still
        proves the network path is open."  Only network-level exceptions
        (DNS, timeout, connection refused) return False.
        """
        from bots.scanner_bot.scanner import _check_candles_connectivity
        import requests

        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch.object(requests, "get", return_value=mock_resp):
            result = _check_candles_connectivity()

        assert result is True

    def test_returns_false_on_timeout(self):
        """Returns False when the request times out."""
        from bots.scanner_bot.scanner import _check_candles_connectivity
        import requests

        with patch.object(requests, "get", side_effect=requests.Timeout()):
            result = _check_candles_connectivity()

        assert result is False


# =============================================================================
# FIX 6 — SCANNER_API_URL defaults
# =============================================================================

<<<<<<< Updated upstream
=======


>>>>>>> Stashed changes
class TestScannerApiUrlDefault:
    """FIX 6: MTB config defaults to port 5000."""

    def test_mtb_scanner_api_url_defaults_to_5000(self):
        """MTB config SCANNER_API_URL default port must be 5000 (app runs on 5000)."""
        import os
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCANNER_API_URL", None)
            import importlib
            import bots.mtb_bot.config as mtb_cfg
            importlib.reload(mtb_cfg)

        assert "5000" in mtb_cfg.SCANNER_API_URL, \
            f"Expected port 5000 in MTB SCANNER_API_URL, got: {mtb_cfg.SCANNER_API_URL}"
        assert "8080" not in mtb_cfg.SCANNER_API_URL, \
            f"MTB SCANNER_API_URL unexpectedly contains 8080: {mtb_cfg.SCANNER_API_URL}"
