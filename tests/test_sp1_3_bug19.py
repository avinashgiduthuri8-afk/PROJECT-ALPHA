"""
SP1.3 BUG-19 — Volatility baseline minimum history guard
Tests that the "High volatility breakout" signal is never awarded when history
is shorter than VOLATILITY_MIN_HISTORY (41 ticks), preventing a degenerate
2-item baseline from generating false breakout signals during warm-up.

Run:
    python -m pytest tests/test_sp1_3_bug19.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    VOLATILITY_LOOKBACK,
    VOLATILITY_MIN_HISTORY,
    analyze_coin,
)

# =============================================================================
# Helpers
# =============================================================================

def _make_history(n: int, *, prices=None, volumes=None) -> list:
    """
    Build a price-history list of length n.

    If prices is provided it is used directly (must have exactly n entries).
    Otherwise a monotonically rising sequence is generated so that EMA
    crossover and volume spike gates also pass, making the volatility block
    reachable.
    """
    if prices is None:
        prices = [100.0 + i * 0.5 for i in range(n)]
    if volumes is None:
        volumes = [1_000_000.0] * n
    return [
        {
            "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price":  prices[i],
            "volume": volumes[i],
        }
        for i in range(n)
    ]


def _history_with_volatility_spike(n: int) -> list:
    """
    Build a history of length n that should trigger a volatility spike
    IF the volatility block runs (current window much more volatile than
    baseline window).

    Structure:
    - First half: flat prices (low volatility baseline)
    - Second half: wildly oscillating prices (high current volatility)

    Also designed so EMA crossover and volume spike gates pass:
    - Prices end higher than they start (EMA fast > slow eventually)
    - Last tick has a 10× volume spike
    """
    flat_count = n // 2
    volatile_count = n - flat_count

    flat_prices     = [100.0] * flat_count
    volatile_prices = [100.0 + (i % 2) * 20.0 for i in range(volatile_count)]
    # Ensure the final price is above the first (for EMA crossover to fire).
    # Guard against n=0/1 where volatile_prices may be empty.
    if volatile_prices:
        volatile_prices[-1] = 125.0

    prices = flat_prices + volatile_prices

    # Normal volume for all ticks except last (which gets a spike).
    # Guard against n=0 where volumes would be empty.
    base_vol = 500_000.0
    volumes = [base_vol] * n
    if volumes:
        volumes[-1] = base_vol * 10   # volume spike to pass Gate 2

    return _make_history(n, prices=prices, volumes=volumes)


def _reasons_from_signals(signals: list) -> list[str]:
    """Collect all reason strings from a list of Signal objects."""
    reasons = []
    for sig in signals:
        reasons.extend(sig.reasons)
    return reasons


# =============================================================================
# Constant sanity
# =============================================================================

class TestVolatilityMinHistoryConstant:

    def test_constant_value_is_41(self):
        assert VOLATILITY_MIN_HISTORY == 41

    def test_constant_equals_lookback_formula(self):
        assert VOLATILITY_MIN_HISTORY == VOLATILITY_LOOKBACK * 2 + 1


# =============================================================================
# Below minimum — volatility block must not run
# =============================================================================

class TestVolatilityBlockSkippedBelowMinimum:
    """
    These tests confirm 'High volatility breakout' is never awarded when
    len(prices) < VOLATILITY_MIN_HISTORY, regardless of how volatile the
    price movement appears.
    """

    def _no_volatility_reason(self, n: int):
        history = _history_with_volatility_spike(n)
        # Patch historical_pattern_score to avoid network calls
        with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
             patch("bots.scanner_bot.scanner.get_historical_performance",
                   return_value={"perf_90d": None}):
            from bots.scanner_bot.scanner import HistoricalPatternScore
            mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)
            signals = analyze_coin("BTC", history)
        reasons = _reasons_from_signals(signals)
        return reasons

    def test_22_ticks_no_volatility_breakout(self):
        """22 ticks — old guard was > 21 (i.e. >= 22) — still below new minimum."""
        reasons = self._no_volatility_reason(22)
        assert "High volatility breakout" not in reasons

    def test_30_ticks_no_volatility_breakout(self):
        reasons = self._no_volatility_reason(30)
        assert "High volatility breakout" not in reasons

    def test_40_ticks_no_volatility_breakout(self):
        """40 is exactly one below VOLATILITY_MIN_HISTORY=41."""
        reasons = self._no_volatility_reason(40)
        assert "High volatility breakout" not in reasons


# =============================================================================
# At and above minimum — block may run
# =============================================================================

class TestVolatilityBlockRunsAtMinimum:

    def test_41_ticks_volatility_block_is_eligible(self):
        """
        With 41 ticks, the volatility block is allowed to run.
        We verify it does not crash and the result is a valid signal list.
        (Whether the reason fires depends on the actual price data.)
        """
        history = _history_with_volatility_spike(41)
        with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
             patch("bots.scanner_bot.scanner.get_historical_performance",
                   return_value={"perf_90d": None}):
            from bots.scanner_bot.scanner import HistoricalPatternScore
            mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)
            signals = analyze_coin("BTC", history)
        assert isinstance(signals, list)

    def test_120_ticks_volatility_block_is_eligible(self):
        """Full history — volatility block must be reachable."""
        history = _history_with_volatility_spike(120)
        with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
             patch("bots.scanner_bot.scanner.get_historical_performance",
                   return_value={"perf_90d": None}):
            from bots.scanner_bot.scanner import HistoricalPatternScore
            mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)
            signals = analyze_coin("BTC", history)
        assert isinstance(signals, list)


# =============================================================================
# Boundary: 40 vs 41 ticks
# =============================================================================

class TestVolatilityBlockBoundary:

    def test_40_ticks_block_skipped_41_ticks_block_runs(self):
        """
        The exact boundary: at 40 the block is skipped, at 41 it is eligible.
        We verify the block skips by confirming 'High volatility breakout'
        cannot appear at 40 ticks even with a highly volatile pattern.
        """
        with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
             patch("bots.scanner_bot.scanner.get_historical_performance",
                   return_value={"perf_90d": None}):
            from bots.scanner_bot.scanner import HistoricalPatternScore
            mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)

            signals_40 = analyze_coin("BTC", _history_with_volatility_spike(40))
            signals_41 = analyze_coin("BTC", _history_with_volatility_spike(41))

        reasons_40 = _reasons_from_signals(signals_40)
        assert "High volatility breakout" not in reasons_40, (
            "40 ticks must not produce 'High volatility breakout'"
        )
        # At 41 we only verify no crash — the signal may or may not fire
        # depending on actual baseline vs current volatility calculation
        assert isinstance(signals_41, list)


# =============================================================================
# Regression — other analyze_coin behaviour unchanged
# =============================================================================

class TestVolatilityBlockRegression:

    def _analyze(self, n: int):
        history = _history_with_volatility_spike(n)
        with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
             patch("bots.scanner_bot.scanner.get_historical_performance",
                   return_value={"perf_90d": None}):
            from bots.scanner_bot.scanner import HistoricalPatternScore
            mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)
            return analyze_coin("BTC", history)

    def test_analyze_coin_returns_list_at_all_lengths(self):
        for n in (0, 1, 5, 22, 40, 41, 60, 120):
            result = self._analyze(n)
            assert isinstance(result, list), f"Expected list at n={n}"

    def test_analyze_coin_does_not_crash_below_minimum(self):
        """Below minimum of analyze_coin (len < 2): no exception, returns [].
        Note: n=2 is currently the minimum for analyze_coin (BUG-16 will raise
        this to 22). For now only n=0 and n=1 are guaranteed to return [].
        """
        for n in (0, 1):
            result = self._analyze(n)
            assert result == [], f"Expected [] at n={n}, got {result}"

    def test_score_without_volatility_bonus_still_valid(self):
        """
        Signals generated below VOLATILITY_MIN_HISTORY must still have
        valid scores (EMA crossover=25 + volume=20 + momentum optional).
        The absence of the volatility bonus (+10) must not crash scoring.
        """
        history = _history_with_volatility_spike(40)
        with patch("bots.scanner_bot.scanner.historical_pattern_score") as mock_hist, \
             patch("bots.scanner_bot.scanner.get_historical_performance",
                   return_value={"perf_90d": None}):
            from bots.scanner_bot.scanner import HistoricalPatternScore
            mock_hist.return_value = HistoricalPatternScore(12, 12, 12, 12, 12, 60)
            signals = analyze_coin("BTC", history)

        for sig in signals:
            assert sig.score >= 0
            assert sig.final_score >= 0


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
