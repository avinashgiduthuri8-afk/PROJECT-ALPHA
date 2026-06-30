"""
SP1.3 BUG-16 — analyze_coin minimum history gate
Tests that analyze_coin() returns [] for any history shorter than
ANALYZE_MIN_HISTORY (22 ticks), preventing false EMA crossover and
spurious volume spike signals during indicator warm-up.

Run:
    python -m pytest tests/test_sp1_3_bug16.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    ANALYZE_MIN_HISTORY,
    EMA_SLOW_PERIOD,
    VOLUME_AVERAGE_PERIOD,
    analyze_coin,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_history(n: int, *, rising: bool = True, base: float = 100.0) -> list:
    """Return n history entries. Rising ensures EMA fast > slow eventually."""
    return [
        {
            "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price":  base + (i * 0.5 if rising else 0.0),
            "volume": 1_000_000.0 * (10 if i == n - 1 else 1),  # last tick is volume spike
        }
        for i in range(n)
    ]


def _analyze(n: int, rising: bool = True):
    history = _make_history(n, rising=rising)
    with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
         patch("bots.scanner_bot.scanner.get_historical_performance",
               return_value={"perf_90d": None}):
        from bots.scanner_bot.scanner import HistoricalPatternScore
        mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)
        return analyze_coin("BTC", history)


# =============================================================================
# Constant sanity
# =============================================================================

class TestAnalyzeMinHistoryConstant:

    def test_constant_equals_ema_slow_plus_one(self):
        assert ANALYZE_MIN_HISTORY == EMA_SLOW_PERIOD + 1

    def test_constant_value_is_22(self):
        assert ANALYZE_MIN_HISTORY == 22

    def test_satisfies_volume_baseline_requirement(self):
        """ANALYZE_MIN_HISTORY must be >= VOLUME_AVERAGE_PERIOD + 1 (21)."""
        assert ANALYZE_MIN_HISTORY >= VOLUME_AVERAGE_PERIOD + 1


# =============================================================================
# Below minimum — must always return []
# =============================================================================

class TestAnalyzeCoinBelowMinimum:

    def test_zero_history_returns_empty(self):
        assert analyze_coin("BTC", []) == []

    def test_one_tick_returns_empty(self):
        assert _analyze(1) == []

    def test_two_ticks_returns_empty(self):
        """2 was the old gate — must now also return []."""
        assert _analyze(2) == []

    def test_five_ticks_returns_empty(self):
        assert _analyze(5) == []

    def test_ten_ticks_returns_empty(self):
        assert _analyze(10) == []

    def test_twenty_ticks_returns_empty(self):
        assert _analyze(20) == []

    def test_twenty_one_ticks_returns_empty(self):
        """21 is one below ANALYZE_MIN_HISTORY=22 — must still return []."""
        assert _analyze(21) == []

    def test_below_minimum_never_returns_signal(self):
        """For all values below minimum, no Signal is ever produced."""
        for n in range(0, ANALYZE_MIN_HISTORY):
            result = _analyze(n)
            assert result == [], f"Expected [] at n={n}, got {len(result)} signal(s)"

    def test_below_minimum_with_flat_prices_returns_empty(self):
        for n in (0, 5, 10, 21):
            result = _analyze(n, rising=False)
            assert result == [], f"Expected [] at n={n} (flat)"


# =============================================================================
# At minimum — gate does not fire, calculation proceeds
# =============================================================================

class TestAnalyzeCoinAtMinimum:

    def test_22_ticks_does_not_return_early(self):
        """
        With 22 ticks the gate must not fire. The function may still return []
        if no signal conditions are met, but it must have run the full logic.
        We verify by confirming it returns a list (not raising an exception).
        """
        result = _analyze(22)
        assert isinstance(result, list)

    def test_22_ticks_does_not_crash(self):
        """No exception at the exact minimum boundary."""
        try:
            _analyze(22)
        except Exception as exc:
            pytest.fail(f"analyze_coin raised at n=22: {exc}")


# =============================================================================
# Above minimum — existing behaviour unchanged
# =============================================================================

class TestAnalyzeCoinAboveMinimum:

    def test_returns_list_at_various_lengths(self):
        for n in (22, 30, 50, 80, 120):
            result = _analyze(n)
            assert isinstance(result, list), f"Expected list at n={n}"

    def test_does_not_crash_at_full_history(self):
        try:
            _analyze(120)
        except Exception as exc:
            pytest.fail(f"analyze_coin raised at n=120: {exc}")

    def test_signals_have_valid_scores(self):
        """Any signals produced above minimum must have non-negative scores."""
        for n in (30, 60, 120):
            signals = _analyze(n)
            for sig in signals:
                assert sig.score >= 0, f"Negative score at n={n}"
                assert sig.final_score >= 0, f"Negative final_score at n={n}"


# =============================================================================
# Boundary: 21 vs 22 ticks
# =============================================================================

class TestAnalyzeCoinBoundary:

    def test_21_returns_empty_22_proceeds(self):
        """
        Exact boundary: 21 → [] (gate fires), 22 → list (gate does not fire).
        """
        result_21 = _analyze(21)
        result_22 = _analyze(22)

        assert result_21 == [], "21 ticks must return []"
        assert isinstance(result_22, list), "22 ticks must return a list"

    def test_old_gate_no_longer_passes_at_2_ticks(self):
        """The old gate was < 2 (i.e. 2 ticks could produce signals). Verify closed."""
        result = _analyze(2)
        assert result == [], "2 ticks must return [] after BUG-16 fix"

    def test_old_gate_no_longer_passes_at_5_ticks(self):
        result = _analyze(5)
        assert result == [], "5 ticks must return [] after BUG-16 fix"


# =============================================================================
# Regression — BUG-19 test updated for new gate
# =============================================================================

class TestAnalyzeCoinBug19Regression:
    """
    BUG-19's test_analyze_coin_does_not_crash_below_minimum previously
    excluded n=2 because it could produce signals under the old gate.
    Now that BUG-16 raises the gate to 22, n=2 must also return [].
    """

    def test_n_0_1_2_all_return_empty(self):
        for n in (0, 1, 2):
            result = _analyze(n)
            assert result == [], f"Expected [] at n={n}"


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
