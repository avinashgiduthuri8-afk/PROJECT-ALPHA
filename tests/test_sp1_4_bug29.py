"""
SP1.4 BUG-29 — /market-state exception safety
Tests that market_state() returns HTTP 200 with a safe default even when
LATEST_MARKET_STATE contains a non-JSON-serialisable value, matching every
other endpoint's "HTTP 200 always" contract.

Run:
    python -m pytest tests/test_sp1_4_bug29.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bots.scanner_bot.main as main_mod
from bots.scanner_bot.main import market_state


# =============================================================================
# Helpers
# =============================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _call_market_state() -> dict:
    response = _run(market_state())
    return json.loads(response.body)


# =============================================================================
# Normal operation — unchanged behaviour
# =============================================================================

class TestMarketStateNormalOperation:

    def test_returns_current_latest_market_state(self):
        fake_state = {"market_state": "bull_trend", "timestamp": "2024-01-01T00:00:00Z"}
        with patch.object(main_mod, "LATEST_MARKET_STATE", fake_state):
            result = _call_market_state()
        assert result == fake_state

    def test_default_initial_state_is_unknown(self):
        fake_state = {"market_state": "unknown", "timestamp": "2024-01-01T00:00:00Z"}
        with patch.object(main_mod, "LATEST_MARKET_STATE", fake_state):
            result = _call_market_state()
        assert result["market_state"] == "unknown"

    def test_returns_dict_not_none(self):
        result = _call_market_state()
        assert isinstance(result, dict)
        assert result is not None

    def test_extra_fields_passed_through(self):
        fake_state = {
            "market_state": "breakout",
            "timestamp": "2024-01-01T00:00:00Z",
            "confidence": 0.8,
            "coins_analyzed": 50,
        }
        with patch.object(main_mod, "LATEST_MARKET_STATE", fake_state):
            result = _call_market_state()
        assert result == fake_state


# =============================================================================
# Exception safety — non-serialisable content
# =============================================================================

class TestMarketStateExceptionSafety:

    def test_non_serializable_value_does_not_raise(self):
        """
        BUG-29 regression: a datetime object (not JSON-serialisable by
        default) inside LATEST_MARKET_STATE must not crash the endpoint.
        """
        bad_state = {"market_state": "bull_trend", "timestamp": datetime.now(timezone.utc)}
        with patch.object(main_mod, "LATEST_MARKET_STATE", bad_state):
            try:
                result = _call_market_state()
            except Exception as exc:
                pytest.fail(f"market_state() raised: {exc}")
        assert isinstance(result, dict)

    def test_non_serializable_value_returns_safe_default(self):
        bad_state = {"market_state": "bull_trend", "timestamp": datetime.now(timezone.utc)}
        with patch.object(main_mod, "LATEST_MARKET_STATE", bad_state):
            result = _call_market_state()
        assert result["market_state"] == "unknown"

    def test_safe_default_has_timestamp_key(self):
        bad_state = {"bad": object()}   # arbitrary non-serialisable object
        with patch.object(main_mod, "LATEST_MARKET_STATE", bad_state):
            result = _call_market_state()
        assert "timestamp" in result

    def test_set_type_does_not_raise(self):
        """A set is not JSON-serialisable — must not crash the endpoint."""
        bad_state = {"market_state": "bull_trend", "tags": {"a", "b", "c"}}
        with patch.object(main_mod, "LATEST_MARKET_STATE", bad_state):
            try:
                result = _call_market_state()
            except Exception as exc:
                pytest.fail(f"market_state() raised on set value: {exc}")
        assert isinstance(result, dict)

    def test_safe_default_response_shape(self):
        bad_state = {"bad": object()}
        with patch.object(main_mod, "LATEST_MARKET_STATE", bad_state):
            result = _call_market_state()
        assert set(result.keys()) == {"market_state", "timestamp"}

    def test_http_200_always_even_on_exception(self):
        """Endpoint must return a response object (HTTP 200), never raise."""
        bad_state = {"market_state": "bull_trend", "timestamp": datetime.now(timezone.utc)}
        with patch.object(main_mod, "LATEST_MARKET_STATE", bad_state):
            response = _run(market_state())
        assert response.status_code == 200


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
