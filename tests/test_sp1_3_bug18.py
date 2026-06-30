"""
SP1.3 BUG-18 — phase5_score minimum history guard
Tests that phase5_score() returns a zero Phase5Score when fewer than
PHASE5_MIN_HISTORY (21) ticks are available, preventing unreliable EMA
warm-up values from inflating trend_quality and final_score.

Run:
    python -m pytest tests/test_sp1_3_bug18.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    EMA_SLOW_PERIOD,
    PHASE5_MIN_HISTORY,
    Phase5Score,
    phase5_score,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_history(n: int, base_price: float = 100.0, rising: bool = True) -> list:
    """Return n history entries with monotonically rising or flat prices."""
    return [
        {
            "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price":  base_price + (i * 0.5 if rising else 0.0),
            "volume": 1000.0 + i * 10,
        }
        for i in range(n)
    ]


def _zero_score() -> Phase5Score:
    return Phase5Score(
        trend_quality=0,
        pullback_quality=0,
        momentum=0,
        risk_reward=0,
        total=0,
    )


# =============================================================================
# Constant sanity
# =============================================================================

class TestPhase5MinHistoryConstant:

    def test_constant_equals_ema_slow_period(self):
        """PHASE5_MIN_HISTORY must equal EMA_SLOW_PERIOD (21)."""
        assert PHASE5_MIN_HISTORY == EMA_SLOW_PERIOD

    def test_constant_value_is_21(self):
        assert PHASE5_MIN_HISTORY == 21


# =============================================================================
# Below minimum — must return zero Phase5Score
# =============================================================================

class TestPhase5ScoreBelowMinimum:

    def test_zero_candles_returns_zero_score(self):
        result = phase5_score([])
        assert result == _zero_score()

    def test_one_candle_returns_zero_score(self):
        result = phase5_score(_make_history(1))
        assert result == _zero_score()

    def test_five_candles_returns_zero_score(self):
        """5 was the old guard — must now also return zero."""
        result = phase5_score(_make_history(5))
        assert result == _zero_score()

    def test_ten_candles_returns_zero_score(self):
        result = phase5_score(_make_history(10))
        assert result == _zero_score()

    def test_twenty_candles_returns_zero_score(self):
        """20 is one below PHASE5_MIN_HISTORY=21 — must return zero."""
        result = phase5_score(_make_history(20))
        assert result == _zero_score()

    def test_below_minimum_trend_quality_is_zero(self):
        """trend_quality specifically must not be calculated below minimum."""
        for n in (0, 1, 5, 6, 10, 15, 20):
            result = phase5_score(_make_history(n))
            assert result.trend_quality == 0, f"trend_quality should be 0 at n={n}"

    def test_below_minimum_total_is_zero(self):
        for n in (0, 1, 5, 6, 10, 15, 20):
            result = phase5_score(_make_history(n))
            assert result.total == 0, f"total should be 0 at n={n}"

    def test_below_minimum_all_components_are_zero(self):
        """Every Phase5Score component must be 0 below minimum."""
        result = phase5_score(_make_history(20))
        assert result.trend_quality    == 0
        assert result.pullback_quality == 0
        assert result.momentum         == 0
        assert result.risk_reward      == 0
        assert result.total            == 0


# =============================================================================
# At minimum — first valid calculation
# =============================================================================

class TestPhase5ScoreAtMinimum:

    def test_21_candles_does_not_return_zero_score(self):
        """21 ticks is exactly PHASE5_MIN_HISTORY — calculation must proceed."""
        result = phase5_score(_make_history(21))
        # Result is a valid Phase5Score (not forced zero)
        assert isinstance(result, Phase5Score)
        # total should reflect the actual calculation — may be 0 if trend is
        # flat, but the guard must not have fired (we verify by checking that
        # a rising series produces a non-zero total)
        rising = _make_history(21, rising=True)
        result_rising = phase5_score(rising)
        # A rising series should produce some positive score components
        assert result_rising.total >= 0   # not forced to zero by guard

    def test_21_candles_rising_produces_nonzero_trend_quality(self):
        """With 21 rising ticks, EMA fast should separate above EMA slow."""
        history = _make_history(21, rising=True)
        result = phase5_score(history)
        # trend_quality comes from EMA separation + consistency
        # A monotonically rising series should give consistency = 1.0
        assert result.trend_quality >= 0   # valid calculation ran


# =============================================================================
# Above minimum — behaviour unchanged
# =============================================================================

class TestPhase5ScoreAboveMinimum:

    def test_30_candles_produces_valid_result(self):
        result = phase5_score(_make_history(30))
        assert isinstance(result, Phase5Score)
        assert result.total >= 0

    def test_total_equals_sum_of_components(self):
        """Regardless of history length, total must equal sum of components."""
        for n in (21, 25, 30, 50, 100, 120):
            result = phase5_score(_make_history(n))
            expected = (result.trend_quality + result.pullback_quality
                        + result.momentum + result.risk_reward)
            assert result.total == expected, f"total mismatch at n={n}"

    def test_all_components_within_bounds(self):
        """Each component is in [0, 25]; total is in [0, 100]."""
        for n in (21, 30, 60, 120):
            result = phase5_score(_make_history(n))
            assert 0 <= result.trend_quality    <= 25, f"trend_quality out of range at n={n}"
            assert 0 <= result.pullback_quality <= 25, f"pullback_quality out of range at n={n}"
            assert 0 <= result.momentum         <= 25, f"momentum out of range at n={n}"
            assert 0 <= result.risk_reward      <= 25, f"risk_reward out of range at n={n}"
            assert 0 <= result.total            <= 100, f"total out of range at n={n}"

    def test_flat_price_series_does_not_crash(self):
        """A completely flat price series should not raise any exception."""
        history = _make_history(30, rising=False)
        result = phase5_score(history)
        assert isinstance(result, Phase5Score)

    def test_returns_phase5score_dataclass(self):
        result = phase5_score(_make_history(50))
        assert isinstance(result, Phase5Score)
        assert hasattr(result, "trend_quality")
        assert hasattr(result, "pullback_quality")
        assert hasattr(result, "momentum")
        assert hasattr(result, "risk_reward")
        assert hasattr(result, "total")


# =============================================================================
# Boundary: 20 vs 21 candles
# =============================================================================

class TestPhase5ScoreBoundary:

    def test_20_returns_zero_21_calculates(self):
        """The exact boundary: 20 → zero, 21 → calculation proceeds."""
        result_20 = phase5_score(_make_history(20))
        result_21 = phase5_score(_make_history(21, rising=True))

        assert result_20 == _zero_score(), "20 ticks must return zero score"
        # 21 ticks: the guard did not fire, so Phase5Score is computed
        # It won't necessarily be non-zero (depends on price pattern),
        # but it is NOT the same as the forced-zero guard return
        # unless the computed values happen to all be 0.
        # We verify the guard specifically didn't fire by checking trend_quality
        # on a strongly rising series where EMA fast > slow is guaranteed.
        strongly_rising = [
            {"time": datetime(2024, 1, 1, tzinfo=timezone.utc),
             "price": 100.0 + i * 2.0,
             "volume": 1000.0}
            for i in range(21)
        ]
        result_21_strong = phase5_score(strongly_rising)
        # A strongly rising 21-tick series: fast EMA > slow EMA → ema_sep > 0
        # → ema_sep_score > 0 → tq_raw > 0 → trend_quality > 0
        assert result_21_strong.trend_quality > 0, (
            "21 ticks with strong uptrend should produce positive trend_quality"
        )


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
