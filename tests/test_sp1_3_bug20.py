"""
SP1.3 BUG-20 — historical_pattern_score exception handler
Tests that any exception inside historical_pattern_score() is caught,
logged with coin name / exception type / message, and the neutral default
score (12,12,12,12,12,60) is returned instead of propagating into analyze_coin.

Run:
    python -m pytest tests/test_sp1_3_bug20.py -v
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    HistoricalPatternScore,
    historical_pattern_score,
)

# The expected neutral default
NEUTRAL = HistoricalPatternScore(12, 12, 12, 12, 12, 60)


# =============================================================================
# Helpers
# =============================================================================

def _hist_score(coin: str, price: float, fetch_side_effect=None, fetch_return=None):
    """Call historical_pattern_score with a mocked _fetch_daily_candles."""
    kwargs = {}
    if fetch_side_effect is not None:
        kwargs["side_effect"] = fetch_side_effect
    elif fetch_return is not None:
        kwargs["return_value"] = fetch_return

    with patch("bots.scanner_bot.scanner._fetch_daily_candles", **kwargs):
        return historical_pattern_score(coin, price)


# =============================================================================
# Neutral default returned on exception
# =============================================================================

class TestHistoricalPatternScoreExceptionHandler:

    def test_runtime_error_returns_neutral(self):
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=RuntimeError("network down"))
        assert result == NEUTRAL

    def test_zero_division_error_returns_neutral(self):
        """BUG-17 aftermath: if ZeroDivisionError somehow slips through, catch it."""
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=ZeroDivisionError("float division by zero"))
        assert result == NEUTRAL

    def test_value_error_returns_neutral(self):
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=ValueError("bad candle data"))
        assert result == NEUTRAL

    def test_type_error_returns_neutral(self):
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=TypeError("unexpected type"))
        assert result == NEUTRAL

    def test_key_error_returns_neutral(self):
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=KeyError("close"))
        assert result == NEUTRAL

    def test_attribute_error_returns_neutral(self):
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=AttributeError("NoneType"))
        assert result == NEUTRAL

    def test_generic_exception_returns_neutral(self):
        result = _hist_score("BTC", 50000.0,
                             fetch_side_effect=Exception("unknown failure"))
        assert result == NEUTRAL

    def test_does_not_raise_on_any_exception(self):
        """historical_pattern_score must never propagate an exception."""
        for exc_class in (
            RuntimeError, ValueError, ZeroDivisionError,
            TypeError, KeyError, AttributeError, Exception,
        ):
            try:
                _hist_score("BTC", 50000.0,
                            fetch_side_effect=exc_class("test"))
            except Exception as e:
                pytest.fail(
                    f"historical_pattern_score raised {type(e).__name__} "
                    f"for {exc_class.__name__} — must not propagate"
                )

    def test_neutral_score_has_correct_total(self):
        result = _hist_score("ETH", 3000.0,
                             fetch_side_effect=RuntimeError("down"))
        assert result.total == 60

    def test_neutral_score_all_components_are_12(self):
        result = _hist_score("SOL", 100.0,
                             fetch_side_effect=RuntimeError("down"))
        assert result.trend_7d   == 12
        assert result.trend_30d  == 12
        assert result.trend_90d  == 12
        assert result.sr_quality == 12
        assert result.hist_vol   == 12


# =============================================================================
# Exception logging — coin, type, message
# =============================================================================

class TestHistoricalPatternScoreExceptionLogging:

    def test_coin_name_is_logged_on_exception(self, caplog):
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            _hist_score("DOGE", 1.0,
                        fetch_side_effect=RuntimeError("down"))
        assert any("DOGE" in r.message for r in caplog.records)

    def test_exception_type_is_logged(self, caplog):
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            _hist_score("BTC", 50000.0,
                        fetch_side_effect=ZeroDivisionError("division by zero"))
        assert any("ZeroDivisionError" in r.message for r in caplog.records)

    def test_exception_message_is_logged(self, caplog):
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            _hist_score("ETH", 3000.0,
                        fetch_side_effect=RuntimeError("specific error detail"))
        assert any("specific error detail" in r.message for r in caplog.records)

    def test_log_level_is_error(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="scanner_bot"):
            _hist_score("BTC", 50000.0,
                        fetch_side_effect=RuntimeError("down"))
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1

    def test_no_error_logged_on_success(self, caplog):
        """No exception → no error log."""
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": 100.0 + i}
            for i in range(30)
        ]
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            _hist_score("BTC", 115.0, fetch_return=candles)
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 0

    def test_type_not_logged_as_literal_type_string(self, caplog):
        """
        Regression for the original bug: type(Exception).__name__ == 'type'
        (wrong — always 'type'). After fix: type(exc).__name__ == actual class name.
        """
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            _hist_score("BTC", 50000.0,
                        fetch_side_effect=ValueError("bad data"))
        # The log must NOT contain the literal string 'type' as the exception_type value
        # (it should contain 'ValueError' instead)
        for record in caplog.records:
            if "exception_type=type " in record.message:
                pytest.fail(
                    f"Log still uses type(Exception).__name__ ('type') "
                    f"instead of actual exception class name: {record.message}"
                )
        assert any("ValueError" in r.message for r in caplog.records)


# =============================================================================
# No regression — successful path unchanged
# =============================================================================

class TestHistoricalPatternScoreSuccessPath:

    def test_empty_candles_returns_neutral(self):
        result = _hist_score("BTC", 50000.0, fetch_return=[])
        assert result == NEUTRAL

    def test_fewer_than_5_closes_returns_neutral(self):
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": 100.0 + i}
            for i in range(4)
        ]
        result = _hist_score("BTC", 102.0, fetch_return=candles)
        assert result == NEUTRAL

    def test_valid_candles_return_histscore(self):
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": 100.0 + i * 0.5}
            for i in range(30)
        ]
        result = _hist_score("BTC", 114.0, fetch_return=candles)
        assert isinstance(result, HistoricalPatternScore)
        assert 0 <= result.total <= 100

    def test_returns_histpatternscorescore_dataclass(self):
        candles = [
            {"time": 1_700_000_000 + i * 86400, "close": 100.0 + i}
            for i in range(20)
        ]
        result = _hist_score("ETH", 115.0, fetch_return=candles)
        assert hasattr(result, "trend_7d")
        assert hasattr(result, "trend_30d")
        assert hasattr(result, "trend_90d")
        assert hasattr(result, "sr_quality")
        assert hasattr(result, "hist_vol")
        assert hasattr(result, "total")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
