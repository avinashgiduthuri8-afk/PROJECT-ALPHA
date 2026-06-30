"""
SP1.3 BUG-22 — _scan_many exception logging
Tests that when individual coin scans raise exceptions:
  - The coin name, exception type, and message are logged.
  - Remaining coins continue scanning normally.
  - The scanner does not crash or re-raise.
  - Successful coins still produce signals.

Run:
    python -m pytest tests/test_sp1_3_bug22.py -v
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    Scanner,
    Signal,
    SignalPerformanceTracker,
    WatchlistStore,
)


# =============================================================================
# Helpers
# =============================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_scanner() -> Scanner:
    async def _noop(signal, source):
        pass
    return Scanner(
        watchlist_store=WatchlistStore(),
        alert_callback=_noop,
        performance_tracker=SignalPerformanceTracker(),
    )


def _make_ticker(market: str = "BTCINR", price: str = "50000") -> dict:
    return {
        "market":       market,
        "last_price":   price,
        "volume":       "1000000",
        "quote_volume": "50000000000",
    }


def _fake_signal(coin: str = "BTC") -> Signal:
    from datetime import datetime, timezone
    return Signal(
        coin=coin, kind="candidate", score=65,
        message="test signal", price=50000.0, volume=1e6,
        created_at=datetime.now(timezone.utc),
        tier="CANDIDATE", reasons=["EMA crossover", "Volume spike"],
        volume_strength=2.5, momentum_strength=1.2,
        model_version="vTest",
        phase5_trend=10, phase5_pullback=5, phase5_momentum=8,
        phase5_risk_reward=12, phase5_total=35,
        final_score=55,
        hist_trend_7d=12, hist_trend_30d=12, hist_trend_90d=12,
        hist_sr_quality=12, hist_vol_score=12, hist_total=60,
        coin_class="A", market_state="bull_trend",
        opportunity_type="continuation", opp_confidence=75,
        opportunity_score=72, priority="High", risk_level="low",
    )


# =============================================================================
# Tests
# =============================================================================

class TestScanManyExceptionLogging:

    def _run_scan_many(self, sc: Scanner, coins: list, ticker_map: dict,
                       side_effects: dict) -> list:
        """
        Run _scan_many with _scan_ticker_bounded patched per-coin.
        side_effects: {coin: Exception | list[Signal]}
        """
        original = sc._scan_ticker_bounded

        async def _patched(coin, ticker, source):
            effect = side_effects.get(coin)
            if isinstance(effect, Exception):
                raise effect
            if effect is not None:
                return effect
            return await original(coin, ticker, source)

        sc._scan_ticker_bounded = _patched
        return _run(sc._scan_many(coins, ticker_map, "watchlist"))

    # ── One coin fails, others succeed ───────────────────────────────────────

    def test_one_failing_coin_does_not_prevent_others(self):
        sc = _make_scanner()
        ticker_map = {
            "BTC":  _make_ticker("BTCINR",  "50000"),
            "FAIL": _make_ticker("FAILINR", "1"),
            "ETH":  _make_ticker("ETHINR",  "3000"),
        }
        btc_sig = _fake_signal("BTC")
        eth_sig = _fake_signal("ETH")
        side_effects = {
            "BTC":  [btc_sig],
            "FAIL": RuntimeError("simulated crash"),
            "ETH":  [eth_sig],
        }
        results = self._run_scan_many(sc, ["BTC", "FAIL", "ETH"], ticker_map, side_effects)
        coins_in_results = {s.coin for s in results}
        assert "BTC" in coins_in_results or "ETH" in coins_in_results
        assert "FAIL" not in coins_in_results

    # ── Multiple coins fail ───────────────────────────────────────────────────

    def test_multiple_failing_coins_are_all_skipped(self):
        sc = _make_scanner()
        ticker_map = {
            "A": _make_ticker("AINR", "10"),
            "B": _make_ticker("BINR", "20"),
            "C": _make_ticker("CINR", "30"),
        }
        btc_sig = _fake_signal("A")
        side_effects = {
            "A": [btc_sig],
            "B": ValueError("bad data"),
            "C": ZeroDivisionError("div by zero"),
        }
        results = self._run_scan_many(sc, ["A", "B", "C"], ticker_map, side_effects)
        result_coins = {s.coin for s in results}
        assert "B" not in result_coins
        assert "C" not in result_coins

    # ── Exception logging — coin ──────────────────────────────────────────────

    def test_failing_coin_name_is_logged(self, caplog):
        sc = _make_scanner()
        ticker_map = {"FAIL": _make_ticker("FAILINR", "1")}
        side_effects = {"FAIL": RuntimeError("network down")}
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            self._run_scan_many(sc, ["FAIL"], ticker_map, side_effects)
        assert any("FAIL" in r.message for r in caplog.records)

    # ── Exception logging — exception type ───────────────────────────────────

    def test_exception_type_is_logged(self, caplog):
        sc = _make_scanner()
        ticker_map = {"FAIL": _make_ticker("FAILINR", "1")}
        side_effects = {"FAIL": ZeroDivisionError("division by zero")}
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            self._run_scan_many(sc, ["FAIL"], ticker_map, side_effects)
        assert any("ZeroDivisionError" in r.message for r in caplog.records)

    # ── Exception logging — exception message ─────────────────────────────────

    def test_exception_message_is_logged(self, caplog):
        sc = _make_scanner()
        ticker_map = {"FAIL": _make_ticker("FAILINR", "1")}
        side_effects = {"FAIL": RuntimeError("specific error detail")}
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            self._run_scan_many(sc, ["FAIL"], ticker_map, side_effects)
        assert any("specific error detail" in r.message for r in caplog.records)

    # ── Scanner does not crash ────────────────────────────────────────────────

    def test_scanner_does_not_raise_on_coin_exception(self):
        sc = _make_scanner()
        ticker_map = {"FAIL": _make_ticker("FAILINR", "1")}
        side_effects = {"FAIL": Exception("total failure")}
        # Must not raise
        result = self._run_scan_many(sc, ["FAIL"], ticker_map, side_effects)
        assert isinstance(result, list)

    def test_scanner_returns_empty_list_when_all_coins_fail(self):
        sc = _make_scanner()
        ticker_map = {
            "A": _make_ticker("AINR", "10"),
            "B": _make_ticker("BINR", "20"),
        }
        side_effects = {
            "A": RuntimeError("fail A"),
            "B": RuntimeError("fail B"),
        }
        result = self._run_scan_many(sc, ["A", "B"], ticker_map, side_effects)
        assert result == []

    # ── Successful coins still produce signals ────────────────────────────────

    def test_successful_coins_produce_signals_alongside_failures(self):
        sc = _make_scanner()
        ticker_map = {
            "BTC":  _make_ticker("BTCINR",  "50000"),
            "FAIL": _make_ticker("FAILINR", "1"),
        }
        btc_sig = _fake_signal("BTC")
        side_effects = {
            "BTC":  [btc_sig],
            "FAIL": RuntimeError("crash"),
        }
        results = self._run_scan_many(sc, ["BTC", "FAIL"], ticker_map, side_effects)
        assert any(s.coin == "BTC" for s in results)

    # ── No regression — all coins succeed ─────────────────────────────────────

    def test_all_coins_succeed_no_errors_logged(self, caplog):
        sc = _make_scanner()
        ticker_map = {
            "BTC": _make_ticker("BTCINR", "50000"),
            "ETH": _make_ticker("ETHINR", "3000"),
        }
        side_effects = {
            "BTC": [_fake_signal("BTC")],
            "ETH": [_fake_signal("ETH")],
        }
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            self._run_scan_many(sc, ["BTC", "ETH"], ticker_map, side_effects)
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) == 0

    def test_empty_coin_list_returns_empty(self):
        sc = _make_scanner()
        result = _run(sc._scan_many([], {}, "watchlist"))
        assert result == []

    # ── Different exception types ─────────────────────────────────────────────

    def test_zero_division_error_logged_with_type(self, caplog):
        sc = _make_scanner()
        ticker_map = {"FAIL": _make_ticker("FAILINR", "1")}
        side_effects = {"FAIL": ZeroDivisionError("float division by zero")}
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            self._run_scan_many(sc, ["FAIL"], ticker_map, side_effects)
        assert any("ZeroDivisionError" in r.message for r in caplog.records)
        assert any("float division by zero" in r.message for r in caplog.records)

    def test_value_error_logged_with_type(self, caplog):
        sc = _make_scanner()
        ticker_map = {"FAIL": _make_ticker("FAILINR", "1")}
        side_effects = {"FAIL": ValueError("invalid candle data")}
        with caplog.at_level(logging.ERROR, logger="scanner_bot"):
            self._run_scan_many(sc, ["FAIL"], ticker_map, side_effects)
        assert any("ValueError" in r.message for r in caplog.records)
        assert any("invalid candle data" in r.message for r in caplog.records)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
