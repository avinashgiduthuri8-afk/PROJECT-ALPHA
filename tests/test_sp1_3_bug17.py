"""
SP1.3 BUG-17 — _sr_quality_score ZeroDivisionError fix
Tests that zero/string-zero closes no longer crash the support/resistance scorer
or historical_pattern_score.

Run:
    python -m pytest tests/test_sp1_3_bug17.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    _sr_quality_score,
    historical_pattern_score,
)


# =============================================================================
# Helper
# =============================================================================

def _closes(n: int, base: float = 100.0) -> list:
    """Return n valid positive closes."""
    return [base + i * 0.5 for i in range(n)]


# =============================================================================
# _sr_quality_score
# =============================================================================

class TestSrQualityScoreZeroClose:

    def test_normal_closes_no_crash(self):
        closes = _closes(15, 100.0)
        score = _sr_quality_score(closes, 107.0)
        assert isinstance(score, int)
        assert 0 <= score <= 25

    def test_zero_close_does_not_raise(self):
        """BUG-17: a 0.0 in closes must not raise ZeroDivisionError."""
        closes = [0.0] + _closes(14, 100.0)
        score = _sr_quality_score(closes, 107.0)
        assert isinstance(score, int)
        assert 0 <= score <= 25

    def test_multiple_zero_closes_do_not_raise(self):
        closes = [0.0, 0.0, 0.0] + _closes(12, 100.0)
        score = _sr_quality_score(closes, 107.0)
        assert isinstance(score, int)

    def test_all_zero_closes_returns_default(self):
        """All zeros — no valid levels found — returns neutral default 12."""
        closes = [0.0] * 15
        score = _sr_quality_score(closes, 107.0)
        assert score == 12

    def test_negative_close_does_not_raise(self):
        closes = [-50.0] + _closes(14, 100.0)
        score = _sr_quality_score(closes, 107.0)
        assert isinstance(score, int)

    def test_fewer_than_10_closes_returns_default(self):
        closes = _closes(9, 100.0)
        assert _sr_quality_score(closes, 107.0) == 12

    def test_zero_current_price_returns_default(self):
        closes = _closes(15, 100.0)
        assert _sr_quality_score(closes, 0.0) == 12

    def test_valid_closes_produce_nonzero_score(self):
        """A cluster of closes near current price should score > 0."""
        closes = [100.0] * 10 + [105.0] * 5
        score = _sr_quality_score(closes, 103.0)
        assert score > 0


# =============================================================================
# historical_pattern_score — closes filter
# =============================================================================

class TestHistoricalPatternScoreClosesFilter:

    def _make_candles(self, closes: list) -> list:
        """Build fake candle dicts from a list of close values."""
        return [
            {"time": 1_700_000_000 + i * 86400, "close": str(c)}
            for i, c in enumerate(closes)
        ]

    def test_string_zero_close_excluded(self):
        """
        BUG-17: '0.0' as string is truthy but float('0.0') == 0.0.
        It must be excluded from closes before _sr_quality_score is called.
        """
        # Mix valid closes with a string zero
        raw_closes = ["0.0"] + [str(100.0 + i) for i in range(20)]
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": c}
            for i, c in enumerate(raw_closes)
        ]
        with patch("bots.scanner_bot.scanner._fetch_daily_candles", return_value=candles):
            # Must not raise ZeroDivisionError
            result = historical_pattern_score("BTC", 110.0)
        assert result.total >= 0

    def test_numeric_zero_close_excluded(self):
        """Numeric 0 in close field must also be excluded."""
        raw_closes = [0] + list(range(100, 121))
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": c}
            for i, c in enumerate(raw_closes)
        ]
        with patch("bots.scanner_bot.scanner._fetch_daily_candles", return_value=candles):
            result = historical_pattern_score("ETH", 110.0)
        assert result.total >= 0

    def test_all_zero_closes_returns_neutral_score(self):
        """All zero closes → fewer than 5 valid closes → neutral default."""
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": 0}
            for i in range(20)
        ]
        with patch("bots.scanner_bot.scanner._fetch_daily_candles", return_value=candles):
            result = historical_pattern_score("DOGE", 1.0)
        # Should return the neutral default (12,12,12,12,12,60)
        assert result.total == 60

    def test_no_candles_returns_neutral_score(self):
        with patch("bots.scanner_bot.scanner._fetch_daily_candles", return_value=[]):
            result = historical_pattern_score("SOL", 50.0)
        assert result.total == 60

    def test_valid_candles_produce_result(self):
        candles = self._make_candles([100.0 + i * 0.5 for i in range(30)])
        with patch("bots.scanner_bot.scanner._fetch_daily_candles", return_value=candles):
            result = historical_pattern_score("BTC", 114.0)
        assert 0 <= result.total <= 100


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
