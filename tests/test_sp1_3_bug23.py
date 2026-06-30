"""
SP1.3 BUG-23 — MTF window env var validation
Tests that _validated_mtf_window() clamps values below the minimum (2),
logs a warning for both sub-minimum and sub-default values, and that
valid values are accepted without warnings.

Run:
    python -m pytest tests/test_sp1_3_bug23.py -v
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    _MTF_1H_WINDOW_MIN,
    _MTF_15M_WINDOW_MIN,
    _MTF_5M_WINDOW_MIN,
    _validated_mtf_window,
)


# =============================================================================
# Minimum constant sanity
# =============================================================================

class TestMtfWindowMinConstants:

    def test_5m_minimum_is_2(self):
        assert _MTF_5M_WINDOW_MIN == 2

    def test_15m_minimum_is_2(self):
        assert _MTF_15M_WINDOW_MIN == 2

    def test_1h_minimum_is_2(self):
        assert _MTF_1H_WINDOW_MIN == 2


# =============================================================================
# _validated_mtf_window — return value
# =============================================================================

class TestValidatedMtfWindowReturnValue:

    def _call(self, env_var: str, env_val: str, default: int, minimum: int = 2) -> int:
        with patch.dict(os.environ, {env_var: env_val}):
            return _validated_mtf_window(env_var, default, minimum)

    # ── Below minimum — clamped ───────────────────────────────────────────────

    def test_zero_is_clamped_to_minimum(self):
        result = self._call("MTF_5M_WINDOW", "0", default=10, minimum=2)
        assert result == 2

    def test_one_is_clamped_to_minimum(self):
        result = self._call("MTF_5M_WINDOW", "1", default=10, minimum=2)
        assert result == 2

    def test_negative_is_clamped_to_minimum(self):
        result = self._call("MTF_5M_WINDOW", "-5", default=10, minimum=2)
        assert result == 2

    # ── Between minimum and default — accepted with warning ───────────────────

    def test_value_between_min_and_default_is_accepted(self):
        result = self._call("MTF_5M_WINDOW", "5", default=10, minimum=2)
        assert result == 5

    def test_value_of_2_is_accepted(self):
        result = self._call("MTF_15M_WINDOW", "2", default=24, minimum=2)
        assert result == 2

    def test_value_just_below_default_is_accepted(self):
        result = self._call("MTF_1H_WINDOW", "47", default=48, minimum=2)
        assert result == 47

    # ── At default — accepted without warning ─────────────────────────────────

    def test_default_value_is_accepted(self):
        result = self._call("MTF_5M_WINDOW", "10", default=10, minimum=2)
        assert result == 10

    def test_5m_default_10_is_accepted(self):
        with patch.dict(os.environ, {"MTF_5M_WINDOW": "10"}):
            result = _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        assert result == 10

    def test_15m_default_24_is_accepted(self):
        with patch.dict(os.environ, {"MTF_15M_WINDOW": "24"}):
            result = _validated_mtf_window("MTF_15M_WINDOW", 24, 2)
        assert result == 24

    def test_1h_default_48_is_accepted(self):
        with patch.dict(os.environ, {"MTF_1H_WINDOW": "48"}):
            result = _validated_mtf_window("MTF_1H_WINDOW", 48, 2)
        assert result == 48

    # ── Above default — accepted ──────────────────────────────────────────────

    def test_above_default_is_accepted(self):
        result = self._call("MTF_5M_WINDOW", "20", default=10, minimum=2)
        assert result == 20

    # ── Env var absent — uses default ─────────────────────────────────────────

    def test_missing_env_var_uses_default(self):
        env = {k: v for k, v in os.environ.items() if k != "MTF_5M_WINDOW"}
        with patch.dict(os.environ, env, clear=True):
            result = _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        assert result == 10


# =============================================================================
# _validated_mtf_window — logging
# =============================================================================

class TestValidatedMtfWindowLogging:

    def _call_with_log(self, env_var: str, env_val: str,
                       default: int, minimum: int = 2, caplog=None):
        with patch.dict(os.environ, {env_var: env_val}):
            return _validated_mtf_window(env_var, default, minimum)

    # ── Below minimum — clamping warning logged ───────────────────────────────

    def test_zero_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_5M_WINDOW": "0"}):
            _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        assert any("MTF_5M_WINDOW" in r.message for r in caplog.records)

    def test_zero_log_contains_clamping_info(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_5M_WINDOW": "0"}):
            _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        assert any("clamping" in r.message.lower() for r in caplog.records)

    def test_one_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_15M_WINDOW": "1"}):
            _validated_mtf_window("MTF_15M_WINDOW", 24, 2)
        assert any("MTF_15M_WINDOW" in r.message for r in caplog.records)

    # ── Below default but at/above minimum — sub-default warning logged ───────

    def test_below_default_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_5M_WINDOW": "5"}):
            _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        assert any("MTF_5M_WINDOW" in r.message for r in caplog.records)

    def test_below_default_log_contains_recommended(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_1H_WINDOW": "30"}):
            _validated_mtf_window("MTF_1H_WINDOW", 48, 2)
        assert any("recommended" in r.message.lower() for r in caplog.records)

    # ── At or above default — no warning ────────────────────────────────────

    def test_default_value_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_5M_WINDOW": "10"}):
            _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    def test_above_default_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, {"MTF_5M_WINDOW": "15"}):
            _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    def test_absent_env_var_no_warning(self, caplog):
        env = {k: v for k, v in os.environ.items() if k != "MTF_5M_WINDOW"}
        with caplog.at_level(logging.WARNING, logger="scanner_bot"), \
             patch.dict(os.environ, env, clear=True):
            _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0


# =============================================================================
# Original silent behaviour no longer occurs
# =============================================================================

class TestMtfWindowZeroNoLongerSilent:

    def test_zero_no_longer_returns_zero(self):
        """
        BUG-23 regression: previously int(os.getenv('MTF_5M_WINDOW', '10'))
        with env='0' silently returned 0, causing prices[-0:] == prices[:].
        Now it must return the minimum (2) instead.
        """
        with patch.dict(os.environ, {"MTF_5M_WINDOW": "0"}):
            result = _validated_mtf_window("MTF_5M_WINDOW", 10, 2)
        assert result != 0
        assert result == 2

    def test_one_no_longer_returns_one(self):
        """
        A window of 1 causes _frame_bullish to always return False
        (len(slice_prices) < 2). Must be clamped to 2.
        """
        with patch.dict(os.environ, {"MTF_15M_WINDOW": "1"}):
            result = _validated_mtf_window("MTF_15M_WINDOW", 24, 2)
        assert result != 1
        assert result == 2


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
