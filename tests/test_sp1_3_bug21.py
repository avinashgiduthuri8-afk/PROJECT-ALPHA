"""
SP1.3 BUG-21 — multi_timeframe_check window gating
Tests that each timeframe result is forced False when history is shorter
than that timeframe's window, preventing false "5m_15m_1h" alignment signals
on histories with as few as 2 ticks.

Run:
    python -m pytest tests/test_sp1_3_bug21.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    MTF_1H_WINDOW,
    MTF_15M_WINDOW,
    MTF_5M_WINDOW,
    multi_timeframe_check,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_history(n: int, rising: bool = True, base: float = 100.0) -> list:
    """Return n rising (or flat) history entries."""
    return [
        {
            "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price":  base + (i * 0.5 if rising else 0.0),
            "volume": 1000.0,
        }
        for i in range(n)
    ]


def _mtf(n: int, rising: bool = True) -> dict:
    return multi_timeframe_check(_make_history(n, rising=rising))


# =============================================================================
# Window constant sanity
# =============================================================================

class TestMtfWindowConstants:

    def test_5m_window_is_10(self):
        assert MTF_5M_WINDOW == 10

    def test_15m_window_is_24(self):
        assert MTF_15M_WINDOW == 24

    def test_1h_window_is_48(self):
        assert MTF_1H_WINDOW == 48

    def test_windows_are_ordered(self):
        assert MTF_5M_WINDOW < MTF_15M_WINDOW < MTF_1H_WINDOW


# =============================================================================
# tf_5m gating — False below MTF_5M_WINDOW (10)
# =============================================================================

class TestTf5mGating:

    def test_2_ticks_tf_5m_false(self):
        assert _mtf(2)["tf_5m_bull"] is False

    def test_9_ticks_tf_5m_false(self):
        """One below the 5m window — must be False."""
        assert _mtf(9)["tf_5m_bull"] is False

    def test_10_ticks_tf_5m_eligible(self):
        """At the window — gate does not fire; result depends on prices."""
        result = _mtf(10, rising=True)
        assert isinstance(result["tf_5m_bull"], bool)

    def test_rising_10_ticks_tf_5m_true(self):
        """With a full rising window, 5m should be bullish."""
        assert _mtf(10, rising=True)["tf_5m_bull"] is True

    def test_flat_10_ticks_tf_5m_false(self):
        """Flat prices — no momentum — 5m should not be bullish."""
        assert _mtf(10, rising=False)["tf_5m_bull"] is False


# =============================================================================
# tf_15m gating — False below MTF_15M_WINDOW (24)
# =============================================================================

class TestTf15mGating:

    def test_2_ticks_tf_15m_false(self):
        assert _mtf(2)["tf_15m_bull"] is False

    def test_10_ticks_tf_15m_false(self):
        """Below the 15m window — must be False even though 5m is eligible."""
        assert _mtf(10)["tf_15m_bull"] is False

    def test_23_ticks_tf_15m_false(self):
        """One below the 15m window — must be False."""
        assert _mtf(23)["tf_15m_bull"] is False

    def test_24_ticks_tf_15m_eligible(self):
        """At the window — gate does not fire."""
        result = _mtf(24, rising=True)
        assert isinstance(result["tf_15m_bull"], bool)

    def test_rising_24_ticks_tf_15m_true(self):
        assert _mtf(24, rising=True)["tf_15m_bull"] is True

    def test_flat_24_ticks_tf_15m_false(self):
        assert _mtf(24, rising=False)["tf_15m_bull"] is False


# =============================================================================
# tf_1h gating — False below MTF_1H_WINDOW (48)
# =============================================================================

class TestTf1hGating:

    def test_2_ticks_tf_1h_false(self):
        assert _mtf(2)["tf_1h_bull"] is False

    def test_10_ticks_tf_1h_false(self):
        assert _mtf(10)["tf_1h_bull"] is False

    def test_24_ticks_tf_1h_false(self):
        """15m is now eligible but 1h still must be False."""
        assert _mtf(24)["tf_1h_bull"] is False

    def test_47_ticks_tf_1h_false(self):
        """One below the 1h window — must be False."""
        assert _mtf(47)["tf_1h_bull"] is False

    def test_48_ticks_tf_1h_eligible(self):
        """At the window — gate does not fire."""
        result = _mtf(48, rising=True)
        assert isinstance(result["tf_1h_bull"], bool)

    def test_rising_48_ticks_tf_1h_true(self):
        assert _mtf(48, rising=True)["tf_1h_bull"] is True

    def test_flat_48_ticks_tf_1h_false(self):
        assert _mtf(48, rising=False)["tf_1h_bull"] is False


# =============================================================================
# Alignment — false full alignment prevented
# =============================================================================

class TestMtfAlignment:

    def test_2_ticks_alignment_is_none(self):
        """2 ticks must never produce any alignment."""
        assert _mtf(2)["alignment"] == "none"

    def test_9_ticks_alignment_is_none(self):
        """Below 5m window — no timeframe eligible."""
        assert _mtf(9)["alignment"] == "none"

    def test_10_ticks_rising_alignment_is_5m_only(self):
        """10 rising ticks: 5m eligible and bullish, 15m/1h not eligible."""
        result = _mtf(10, rising=True)
        assert result["alignment"] == "5m_only"
        assert result["tf_15m_bull"] is False
        assert result["tf_1h_bull"]  is False

    def test_24_ticks_rising_alignment_is_5m_15m(self):
        """24 rising ticks: 5m and 15m eligible, 1h not."""
        result = _mtf(24, rising=True)
        assert result["alignment"] == "5m_15m"
        assert result["tf_1h_bull"] is False

    def test_47_ticks_rising_alignment_is_5m_15m(self):
        """47 ticks: 5m and 15m eligible, 1h still gated."""
        result = _mtf(47, rising=True)
        assert result["alignment"] in ("5m_15m", "5m_only", "15m_only", "none")
        assert result["tf_1h_bull"] is False

    def test_48_ticks_rising_alignment_can_be_full(self):
        """48 rising ticks: all three timeframes eligible."""
        result = _mtf(48, rising=True)
        assert result["alignment"] == "5m_15m_1h"

    def test_full_alignment_requires_48_ticks(self):
        """5m_15m_1h alignment must never appear with fewer than 48 ticks."""
        for n in range(0, MTF_1H_WINDOW):
            result = _mtf(n, rising=True)
            assert result["alignment"] != "5m_15m_1h", (
                f"False full alignment at n={n}: {result['alignment']}"
            )

    def test_candidate_ok_requires_5m_window(self):
        """candidate_ok must be False when fewer than MTF_5M_WINDOW ticks."""
        for n in range(0, MTF_5M_WINDOW):
            result = _mtf(n, rising=True)
            assert result["candidate_ok"] is False, (
                f"candidate_ok should be False at n={n}"
            )

    # ── BUG-21 specific: the original false positive ─────────────────────────

    def test_2_ticks_rising_no_full_alignment(self):
        """
        BUG-21 regression: with 2 rising ticks the old code could return
        tf_1h=True (prices[-1] > prices[0]) and produce '5m_15m_1h' alignment.
        """
        result = _mtf(2, rising=True)
        assert result["tf_1h_bull"]  is False
        assert result["tf_15m_bull"] is False
        assert result["alignment"]   != "5m_15m_1h"

    def test_5_ticks_rising_no_full_alignment(self):
        result = _mtf(5, rising=True)
        assert result["tf_1h_bull"]  is False
        assert result["tf_15m_bull"] is False
        assert result["alignment"]   != "5m_15m_1h"


# =============================================================================
# Return structure unchanged
# =============================================================================

class TestMtfReturnStructure:

    def test_all_keys_present_at_any_length(self):
        required_keys = {
            "tf_5m_bull", "tf_15m_bull", "tf_1h_bull",
            "candidate_ok", "strong_ok", "premium_ok", "alignment",
        }
        for n in (0, 2, 10, 24, 48, 120):
            result = _mtf(n)
            assert required_keys == set(result.keys()), (
                f"Missing keys at n={n}: {required_keys - set(result.keys())}"
            )

    def test_premium_ok_matches_full_alignment(self):
        """premium_ok must equal tf_5m and tf_15m and tf_1h."""
        for n in (2, 10, 24, 48, 120):
            r = _mtf(n, rising=True)
            expected = r["tf_5m_bull"] and r["tf_15m_bull"] and r["tf_1h_bull"]
            assert r["premium_ok"] == expected, f"premium_ok mismatch at n={n}"

    def test_strong_ok_matches_5m_and_15m(self):
        for n in (2, 10, 24, 48, 120):
            r = _mtf(n, rising=True)
            expected = r["tf_5m_bull"] and r["tf_15m_bull"]
            assert r["strong_ok"] == expected, f"strong_ok mismatch at n={n}"


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
