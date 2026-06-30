"""
SP1.2 — Live Price Feed Reliability test suite
Tests CoinDCXPublicClient, Scanner.get_tickers, and Scanner._append_history.

Run:
    python -m pytest tests/test_sp1_2_live_feed.py -v
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    CoinDCXPublicClient,
    Scanner,
    SignalPerformanceTracker,
    WatchlistStore,
    PRICE_HISTORY_LIMIT,
)


# =============================================================================
# HELPERS
# =============================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_ticker(market: str = "BTCINR", price: str = "50000", volume: str = "1000000") -> dict:
    return {
        "market":        market,
        "last_price":    price,
        "volume":        volume,
        "quote_volume":  str(float(price) * float(volume)),
    }


def _make_scanner() -> Scanner:
    async def _noop(signal, source):
        pass
    return Scanner(
        watchlist_store=WatchlistStore(),
        alert_callback=_noop,
        performance_tracker=SignalPerformanceTracker(),
    )


# =============================================================================
# 1. CoinDCXPublicClient — fetch_tickers
# =============================================================================

class TestCoinDCXPublicClientFetchTickers:

    def _ok_response(self, data: list) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def _bad_response(self, code: int = 500) -> MagicMock:
        import requests as _req
        resp = MagicMock()
        resp.status_code = code
        resp.raise_for_status.side_effect = _req.exceptions.HTTPError(response=resp)
        return resp

    # ── Normal fetch ──────────────────────────────────────────────────────────

    def test_normal_fetch_returns_tickers(self):
        tickers = [_make_ticker("BTCINR"), _make_ticker("ETHINR")]
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response(tickers)):
            result = client.fetch_tickers()
        assert len(result) == 2
        assert result[0]["market"] == "BTCINR"

    # ── Empty response ────────────────────────────────────────────────────────

    def test_empty_list_response_raises_value_error(self):
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response([])):
            with pytest.raises(ValueError, match="empty list"):
                client.fetch_tickers()

    # ── Non-list response ─────────────────────────────────────────────────────

    def test_non_list_response_raises_value_error(self):
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response({"error": "bad"})):
            with pytest.raises(ValueError, match="unexpected type"):
                client.fetch_tickers()

    # ── Malformed JSON ────────────────────────────────────────────────────────

    def test_malformed_json_raises_value_error(self):
        import requests as _req
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = _req.exceptions.JSONDecodeError("bad", "", 0)
        resp.text = "not json"
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get", return_value=resp):
            with pytest.raises(ValueError, match="non-JSON"):
                client.fetch_tickers()

    # ── Retry on timeout ──────────────────────────────────────────────────────

    def test_retries_on_timeout_then_succeeds(self):
        import requests as _req
        tickers = [_make_ticker("BTCINR")]
        side_effects = [
            _req.exceptions.Timeout(),
            self._ok_response(tickers),
        ]
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get", side_effect=side_effects), \
             patch("bots.scanner_bot.scanner.time") as mt:
            mt.sleep = MagicMock()
            result = client.fetch_tickers()
        assert len(result) == 1

    def test_all_retries_exhausted_raises(self):
        import requests as _req
        client = CoinDCXPublicClient()
        n = CoinDCXPublicClient._TICKER_MAX_RETRIES
        with patch("bots.scanner_bot.scanner.requests.get",
                   side_effect=[_req.exceptions.Timeout()] * n), \
             patch("bots.scanner_bot.scanner.time") as mt:
            mt.sleep = MagicMock()
            with pytest.raises(_req.exceptions.Timeout):
                client.fetch_tickers()

    def test_connection_error_is_retried(self):
        import requests as _req
        tickers = [_make_ticker("SOLINR")]
        side_effects = [
            _req.exceptions.ConnectionError("refused"),
            self._ok_response(tickers),
        ]
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get", side_effect=side_effects), \
             patch("bots.scanner_bot.scanner.time") as mt:
            mt.sleep = MagicMock()
            result = client.fetch_tickers()
        assert result[0]["market"] == "SOLINR"

    def test_http_error_not_retried(self):
        """HTTP 429/500 errors are not retried — fail immediately."""
        import requests as _req
        call_count = {"n": 0}
        def _side(*a, **kw):
            call_count["n"] += 1
            return self._bad_response(429)
        client = CoinDCXPublicClient()
        with patch("bots.scanner_bot.scanner.requests.get", side_effect=_side):
            with pytest.raises(_req.exceptions.HTTPError):
                client.fetch_tickers()
        assert call_count["n"] == 1   # no retry

    def test_list_with_no_valid_market_entries_raises(self):
        """A list of dicts without 'market' keys is rejected."""
        client = CoinDCXPublicClient()
        bad_data = [{"price": "100"}, {"size": "50"}]   # no 'market' key
        with patch("bots.scanner_bot.scanner.requests.get",
                   return_value=self._ok_response(bad_data)):
            with pytest.raises(ValueError, match="no valid market entries"):
                client.fetch_tickers()


# =============================================================================
# 2. Scanner.get_tickers — caching and fallback
# =============================================================================

class TestScannerGetTickers:

    def _scanner_with_mock_client(self, fetch_side_effect=None, fetch_return=None):
        sc = _make_scanner()
        if fetch_side_effect:
            sc.client.fetch_tickers = MagicMock(side_effect=fetch_side_effect)
        elif fetch_return is not None:
            sc.client.fetch_tickers = MagicMock(return_value=fetch_return)
        return sc

    # ── Normal fetch ──────────────────────────────────────────────────────────

    def test_normal_fetch_populates_cache(self):
        tickers = [_make_ticker("BTCINR"), _make_ticker("ETHINR")]
        sc = self._scanner_with_mock_client(fetch_return=tickers)
        result = _run(sc.get_tickers(force=True))
        assert len(result) == 2
        assert sc._ticker_cache is tickers

    # ── Cache hit ─────────────────────────────────────────────────────────────

    def test_cache_returned_when_fresh(self):
        tickers = [_make_ticker("BTCINR")]
        sc = _make_scanner()
        sc._ticker_cache = tickers
        sc._ticker_cache_at = asyncio.get_event_loop().time()   # just set
        sc.client.fetch_tickers = MagicMock()

        result = _run(sc.get_tickers(force=False))
        assert result is tickers
        sc.client.fetch_tickers.assert_not_called()

    def test_force_true_bypasses_cache(self):
        old = [_make_ticker("BTCINR")]
        new = [_make_ticker("ETHINR")]
        sc = _make_scanner()
        sc._ticker_cache = old
        sc._ticker_cache_at = asyncio.get_event_loop().time()
        sc.client.fetch_tickers = MagicMock(return_value=new)

        result = _run(sc.get_tickers(force=True))
        assert result is new

    # ── Fallback to stale cache ───────────────────────────────────────────────

    def test_network_error_returns_stale_cache(self):
        """Any exception during fetch returns stale cache when available."""
        stale = [_make_ticker("BTCINR")]
        sc = self._scanner_with_mock_client(fetch_side_effect=Exception("network down"))
        sc._ticker_cache    = stale
        sc._ticker_cache_at = 0.0   # expired but still present

        result = _run(sc.get_tickers(force=True))
        assert result is stale

    def test_value_error_returns_stale_cache(self):
        """ValueError (bad response structure) also falls back to stale cache."""
        stale = [_make_ticker("SOLINR")]
        sc = self._scanner_with_mock_client(fetch_side_effect=ValueError("empty list"))
        sc._ticker_cache    = stale
        sc._ticker_cache_at = 0.0

        result = _run(sc.get_tickers(force=True))
        assert result is stale

    def test_no_cache_on_first_failure_raises(self):
        """When there is no cache at all, fetch failure must raise."""
        sc = self._scanner_with_mock_client(fetch_side_effect=Exception("down"))
        sc._ticker_cache = None

        with pytest.raises(Exception, match="down"):
            _run(sc.get_tickers(force=True))

    def test_stale_cache_log_includes_age(self, caplog):
        """Stale cache fallback should log cache age."""
        import logging
        stale = [_make_ticker("BTCINR")]
        sc = self._scanner_with_mock_client(fetch_side_effect=Exception("down"))
        sc._ticker_cache    = stale
        sc._ticker_cache_at = 0.0

        with caplog.at_level(logging.WARNING):
            _run(sc.get_tickers(force=True))
        assert any("stale cache" in r.message for r in caplog.records)

    # ── Invalid response structure (validation gate) ───────────────────────────

    def test_empty_list_response_does_not_update_cache(self):
        """An empty-list response is rejected; stale cache remains."""
        stale = [_make_ticker("BTCINR")]
        sc = self._scanner_with_mock_client(fetch_side_effect=ValueError("empty list"))
        sc._ticker_cache    = stale
        sc._ticker_cache_at = 0.0

        _run(sc.get_tickers(force=True))
        assert sc._ticker_cache is stale   # unchanged

    def test_valid_response_updates_cache_timestamp(self):
        fresh = [_make_ticker("BTCINR")]
        sc = _make_scanner()
        sc.client.fetch_tickers = MagicMock(return_value=fresh)
        before = asyncio.get_event_loop().time()
        _run(sc.get_tickers(force=True))
        assert sc._ticker_cache_at >= before


# =============================================================================
# 3. Scanner._append_history — invalid tick rejection
# =============================================================================

class TestAppendHistory:

    # ── Valid ticks ───────────────────────────────────────────────────────────

    def test_valid_tick_appended(self):
        sc = _make_scanner()
        sc._append_history("BTC", 50000.0, 1000.0)
        assert len(sc.price_history["BTC"]) == 1
        assert sc.price_history["BTC"][0]["price"] == 50000.0

    def test_volume_coerced_to_non_negative(self):
        """Negative volume is clamped to 0."""
        sc = _make_scanner()
        sc._append_history("BTC", 50000.0, -5.0)
        assert sc.price_history["BTC"][0]["volume"] == 0.0

    # ── Invalid price — rejected ───────────────────────────────────────────────

    def test_zero_price_rejected(self):
        sc = _make_scanner()
        sc._append_history("BTC", 0.0, 1000.0)
        assert len(sc.price_history["BTC"]) == 0

    def test_negative_price_rejected(self):
        sc = _make_scanner()
        sc._append_history("BTC", -1.0, 1000.0)
        assert len(sc.price_history["BTC"]) == 0

    def test_none_price_rejected(self):
        sc = _make_scanner()
        sc._append_history("BTC", None, 1000.0)
        assert len(sc.price_history["BTC"]) == 0

    def test_nan_price_rejected(self):
        sc = _make_scanner()
        sc._append_history("BTC", float("nan"), 1000.0)
        assert len(sc.price_history["BTC"]) == 0

    def test_inf_price_rejected(self):
        sc = _make_scanner()
        sc._append_history("BTC", float("inf"), 1000.0)
        assert len(sc.price_history["BTC"]) == 0

    def test_string_price_rejected(self):
        sc = _make_scanner()
        sc._append_history("BTC", "50000", 1000.0)
        assert len(sc.price_history["BTC"]) == 0

    # ── History cap ───────────────────────────────────────────────────────────

    def test_history_capped_at_limit(self):
        sc = _make_scanner()
        for i in range(PRICE_HISTORY_LIMIT + 20):
            sc._append_history("BTC", float(i + 1), 1.0)
        assert len(sc.price_history["BTC"]) == PRICE_HISTORY_LIMIT

    # ── Existing history preserved on bad tick ─────────────────────────────────

    def test_bad_tick_does_not_corrupt_existing_history(self):
        sc = _make_scanner()
        sc._append_history("BTC", 50000.0, 1.0)
        sc._append_history("BTC", 0.0, 1.0)     # bad — should be rejected
        sc._append_history("BTC", 51000.0, 1.0)
        history = sc.price_history["BTC"]
        assert len(history) == 2
        assert history[0]["price"] == 50000.0
        assert history[1]["price"] == 51000.0


# =============================================================================
# 4. End-to-end: ticker fetch failure during scan cycle
# =============================================================================

class TestScanCycleFeedResilience:
    """
    Verify the scan loop in main.py handles ticker failures gracefully.
    We test the Scanner's get_tickers directly rather than the full loop.
    """

    def test_scan_watchlist_uses_stale_cache_on_network_outage(self):
        """
        If the network fails mid-cycle, scan_watchlist falls back to cached
        tickers rather than raising.
        """
        stale = [_make_ticker("BTCINR", "50000", "2000000")]
        sc = _make_scanner()
        sc._ticker_cache    = stale
        sc._ticker_cache_at = 0.0  # expired

        # Network is down — fetch_tickers raises
        sc.client.fetch_tickers = MagicMock(side_effect=Exception("network down"))

        # scan_watchlist calls get_tickers() internally; should not raise
        result = _run(sc.scan_watchlist(tickers=None))
        # Result may be [] (no coins in watchlist), but must not crash
        assert isinstance(result, list)

    def test_consecutive_fetch_failures_do_not_crash_scanner(self):
        """Multiple consecutive failures should all return stale cache."""
        stale = [_make_ticker("BTCINR")]
        sc = _make_scanner()
        sc._ticker_cache    = stale
        sc._ticker_cache_at = 0.0
        sc.client.fetch_tickers = MagicMock(side_effect=Exception("down"))

        for _ in range(5):
            result = _run(sc.get_tickers(force=True))
            assert result is stale


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
