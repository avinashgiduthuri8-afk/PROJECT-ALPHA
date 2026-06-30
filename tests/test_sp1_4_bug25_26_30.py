"""
SP1.4 BUG-25 + BUG-26 + BUG-30 — Watchlist POST validation
Tests that /api/v1/scanner/watchlist (POST) validates coin symbols via the
centralized validate_coin_symbol() helper before they reach
WatchlistStore.add(), and that the response status accurately reflects
rejected / already_exists / success outcomes.

Run:
    python -m pytest tests/test_sp1_4_bug25_26_30.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.scanner_bot.scanner import (
    COIN_SYMBOL_MAX_LENGTH,
    WatchlistStore,
    validate_coin_symbol,
)
import bots.scanner_bot.main as main_mod


# =============================================================================
# Helpers
# =============================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _tmp_watchlist_store() -> tuple[WatchlistStore, Path]:
    """Create a WatchlistStore backed by a temp file, starting empty."""
    tmp_dir = tempfile.mkdtemp()
    path = Path(tmp_dir) / "watchlist.json"
    path.write_text(json.dumps({"coins": []}), encoding="utf-8")
    store = WatchlistStore(path=str(path))
    store._coins = []   # force empty regardless of DEFAULT_WATCHLIST fallback
    store.save()
    return store, path


def _post_watchlist(coin_value: str, store: WatchlistStore) -> dict:
    """Call watchlist_add() with _SCANNER patched to a mock exposing store."""
    from unittest.mock import MagicMock
    mock_scanner = MagicMock()
    mock_scanner.watchlist_store = store

    from bots.scanner_bot.main import _AddCoinBody, watchlist_add
    body = _AddCoinBody(coin=coin_value)
    with patch.object(main_mod, "_SCANNER", mock_scanner):
        response = _run(watchlist_add(body))
    return json.loads(response.body)


# =============================================================================
# validate_coin_symbol — unit tests
# =============================================================================

class TestValidateCoinSymbolUnit:

    # ── Empty / whitespace (BUG-25) ───────────────────────────────────────────

    def test_empty_string_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("")
        assert is_valid is False
        assert symbol == ""
        assert reason == "invalid_coin"

    def test_whitespace_only_rejected(self):
        for raw in (" ", "  ", "\t", "\n", "\t\n "):
            is_valid, symbol, reason = validate_coin_symbol(raw)
            assert is_valid is False, f"Expected rejection for {raw!r}"
            assert symbol == ""
            assert reason == "invalid_coin"

    # ── Normalization ─────────────────────────────────────────────────────────

    def test_lowercase_normalized_to_uppercase(self):
        is_valid, symbol, reason = validate_coin_symbol("btc")
        assert is_valid is True
        assert symbol == "BTC"

    def test_mixed_case_normalized(self):
        is_valid, symbol, reason = validate_coin_symbol("BtC")
        assert is_valid is True
        assert symbol == "BTC"

    def test_leading_trailing_whitespace_trimmed(self):
        is_valid, symbol, reason = validate_coin_symbol("  btc  ")
        assert is_valid is True
        assert symbol == "BTC"

    # ── Format validation (BUG-26 / BUG-30) ───────────────────────────────────

    def test_slash_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC/USDT")
        assert is_valid is False
        assert reason == "invalid_coin"

    def test_hyphen_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC-USDT")
        assert is_valid is False

    def test_internal_space_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC USDT")
        assert is_valid is False

    def test_semicolon_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC;")
        assert is_valid is False

    def test_dollar_sign_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC$")
        assert is_valid is False

    def test_at_symbol_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC@")
        assert is_valid is False

    def test_alphanumeric_accepted(self):
        is_valid, symbol, reason = validate_coin_symbol("BTC2")
        assert is_valid is True
        assert symbol == "BTC2"

    def test_numeric_only_accepted(self):
        """Pure digits are technically valid per the A-Z0-9 rule."""
        is_valid, symbol, reason = validate_coin_symbol("1000")
        assert is_valid is True

    # ── Length validation (BUG-26) ────────────────────────────────────────────

    def test_max_length_accepted(self):
        symbol_in = "A" * COIN_SYMBOL_MAX_LENGTH
        is_valid, symbol, reason = validate_coin_symbol(symbol_in)
        assert is_valid is True
        assert len(symbol) == COIN_SYMBOL_MAX_LENGTH

    def test_over_max_length_rejected(self):
        symbol_in = "A" * (COIN_SYMBOL_MAX_LENGTH + 1)
        is_valid, symbol, reason = validate_coin_symbol(symbol_in)
        assert is_valid is False
        assert reason == "invalid_coin"

    def test_very_long_symbol_rejected(self):
        is_valid, symbol, reason = validate_coin_symbol("A" * 200)
        assert is_valid is False


# =============================================================================
# Endpoint — rejected responses
# =============================================================================

class TestWatchlistAddRejected:

    def test_empty_string_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("", store)
        assert result["status"] == "rejected"
        assert result["reason"] == "invalid_coin"
        assert result["coin"]   == ""

    def test_whitespace_only_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("   ", store)
        assert result["status"] == "rejected"
        assert result["coin"]   == ""

    def test_tab_only_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("\t", store)
        assert result["status"] == "rejected"

    def test_newline_only_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("\n", store)
        assert result["status"] == "rejected"

    def test_slash_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("BTC/USDT", store)
        assert result["status"] == "rejected"
        assert result["reason"] == "invalid_coin"

    def test_semicolon_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("BTC;", store)
        assert result["status"] == "rejected"

    def test_internal_space_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("BTC USDT", store)
        assert result["status"] == "rejected"

    def test_dollar_sign_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("BTC$", store)
        assert result["status"] == "rejected"

    def test_oversized_symbol_returns_rejected(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("A" * 11, store)
        assert result["status"] == "rejected"

    def test_rejected_never_says_success(self):
        store, _ = _tmp_watchlist_store()
        for bad in ("", "  ", "BTC/USDT", "BTC;", "A" * 50):
            result = _post_watchlist(bad, store)
            assert result["status"] != "success", f"Got success for {bad!r}"


# =============================================================================
# Endpoint — successful add
# =============================================================================

class TestWatchlistAddSuccess:

    def test_lowercase_input_succeeds(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("btc", store)
        assert result["status"] == "success"
        assert result["coin"]   == "BTC"

    def test_response_structure_on_success(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("eth", store)
        assert set(result.keys()) == {"status", "coin", "count"}

    def test_count_reflects_watchlist_size(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("sol", store)
        assert result["count"] == len(store.all())

    def test_valid_symbol_with_digits_succeeds(self):
        store, _ = _tmp_watchlist_store()
        result = _post_watchlist("1inch", store)
        assert result["status"] == "success"
        assert result["coin"]   == "1INCH"


# =============================================================================
# Endpoint — duplicate handling
# =============================================================================

class TestWatchlistAddDuplicate:

    def test_duplicate_returns_already_exists(self):
        store, _ = _tmp_watchlist_store()
        first  = _post_watchlist("btc", store)
        second = _post_watchlist("btc", store)
        assert first["status"]  == "success"
        assert second["status"] == "already_exists"
        assert second["coin"]   == "BTC"

    def test_duplicate_case_insensitive(self):
        store, _ = _tmp_watchlist_store()
        _post_watchlist("btc", store)
        result = _post_watchlist("BTC", store)
        assert result["status"] == "already_exists"

    def test_duplicate_does_not_increase_count(self):
        store, _ = _tmp_watchlist_store()
        first  = _post_watchlist("eth", store)
        second = _post_watchlist("eth", store)
        assert first["count"] == second["count"]

    def test_duplicate_never_says_success(self):
        store, _ = _tmp_watchlist_store()
        _post_watchlist("sol", store)
        result = _post_watchlist("sol", store)
        assert result["status"] != "success"


# =============================================================================
# Watchlist file integrity — rejected requests must not modify storage
# =============================================================================

class TestWatchlistFileUnchangedOnRejection:

    def test_file_unchanged_after_empty_rejection(self):
        store, path = _tmp_watchlist_store()
        before = path.read_text(encoding="utf-8")
        _post_watchlist("", store)
        after = path.read_text(encoding="utf-8")
        assert before == after

    def test_file_unchanged_after_invalid_format_rejection(self):
        store, path = _tmp_watchlist_store()
        before = path.read_text(encoding="utf-8")
        _post_watchlist("BTC/USDT", store)
        after = path.read_text(encoding="utf-8")
        assert before == after

    def test_file_unchanged_after_oversized_rejection(self):
        store, path = _tmp_watchlist_store()
        before = path.read_text(encoding="utf-8")
        _post_watchlist("A" * 50, store)
        after = path.read_text(encoding="utf-8")
        assert before == after

    def test_watchlist_coins_unchanged_after_rejection(self):
        store, _ = _tmp_watchlist_store()
        before_coins = list(store.all())
        _post_watchlist("BTC;", store)
        after_coins = store.all()
        assert before_coins == after_coins

    def test_file_changes_after_valid_add(self):
        """Sanity: valid adds DO change the file (contrast with rejections)."""
        store, path = _tmp_watchlist_store()
        before = path.read_text(encoding="utf-8")
        _post_watchlist("btc", store)
        after = path.read_text(encoding="utf-8")
        assert before != after


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
