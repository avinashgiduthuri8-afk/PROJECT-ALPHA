"""
SP1.1 — Bootstrap test suite
Tests the Scanner's historical data bootstrap and recovery subsystem.

Run:
    python -m pytest tests/test_sp1_1_bootstrap.py -v
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    BootstrapResult,
    _BOOTSTRAP_MIN_CANDLES,
    _BOOTSTRAP_MAX_RETRIES,
    _READY_EMA,
    _READY_MTF_1H,
    _READY_P5,
    PRICE_HISTORY_LIMIT,
    _bootstrap_pair_candidates,
    _candles_to_history,
    _fetch_bootstrap_candles,
    bootstrap_price_history,
)


# =============================================================================
# HELPERS
# =============================================================================

def _make_candles(n: int, base_price: float = 1.0) -> list[dict]:
    """Return *n* syntactically valid candle dicts with unique timestamps."""
    return [
        {
            "time":   (1_700_000_000 + i * 300) * 1000,   # 5-min intervals in ms
            "close":  base_price + i * 0.001,
            "volume": 1000.0 + i,
        }
        for i in range(n)
    ]


def _make_history(n: int) -> list[dict]:
    """Return *n* price-history entries (already converted from candles)."""
    from datetime import datetime, timezone
    return [
        {
            "time":   datetime.fromtimestamp(1_700_000_000 + i * 300, tz=timezone.utc),
            "price":  1.0 + i * 0.001,
            "volume": 1000.0 + i,
        }
        for i in range(n)
    ]


def _run(coro):
    """Run a coroutine synchronously (helper for non-async tests)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# 1. BootstrapResult
# =============================================================================

class TestBootstrapResult:
    def test_default_failed_coins_is_empty_list(self):
        r = BootstrapResult()
        assert r.failed_coins == []

    def test_summary_lines_contains_key_fields(self):
        r = BootstrapResult(
            coins_attempted=10,
            coins_loaded=8,
            coins_failed=2,
            coins_skipped=0,
            avg_history_len=100.0,
            min_history_len=80,
            ema_ready=True,
            mtf_ready=False,
            phase5_ready=True,
            duration_s=5.3,
            failed_coins=["DOGE", "SHIB"],
        )
        lines = "\n".join(r.summary_lines())
        assert "10" in lines          # coins_attempted
        assert "8" in lines           # coins_loaded
        assert "2" in lines           # coins_failed
        assert "100.0" in lines       # avg_history_len
        assert "YES" in lines         # ema_ready
        assert "NO"  in lines         # mtf_ready
        assert "5.3" in lines         # duration_s

    def test_failed_coins_list_explicit(self):
        r = BootstrapResult(failed_coins=["BTC"])
        assert "BTC" in r.failed_coins


# =============================================================================
# 2. _candles_to_history — conversion and deduplication
# =============================================================================

class TestCandlesToHistory:
    def test_normal_conversion(self):
        candles = _make_candles(30)
        history = _candles_to_history(candles)
        assert len(history) == 30
        assert all("time" in h and "price" in h and "volume" in h for h in history)

    def test_sorted_ascending_by_time(self):
        candles = list(reversed(_make_candles(10)))
        history = _candles_to_history(candles)
        times = [h["time"] for h in history]
        assert times == sorted(times)

    def test_capped_at_price_history_limit(self):
        candles = _make_candles(PRICE_HISTORY_LIMIT + 50)
        history = _candles_to_history(candles)
        assert len(history) == PRICE_HISTORY_LIMIT

    def test_invalid_candles_skipped(self):
        """Candles with close=0 or ts_ms=0 must be dropped."""
        candles = [
            {"time": 1_000_000_000_000, "close": 0.0, "volume": 100},   # zero close
            {"time": 0, "close": 1.0, "volume": 100},                    # zero ts
            {"time": 1_000_000_001_000, "close": 1.5, "volume": 200},   # valid
        ]
        history = _candles_to_history(candles)
        assert len(history) == 1
        assert history[0]["price"] == 1.5

    def test_duplicate_timestamps_deduplicated(self):
        """Duplicate timestamps must produce only one entry (last value wins)."""
        ts = 1_700_000_000_000
        candles = [
            {"time": ts, "close": 1.0, "volume": 100},
            {"time": ts, "close": 2.0, "volume": 200},   # duplicate — should win
        ]
        history = _candles_to_history(candles)
        assert len(history) == 1
        assert history[0]["price"] == 2.0

    def test_empty_candles_returns_empty(self):
        assert _candles_to_history([]) == []

    def test_alternate_field_names(self):
        """CoinDCX sometimes uses 'c', 'v', 't' short keys."""
        candles = [{"t": 1_700_000_000_000, "c": 3.14, "v": 42.0}]
        history = _candles_to_history(candles)
        assert len(history) == 1
        assert history[0]["price"] == pytest.approx(3.14)


# =============================================================================
# 3. _fetch_bootstrap_candles — network and retry logic
# =============================================================================

class TestFetchBootstrapCandles:
    """Patches requests.get to simulate various network conditions."""

    def _ok_response(self, n: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _make_candles(n)
        return resp

    def _empty_response(self) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        return resp

    def _non_200_response(self, code: int = 429) -> MagicMock:
        resp = MagicMock()
        resp.status_code = code
        return resp

    # ── Normal bootstrap ──────────────────────────────────────────────────────

    def test_normal_bootstrap_returns_candles(self):
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response(100)):
            result = _fetch_bootstrap_candles("BTC")
        assert len(result) == 100

    def test_returns_empty_on_all_pairs_empty_response(self):
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._empty_response()):
            result = _fetch_bootstrap_candles("BTC")
        assert result == []

    # ── Partial data ──────────────────────────────────────────────────────────

    def test_partial_history_below_minimum_returns_empty(self):
        """API returns data but fewer candles than _BOOTSTRAP_MIN_CANDLES."""
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response(_BOOTSTRAP_MIN_CANDLES - 1)):
            result = _fetch_bootstrap_candles("DOGE")
        assert result == []

    def test_exactly_min_candles_is_accepted(self):
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response(_BOOTSTRAP_MIN_CANDLES)):
            result = _fetch_bootstrap_candles("ETH")
        assert len(result) == _BOOTSTRAP_MIN_CANDLES

    # ── Retry logic ───────────────────────────────────────────────────────────

    def test_retries_on_timeout_then_succeeds(self):
        """First call times out; second call succeeds."""
        import requests as _req
        side_effects = [_req.exceptions.Timeout(), self._ok_response(50)]
        with patch("bots.scanner_bot.scanner.requests.get", side_effect=side_effects), \
             patch("bots.scanner_bot.scanner.time") as mock_time:
            mock_time.sleep = MagicMock()   # skip actual sleep delay
            mock_time.monotonic.return_value = 0.0  # satisfy _limited_get rate-limit calc
            result = _fetch_bootstrap_candles("SOL")
        assert len(result) == 50

    def test_all_retries_exhausted_returns_empty(self):
        """All _BOOTSTRAP_MAX_RETRIES attempts for every pair time out."""
        import requests as _req
        # Each pair gets _BOOTSTRAP_MAX_RETRIES timeouts; 2 pairs total
        num_calls = 2 * _BOOTSTRAP_MAX_RETRIES
        with patch("bots.scanner_bot.scanner.requests.get",
                   side_effect=[_req.exceptions.Timeout()] * num_calls), \
             patch("bots.scanner_bot.scanner.time") as mock_time:
            mock_time.sleep = MagicMock()
            result = _fetch_bootstrap_candles("XYZ")
        assert result == []

    def test_non_200_does_not_retry_same_pair(self):
        """HTTP 429 is not retried on the same pair; next pair is tried."""
        call_count = {"n": 0}
        def _side(url, params, timeout):
            call_count["n"] += 1
            pair = params.get("pair", "")
            if "_INR" in pair:
                return self._non_200_response(429)   # skip without retry
            return self._ok_response(50)              # USDT pair succeeds

        with patch("bots.scanner_bot.scanner.requests.get", side_effect=_side):
            result = _fetch_bootstrap_candles("ETH")

        assert len(result) == 50
        # INR pair: 1 call (no retry). USDT pair: 1 call. Total: 2.
        assert call_count["n"] == 2

    def test_connection_error_is_retried(self):
        import requests as _req
        side_effects = [
            _req.exceptions.ConnectionError("refused"),
            self._ok_response(60),
        ]
        with patch("bots.scanner_bot.scanner.requests.get", side_effect=side_effects), \
             patch("bots.scanner_bot.scanner.time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.monotonic.return_value = 0.0  # satisfy _limited_get rate-limit calc
            result = _fetch_bootstrap_candles("BNB")
        assert len(result) == 60

    # ── Pair fallback ──────────────────────────────────────────────────────────

    def test_falls_back_to_usdt_when_inr_empty(self):
        def _side(url, params, timeout):
            if "_INR" in params.get("pair", ""):
                return self._empty_response()
            return self._ok_response(80)
        with patch("bots.scanner_bot.scanner.requests.get", side_effect=_side):
            result = _fetch_bootstrap_candles("SOL")
        assert len(result) == 80


# =============================================================================
# 4. bootstrap_price_history — orchestration
# =============================================================================

class TestBootstrapPriceHistory:
    """Patches _fetch_bootstrap_candles at the scanner module level."""

    def _run_bootstrap(self, coins, price_history, fetch_fn):
        with patch("bots.scanner_bot.scanner._fetch_bootstrap_candles", side_effect=fetch_fn):
            return _run(bootstrap_price_history(coins, price_history))

    # ── Normal bootstrap ──────────────────────────────────────────────────────

    def test_normal_bootstrap_loads_all_coins(self):
        coins = ["BTC", "ETH", "SOL"]
        ph: dict = {}
        result = self._run_bootstrap(coins, ph, lambda c: _make_candles(100))
        assert result.coins_loaded == 3
        assert result.coins_failed == 0
        assert all(c in ph for c in coins)

    # ── Restart bootstrap (skip already-loaded coins) ─────────────────────────

    def test_restart_skips_coins_with_sufficient_history(self):
        coins = ["BTC", "ETH"]
        ph = {"BTC": _make_history(_READY_EMA + 5)}   # BTC already loaded
        result = self._run_bootstrap(coins, ph, lambda c: _make_candles(100))
        assert result.coins_skipped == 1
        assert result.coins_loaded  == 1   # ETH fetched

    def test_restart_does_not_corrupt_existing_history(self):
        existing = _make_history(_READY_EMA + 10)
        ph = {"BTC": existing}
        self._run_bootstrap(["BTC"], ph, lambda c: _make_candles(100))
        # BTC was skipped — original list object should still be in ph
        assert ph["BTC"] is existing

    # ── Empty history response ─────────────────────────────────────────────────

    def test_empty_response_marks_coin_as_failed(self):
        ph: dict = {}
        result = self._run_bootstrap(["BTC"], ph, lambda c: [])
        assert result.coins_failed == 1
        assert "BTC" in result.failed_coins
        assert "BTC" not in ph

    # ── Partial historical data ───────────────────────────────────────────────

    def test_partial_data_below_minimum_marked_as_failed(self):
        """Candles that convert to fewer than _BOOTSTRAP_MIN_CANDLES are rejected."""
        ph: dict = {}
        # Return candles that convert to < min (e.g., all with close=0 except 2)
        def _partial(coin):
            return [{"time": 1_000_000_000_000, "close": 1.0, "volume": 1.0}] * 2
        result = self._run_bootstrap(["ETH"], ph, _partial)
        assert result.coins_failed == 1
        assert "ETH" not in ph

    # ── Missing candles (some coins fail, others succeed) ─────────────────────

    def test_one_failed_coin_does_not_abort_others(self):
        """
        SP1.1 critical: return_exceptions=True ensures a single coin failure
        does not cancel the rest.
        """
        def _fetch(coin):
            if coin == "FAIL":
                raise RuntimeError("simulated network crash")
            return _make_candles(100)

        coins = ["BTC", "FAIL", "ETH"]
        ph: dict = {}
        result = self._run_bootstrap(coins, ph, _fetch)
        assert "BTC" in ph
        assert "ETH" in ph
        assert "FAIL" not in ph
        assert result.coins_failed == 1

    # ── Duplicate candle prevention ───────────────────────────────────────────

    def test_no_duplicate_timestamps_in_loaded_history(self):
        def _fetch(coin):
            # Return candles where first entry is duplicated
            c = _make_candles(50)
            return [c[0]] + c   # duplicate first candle
        ph: dict = {}
        self._run_bootstrap(["BTC"], ph, _fetch)
        history = ph.get("BTC", [])
        times = [h["time"] for h in history]
        assert len(times) == len(set(times)), "Duplicate timestamps found in loaded history"

    # ── BootstrapResult fields ────────────────────────────────────────────────

    def test_result_counts_are_accurate(self):
        coins = ["BTC", "ETH", "FAIL"]
        ph = {"BTC": _make_history(_READY_EMA + 1)}   # BTC skipped

        def _fetch(coin):
            if coin == "FAIL":
                return []
            return _make_candles(100)

        result = self._run_bootstrap(coins, ph, _fetch)
        assert result.coins_attempted == 3
        assert result.coins_skipped   == 1   # BTC
        assert result.coins_loaded    == 1   # ETH
        assert result.coins_failed    == 1   # FAIL

    def test_ema_ready_flag_set_correctly(self):
        ph: dict = {}
        result = self._run_bootstrap(
            ["BTC"], ph, lambda c: _make_candles(_READY_EMA + 10)
        )
        assert result.ema_ready is True

    def test_ema_ready_false_when_not_enough(self):
        ph: dict = {}
        # All coins fail — min_history_len = 0
        result = self._run_bootstrap(["BTC"], ph, lambda c: [])
        assert result.ema_ready is False

    def test_duration_is_positive(self):
        ph: dict = {}
        result = self._run_bootstrap(["BTC"], ph, lambda c: _make_candles(50))
        assert result.duration_s >= 0.0

    # ── Failed symbol recovery ────────────────────────────────────────────────

    def test_failed_coins_listed_in_result(self):
        coins = ["AAA", "BBB", "CCC"]
        ph: dict = {}
        result = self._run_bootstrap(coins, ph, lambda c: [])
        assert set(result.failed_coins) == {"AAA", "BBB", "CCC"}

    def test_successful_coins_not_in_failed_list(self):
        coins = ["BTC", "FAIL"]
        ph: dict = {}

        def _fetch(coin):
            return _make_candles(80) if coin == "BTC" else []

        result = self._run_bootstrap(coins, ph, _fetch)
        assert "BTC"  not in result.failed_coins
        assert "FAIL" in  result.failed_coins


# =============================================================================
# 5. _bootstrap_pair_candidates
# =============================================================================

class TestBootstrapPairCandidates:
    def test_returns_inr_and_usdt_pairs(self):
        pairs = _bootstrap_pair_candidates("BTC")
        pair_strs = [p for p, _ in pairs]
        assert "B-BTC_INR"  in pair_strs
        assert "B-BTC_USDT" in pair_strs

    def test_coin_is_uppercased(self):
        pairs = _bootstrap_pair_candidates("eth")
        assert all("ETH" in p for p, _ in pairs)


# =============================================================================
# 6. Integration — Scanner.run_bootstrap
# =============================================================================

class TestScannerRunBootstrap:
    """
    Tests Scanner.run_bootstrap() in isolation, mocking the network layer.
    Does not start the FastAPI app or the scan loop.
    """

    def _make_scanner(self):
        from bots.scanner_bot.scanner import (
            Scanner,
            SignalPerformanceTracker,
            WatchlistStore,
        )

        async def _noop_alert(signal, source):
            pass

        ws = WatchlistStore()
        tr = SignalPerformanceTracker()
        return Scanner(watchlist_store=ws, alert_callback=_noop_alert, performance_tracker=tr)

    def test_bootstrap_disabled_returns_empty_result(self):
        import os
        with patch.dict(os.environ, {"BOOTSTRAP_ENABLED": "false"}):
            # Re-evaluate the constant in the module
            with patch("bots.scanner_bot.scanner.BOOTSTRAP_ENABLED", False):
                sc = self._make_scanner()
                result = _run(sc.run_bootstrap())
        assert isinstance(result, BootstrapResult)
        assert result.coins_attempted == 0

    def test_bootstrap_with_ticker_fetch_failure_returns_empty_result(self):
        sc = self._make_scanner()
        with patch.object(sc, "get_tickers", side_effect=RuntimeError("network down")):
            result = _run(sc.run_bootstrap())
        assert isinstance(result, BootstrapResult)
        assert result.coins_attempted == 0

    def test_bootstrap_result_stored_on_scanner(self):
        sc = self._make_scanner()
        fake_tickers = [
            {"market": "BTCINR",  "last_price": "50000", "volume": "1000000",
             "quote_volume": "50000000000"},
        ]
        with patch.object(sc, "get_tickers", return_value=fake_tickers), \
             patch("bots.scanner_bot.scanner._fetch_bootstrap_candles",
                   return_value=_make_candles(100)):
            result = _run(sc.run_bootstrap())
        assert sc._bootstrap_result is result
        assert isinstance(result, BootstrapResult)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
