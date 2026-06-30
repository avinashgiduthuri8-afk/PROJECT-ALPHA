"""
SP1.3 BUG-24 — trend_summary minimum history guard
Tests that trend_summary() returns {"trend": "neutral", "move_percent": 0.0}
for any history shorter than ANALYZE_MIN_HISTORY (22), preventing the
spurious "uptrend" result caused by EMA warm-up on 2–21 ticks.

Run:
    python -m pytest tests/test_sp1_3_bug24.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    ANALYZE_MIN_HISTORY,
    EMA_SLOW_PERIOD,
    trend_summary,
)

# Expected neutral response for insufficient history
NEUTRAL = {"trend": "neutral", "move_percent": 0.0}


# =============================================================================
# Helpers
# =============================================================================

def _make_history(n: int, rising: bool = True, base: float = 100.0) -> list:
    """Return n history entries, rising or flat."""
    return [
        {
            "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price":  base + (i * 0.5 if rising else 0.0),
            "volume": 1000.0,
        }
        for i in range(n)
    ]


# =============================================================================
# Below minimum — must return neutral
# =============================================================================

class TestTrendSummaryBelowMinimum:

    def test_zero_history_returns_neutral(self):
        assert trend_summary([]) == NEUTRAL

    def test_one_tick_returns_neutral(self):
        assert trend_summary(_make_history(1)) == NEUTRAL

    def test_two_ticks_returns_neutral(self):
        """2 was the old gate — must now also return neutral."""
        assert trend_summary(_make_history(2)) == NEUTRAL

    def test_two_rising_ticks_no_longer_returns_uptrend(self):
        """
        BUG-24 regression: with 2 rising ticks the old code returned 'uptrend'
        because EMA fast (m=0.2) diverges above EMA slow (m=0.09) immediately.
        """
        result = trend_summary(_make_history(2, rising=True))
        assert result["trend"] != "uptrend"
        assert result["trend"] == "neutral"

    def test_five_ticks_returns_neutral(self):
        assert trend_summary(_make_history(5)) == NEUTRAL

    def test_ten_ticks_returns_neutral(self):
        assert trend_summary(_make_history(10)) == NEUTRAL

    def test_twenty_ticks_returns_neutral(self):
        assert trend_summary(_make_history(20)) == NEUTRAL

    def test_twenty_one_ticks_returns_neutral(self):
        """21 is one below ANALYZE_MIN_HISTORY=22 — must still return neutral."""
        assert trend_summary(_make_history(21)) == NEUTRAL

    def test_all_lengths_below_minimum_return_neutral(self):
        """Exhaustive: every n from 0 to 21 must return neutral."""
        for n in range(0, ANALYZE_MIN_HISTORY):
            result = trend_summary(_make_history(n, rising=True))
            assert result == NEUTRAL, (
                f"Expected neutral at n={n}, got {result['trend']!r}"
            )

    def test_neutral_move_percent_is_zero(self):
        for n in (0, 1, 2, 10, 21):
            result = trend_summary(_make_history(n))
            assert result["move_percent"] == 0.0, f"move_percent != 0 at n={n}"

    def test_neutral_trend_string_is_neutral(self):
        for n in (0, 1, 2, 10, 21):
            result = trend_summary(_make_history(n))
            assert result["trend"] == "neutral", (
                f"trend should be 'neutral' at n={n}, got {result['trend']!r}"
            )

    def test_neutral_result_has_no_ema_keys(self):
        """Below minimum: no ema_fast/ema_slow keys in result (not computed)."""
        result = trend_summary(_make_history(5))
        assert "ema_fast" not in result
        assert "ema_slow" not in result


# =============================================================================
# At minimum — gate does not fire, calculation proceeds
# =============================================================================

class TestTrendSummaryAtMinimum:

    def test_22_ticks_does_not_return_neutral_dict(self):
        """At exactly 22 ticks the gate must not fire."""
        result = trend_summary(_make_history(22, rising=True))
        # Gate didn't fire — result has full keys
        assert "ema_fast" in result
        assert "ema_slow" in result

    def test_22_ticks_rising_returns_uptrend(self):
        """With 22 strongly rising ticks, EMA fast > slow → uptrend."""
        history = [
            {
                "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
                "price":  100.0 + i * 2.0,   # steep rise
                "volume": 1000.0,
            }
            for i in range(22)
        ]
        result = trend_summary(history)
        assert result["trend"] == "uptrend"

    def test_22_ticks_flat_does_not_return_uptrend(self):
        result = trend_summary(_make_history(22, rising=False))
        assert result["trend"] != "uptrend"

    def test_22_ticks_result_has_move_percent(self):
        result = trend_summary(_make_history(22, rising=True))
        assert "move_percent" in result
        assert isinstance(result["move_percent"], float)


# =============================================================================
# Above minimum — existing behaviour unchanged
# =============================================================================

class TestTrendSummaryAboveMinimum:

    def test_30_ticks_returns_valid_result(self):
        result = trend_summary(_make_history(30, rising=True))
        assert result["trend"] in ("uptrend", "downtrend", "sideways")

    def test_120_ticks_does_not_crash(self):
        try:
            trend_summary(_make_history(120))
        except Exception as exc:
            pytest.fail(f"trend_summary raised at n=120: {exc}")

    def test_all_required_keys_present_above_minimum(self):
        result = trend_summary(_make_history(50, rising=True))
        assert "trend"        in result
        assert "move_percent" in result
        assert "ema_fast"     in result
        assert "ema_slow"     in result

    def test_flat_prices_return_sideways(self):
        result = trend_summary(_make_history(30, rising=False))
        assert result["trend"] == "sideways"

    def test_falling_prices_return_downtrend(self):
        history = [
            {
                "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
                "price":  200.0 - i * 2.0,   # steep fall
                "volume": 1000.0,
            }
            for i in range(30)
        ]
        result = trend_summary(history)
        assert result["trend"] == "downtrend"

    def test_ema_fast_and_slow_are_floats(self):
        result = trend_summary(_make_history(50, rising=True))
        assert isinstance(result["ema_fast"], float)
        assert isinstance(result["ema_slow"], float)


# =============================================================================
# Boundary: 21 vs 22
# =============================================================================

class TestTrendSummaryBoundary:

    def test_21_returns_neutral_22_calculates(self):
        result_21 = trend_summary(_make_history(21, rising=True))
        result_22 = trend_summary(_make_history(22, rising=True))

        assert result_21 == NEUTRAL
        assert "ema_fast" in result_22   # full calculation ran

    def test_old_gate_closed_at_2_ticks(self):
        """The old gate was < 2 (allowed signals at 2 ticks). Confirmed closed."""
        result = trend_summary(_make_history(2, rising=True))
        assert result == NEUTRAL

    def test_neutral_string_not_warming_up(self):
        """Return value uses 'neutral', not the old 'warming up' string."""
        result = trend_summary(_make_history(1))
        assert result["trend"] == "neutral"
        assert result["trend"] != "warming up"


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
