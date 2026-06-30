"""
SP1.4 BUG-27 — /signals strategy param normalization
Tests that scanner_signals() accepts "MTB" regardless of case or surrounding
whitespace, and still correctly rejects genuinely different strategy values.

Run:
    python -m pytest tests/test_sp1_4_bug27.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bots.scanner_bot.main as main_mod
from bots.scanner_bot.main import scanner_signals


# =============================================================================
# Helpers
# =============================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_tracker_with_signals(signals: list) -> MagicMock:
    tracker = MagicMock()
    tracker.recent_signals.return_value = signals
    return tracker


def _sample_signal(coin: str = "BTC", priority: str = "High",
                   timestamp: str = "2024-01-01T00:00:00Z") -> dict:
    return {
        "coin": coin, "market_state": "bull_trend",
        "opportunity_type": "continuation", "priority": priority,
        "opportunity_score": 75, "opp_confidence": 80,
        "risk_level": "low", "timestamp": timestamp,
    }


def _call_signals(strategy: str, tracker=None) -> list:
    if tracker is None:
        tracker = _make_tracker_with_signals([_sample_signal()])
    with patch.object(main_mod, "_TRACKER", tracker):
        response = _run(scanner_signals(strategy=strategy))
    return json.loads(response.body)


# =============================================================================
# Accepted variants — must all behave like exact "MTB"
# =============================================================================

class TestStrategyParamAccepted:

    def test_exact_mtb_returns_signals(self):
        result = _call_signals("MTB")
        assert len(result) == 1

    def test_lowercase_mtb_returns_signals(self):
        """BUG-27 regression: lowercase must now be accepted."""
        result = _call_signals("mtb")
        assert len(result) == 1

    def test_mixed_case_mtb_returns_signals(self):
        result = _call_signals("MtB")
        assert len(result) == 1

    def test_leading_whitespace_mtb_returns_signals(self):
        """BUG-27 regression: leading space must now be accepted."""
        result = _call_signals("  MTB")
        assert len(result) == 1

    def test_trailing_whitespace_mtb_returns_signals(self):
        result = _call_signals("MTB  ")
        assert len(result) == 1

    def test_padded_lowercase_mtb_returns_signals(self):
        """BUG-27 regression: ' mtb ' (padded + lowercase) must be accepted."""
        result = _call_signals("  mtb  ")
        assert len(result) == 1

    def test_tab_padded_mtb_returns_signals(self):
        result = _call_signals("\tMTB\t")
        assert len(result) == 1

    def test_default_value_is_mtb(self):
        """Default strategy (no query param) must still work."""
        result = _call_signals("MTB")  # mirrors Query(default="MTB")
        assert len(result) == 1


# =============================================================================
# Rejected variants — genuinely different strategies still return []
# =============================================================================

class TestStrategyParamRejected:

    def test_different_strategy_returns_empty(self):
        result = _call_signals("VGX")
        assert result == []

    def test_pmb_strategy_returns_empty(self):
        result = _call_signals("PMB")
        assert result == []

    def test_empty_string_returns_empty(self):
        result = _call_signals("")
        assert result == []

    def test_whitespace_only_returns_empty(self):
        """Whitespace-only strips to '' which != 'MTB' — still rejected."""
        result = _call_signals("   ")
        assert result == []

    def test_partial_match_returns_empty(self):
        result = _call_signals("MTBX")
        assert result == []

    def test_mtb_with_internal_space_returns_empty(self):
        """'M TB' strips to 'M TB' which != 'MTB' — correctly still rejected."""
        result = _call_signals("M TB")
        assert result == []


# =============================================================================
# No regression — filtering and sorting logic unaffected
# =============================================================================

class TestSignalsFilteringUnaffected:

    def test_filters_to_mtb_priorities_only(self):
        signals = [
            _sample_signal("BTC", priority="Elite"),
            _sample_signal("ETH", priority="High"),
            _sample_signal("SOL", priority="Medium"),
            _sample_signal("DOGE", priority="Watch"),
            _sample_signal("ADA", priority="Ignore"),
        ]
        tracker = _make_tracker_with_signals(signals)
        result = _call_signals("mtb", tracker=tracker)
        coins = {s["coin"] for s in result}
        assert coins == {"BTC", "ETH", "SOL"}

    def test_sorted_newest_first(self):
        signals = [
            _sample_signal("BTC", timestamp="2024-01-01T00:00:00Z"),
            _sample_signal("ETH", timestamp="2024-01-03T00:00:00Z"),
            _sample_signal("SOL", timestamp="2024-01-02T00:00:00Z"),
        ]
        tracker = _make_tracker_with_signals(signals)
        result = _call_signals("  MTB  ", tracker=tracker)
        timestamps = [s["timestamp"] for s in result]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_no_tracker_returns_empty(self):
        with patch.object(main_mod, "_TRACKER", None):
            response = _run(scanner_signals(strategy="MTB"))
        assert json.loads(response.body) == []

    def test_response_fields_present(self):
        result = _call_signals("mtb")
        required = {"coin", "market_state", "opportunity_type", "priority",
                   "score", "confidence", "risk", "timestamp"}
        assert required == set(result[0].keys())


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
