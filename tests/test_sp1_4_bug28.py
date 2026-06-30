"""
SP1.4 BUG-28 — /coins readiness flag accuracy
Tests that the readiness flags returned by scanner_coins() match the actual
thresholds enforced by analyze_coin() and phase5_score(), and that the new
analyze_ready flag is present and correct.

Run:
    python -m pytest tests/test_sp1_4_bug28.py -v
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    ANALYZE_MIN_HISTORY,
    PHASE5_MIN_HISTORY,
    MTF_1H_WINDOW,
)


# =============================================================================
# Helpers
# =============================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_history(n: int) -> list:
    return [
        {
            "time":   datetime(2024, 1, 1, tzinfo=timezone.utc),
            "price":  100.0 + i * 0.5,
            "volume": 1000.0,
        }
        for i in range(n)
    ]


def _make_scanner_with_history(coin_histories: dict) -> MagicMock:
    """Return a mock Scanner whose price_history contains the given coin→history map."""
    sc = MagicMock()
    sc.price_history = {coin: _make_history(n) for coin, n in coin_histories.items()}
    return sc


async def _call_coins_endpoint(scanner_mock) -> list:
    """Import and call scanner_coins() with _SCANNER patched to scanner_mock."""
    import bots.scanner_bot.main as main_mod
    with patch.object(main_mod, "_SCANNER", scanner_mock):
        response = await main_mod.scanner_coins()
    import json
    return json.loads(response.body)


def _coins(coin_histories: dict) -> list:
    scanner = _make_scanner_with_history(coin_histories)
    return _run(_call_coins_endpoint(scanner))


def _coin(coin_histories: dict, coin_name: str) -> dict:
    results = _coins(coin_histories)
    return next(r for r in results if r["coin"] == coin_name)


# =============================================================================
# Constant alignment sanity
# =============================================================================

class TestConstantAlignment:

    def test_analyze_min_history_is_22(self):
        assert ANALYZE_MIN_HISTORY == 22

    def test_phase5_min_history_is_21(self):
        assert PHASE5_MIN_HISTORY == 21

    def test_mtf_1h_window_is_48(self):
        assert MTF_1H_WINDOW == 48

    def test_analyze_min_greater_than_phase5_min(self):
        assert ANALYZE_MIN_HISTORY > PHASE5_MIN_HISTORY

    def test_phase5_min_less_than_mtf_1h(self):
        assert PHASE5_MIN_HISTORY < MTF_1H_WINDOW


# =============================================================================
# analyze_ready flag
# =============================================================================

class TestAnalyzeReadyFlag:

    def test_analyze_ready_key_present(self):
        result = _coin({"BTC": 30}, "BTC")
        assert "analyze_ready" in result

    def test_analyze_ready_false_below_threshold(self):
        for n in (0, 1, 10, 20, 21):
            result = _coin({"BTC": n}, "BTC")
            assert result["analyze_ready"] is False, (
                f"analyze_ready should be False at n={n}"
            )

    def test_analyze_ready_true_at_threshold(self):
        result = _coin({"BTC": ANALYZE_MIN_HISTORY}, "BTC")
        assert result["analyze_ready"] is True

    def test_analyze_ready_true_above_threshold(self):
        for n in (22, 30, 48, 120):
            result = _coin({"BTC": n}, "BTC")
            assert result["analyze_ready"] is True, (
                f"analyze_ready should be True at n={n}"
            )

    def test_analyze_ready_boundary_21_vs_22(self):
        """Exact boundary: 21 → False, 22 → True."""
        r21 = _coin({"BTC": 21}, "BTC")
        r22 = _coin({"ETH": 22}, "ETH")
        assert r21["analyze_ready"] is False
        assert r22["analyze_ready"] is True


# =============================================================================
# phase5_ready flag — now uses PHASE5_MIN_HISTORY (21), not _READY_P5 (20)
# =============================================================================

class TestPhase5ReadyFlag:

    def test_phase5_ready_key_present(self):
        result = _coin({"BTC": 30}, "BTC")
        assert "phase5_ready" in result

    def test_phase5_ready_false_below_threshold(self):
        for n in (0, 1, 5, 10, 20):
            result = _coin({"BTC": n}, "BTC")
            assert result["phase5_ready"] is False, (
                f"phase5_ready should be False at n={n}"
            )

    def test_phase5_ready_false_at_old_stale_threshold_20(self):
        """
        BUG-28 regression: the old code used _READY_P5=20, reporting
        phase5_ready=True at 20 ticks when phase5_score returns zeros.
        Must now be False at 20 ticks.
        """
        result = _coin({"BTC": 20}, "BTC")
        assert result["phase5_ready"] is False

    def test_phase5_ready_true_at_threshold(self):
        result = _coin({"BTC": PHASE5_MIN_HISTORY}, "BTC")
        assert result["phase5_ready"] is True

    def test_phase5_ready_true_above_threshold(self):
        for n in (21, 22, 48, 120):
            result = _coin({"BTC": n}, "BTC")
            assert result["phase5_ready"] is True, (
                f"phase5_ready should be True at n={n}"
            )

    def test_phase5_ready_boundary_20_vs_21(self):
        """Exact boundary: 20 → False, 21 → True."""
        r20 = _coin({"BTC": 20}, "BTC")
        r21 = _coin({"ETH": 21}, "ETH")
        assert r20["phase5_ready"] is False
        assert r21["phase5_ready"] is True


# =============================================================================
# mtf_ready flag — unchanged (MTF_1H_WINDOW=48)
# =============================================================================

class TestMtfReadyFlag:

    def test_mtf_ready_key_present(self):
        result = _coin({"BTC": 50}, "BTC")
        assert "mtf_ready" in result

    def test_mtf_ready_false_below_threshold(self):
        for n in (0, 22, 30, 47):
            result = _coin({"BTC": n}, "BTC")
            assert result["mtf_ready"] is False, (
                f"mtf_ready should be False at n={n}"
            )

    def test_mtf_ready_true_at_threshold(self):
        result = _coin({"BTC": MTF_1H_WINDOW}, "BTC")
        assert result["mtf_ready"] is True

    def test_mtf_ready_true_above_threshold(self):
        result = _coin({"BTC": 120}, "BTC")
        assert result["mtf_ready"] is True

    def test_mtf_ready_boundary_47_vs_48(self):
        r47 = _coin({"BTC": 47}, "BTC")
        r48 = _coin({"ETH": 48}, "ETH")
        assert r47["mtf_ready"] is False
        assert r48["mtf_ready"] is True


# =============================================================================
# ema_ready flag removed — verify it is absent (replaced by analyze_ready)
# =============================================================================

class TestEmaReadyRemoved:

    def test_ema_ready_key_not_present(self):
        """
        BUG-28: ema_ready used EMA_SLOW_PERIOD=21 which was off by 1
        from ANALYZE_MIN_HISTORY=22. It has been replaced by analyze_ready.
        """
        result = _coin({"BTC": 30}, "BTC")
        assert "ema_ready" not in result


# =============================================================================
# Response structure
# =============================================================================

class TestCoinsResponseStructure:

    def test_required_keys_present(self):
        result = _coin({"BTC": 50}, "BTC")
        required = {"coin", "history_len", "analyze_ready",
                    "phase5_ready", "mtf_ready", "market_state"}
        assert required == set(result.keys())

    def test_history_len_accurate(self):
        for n in (0, 10, 22, 48, 100):
            result = _coin({"BTC": n}, "BTC")
            assert result["history_len"] == n

    def test_multiple_coins_all_have_flags(self):
        results = _coins({"BTC": 50, "ETH": 20, "SOL": 5})
        assert len(results) == 3
        for r in results:
            assert "analyze_ready" in r
            assert "phase5_ready"  in r
            assert "mtf_ready"     in r

    def test_sorted_by_history_len_descending(self):
        results = _coins({"BTC": 100, "ETH": 22, "SOL": 5})
        lens = [r["history_len"] for r in results]
        assert lens == sorted(lens, reverse=True)

    def test_scanner_none_returns_empty_list(self):
        import bots.scanner_bot.main as main_mod
        with patch.object(main_mod, "_SCANNER", None):
            response = _run(main_mod.scanner_coins())
        import json
        assert json.loads(response.body) == []

    def test_flag_ordering_consistent_with_thresholds(self):
        """
        At any history length, the flags must satisfy:
        analyze_ready → phase5_ready (analyze gate is higher)
        phase5_ready does NOT imply analyze_ready
        mtf_ready → analyze_ready and phase5_ready
        """
        for n in range(0, 60):
            r = _coin({"BTC": n}, "BTC")
            if r["analyze_ready"]:
                assert r["phase5_ready"], (
                    f"analyze_ready=True but phase5_ready=False at n={n}"
                )
            if r["mtf_ready"]:
                assert r["analyze_ready"], (
                    f"mtf_ready=True but analyze_ready=False at n={n}"
                )
                assert r["phase5_ready"], (
                    f"mtf_ready=True but phase5_ready=False at n={n}"
                )


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
