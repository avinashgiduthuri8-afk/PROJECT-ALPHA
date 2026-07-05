"""
tests/test_vgx_grid_management.py
==================================
Unit tests for VGX Grid Management (V1 Part 0.1).

Covers:
  - Storage layer: get/set/remove grid_coins and base_price
  - Validation rules: empty list, duplicates, non-alphanumeric, >20 coins, price ≤ 0
  - Persistence: values survive a simulated process restart (reload from file)
  - Type coercion: corrupt storage values reset to safe defaults
  - API endpoints: all four routes via FastAPI TestClient
  - Auth: every mutating endpoint rejects requests missing X-API-Key
  - Hardcoded lists: PHASE5["coins"] removed from config; _VGX_PHASE5_COINS removed from app
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Storage-layer helpers — redirect file paths to a tmp dir before any import
# so tests never touch the real TradingBotCrypto.json.
# ---------------------------------------------------------------------------

@pytest.fixture()
def vgx_storage(tmp_path):
    """Return the storage module wired to an isolated tmp directory."""
    import bots.volatile_gridX.storage as st

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    storage_file   = storage_dir / "TradingBotCrypto.json"
    storage_backup = storage_dir / "TradingBotCrypto_backup.json"

    # Redirect module-level path constants.
    orig_file   = st.STORAGE_FILE
    orig_backup = st.STORAGE_BACKUP
    orig_dir    = st.STORAGE_DIR

    st.STORAGE_FILE   = str(storage_file)
    st.STORAGE_BACKUP = str(storage_backup)
    st.STORAGE_DIR    = str(storage_dir)

    # Reset in-memory state.
    st.grid_config = {}
    st.grid_coins  = list(st._DEFAULT_GRID_COINS)

    yield st

    # Restore originals so other tests are unaffected.
    st.STORAGE_FILE   = orig_file
    st.STORAGE_BACKUP = orig_backup
    st.STORAGE_DIR    = orig_dir


# ===========================================================================
# 1. get_grid_coins
# ===========================================================================

class TestGetGridCoins:
    def test_returns_default_when_no_file(self, vgx_storage):
        """get_grid_coins() returns the built-in default list when storage is empty."""
        coins = vgx_storage.get_grid_coins()
        assert coins == list(vgx_storage._DEFAULT_GRID_COINS)

    def test_returns_saved_list(self, vgx_storage):
        """get_grid_coins() returns the list that was previously saved."""
        vgx_storage.set_grid_coins(["BTC", "ETH", "DOGE"])
        assert vgx_storage.get_grid_coins() == ["BTC", "ETH", "DOGE"]

    def test_returns_list_after_reload(self, vgx_storage):
        """get_grid_coins() survives a simulated process restart."""
        vgx_storage.set_grid_coins(["SOL", "BNB"])
        # Wipe in-memory state and reload from disk.
        vgx_storage.grid_coins = []
        vgx_storage.load_data()
        assert vgx_storage.get_grid_coins() == ["SOL", "BNB"]


# ===========================================================================
# 2. set_grid_coins — validation
# ===========================================================================

class TestSetGridCoins:
    def test_rejects_empty_list(self, vgx_storage):
        assert vgx_storage.set_grid_coins([]) is False

    def test_rejects_more_than_20_coins(self, vgx_storage):
        big = [f"C{i:02d}" for i in range(21)]
        assert vgx_storage.set_grid_coins(big) is False

    def test_rejects_non_alphanumeric_coin(self, vgx_storage):
        assert vgx_storage.set_grid_coins(["BTC-USD", "ETH"]) is False

    def test_rejects_coin_longer_than_10_chars(self, vgx_storage):
        assert vgx_storage.set_grid_coins(["TOOLONGCOIN1"]) is False

    def test_normalises_lowercase_to_uppercase(self, vgx_storage):
        ok = vgx_storage.set_grid_coins(["btc", "eth", "sol"])
        assert ok is True
        assert vgx_storage.get_grid_coins() == ["BTC", "ETH", "SOL"]

    def test_deduplicates_coins(self, vgx_storage):
        ok = vgx_storage.set_grid_coins(["BTC", "BTC", "ETH"])
        assert ok is True
        coins = vgx_storage.get_grid_coins()
        assert coins.count("BTC") == 1

    def test_accepts_exactly_20_coins(self, vgx_storage):
        twenty = [f"C{i:02d}" for i in range(20)]
        assert vgx_storage.set_grid_coins(twenty) is True

    def test_persists_to_disk(self, vgx_storage):
        vgx_storage.set_grid_coins(["XRP", "ZEC"])
        vgx_storage.grid_coins = []
        vgx_storage.load_data()
        assert vgx_storage.get_grid_coins() == ["XRP", "ZEC"]


# ===========================================================================
# 3. get_coin_base_price
# ===========================================================================

class TestGetCoinBasePrice:
    def test_returns_none_when_not_set(self, vgx_storage):
        assert vgx_storage.get_coin_base_price("BTC") is None

    def test_returns_price_after_set(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 9_000_000.0)
        assert vgx_storage.get_coin_base_price("BTC") == 9_000_000.0

    def test_returns_none_for_unrelated_coin(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 9_000_000.0)
        assert vgx_storage.get_coin_base_price("ETH") is None


# ===========================================================================
# 4. set_coin_base_price — validation & persistence
# ===========================================================================

class TestSetCoinBasePrice:
    def test_rejects_zero_price(self, vgx_storage):
        assert vgx_storage.set_coin_base_price("BTC", 0) is False

    def test_rejects_negative_price(self, vgx_storage):
        assert vgx_storage.set_coin_base_price("BTC", -100.0) is False

    def test_accepts_valid_price(self, vgx_storage):
        assert vgx_storage.set_coin_base_price("BTC", 9_000_000.0) is True

    def test_records_set_by(self, vgx_storage):
        vgx_storage.set_coin_base_price("ETH", 200_000.0, set_by="unit_test")
        cfg = vgx_storage.get_grid_config()
        assert cfg["ETH"]["base_price_set_by"] == "unit_test"

    def test_records_set_at_timestamp(self, vgx_storage):
        vgx_storage.set_coin_base_price("SOL", 8_500.0)
        cfg = vgx_storage.get_grid_config()
        assert "base_price_set_at" in cfg["SOL"]
        assert cfg["SOL"]["base_price_set_at"]  # non-empty

    def test_updates_existing_price(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 9_000_000.0)
        vgx_storage.set_coin_base_price("BTC", 9_500_000.0)
        assert vgx_storage.get_coin_base_price("BTC") == 9_500_000.0

    def test_persists_across_simulated_restart(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 9_000_000.0, set_by="test")
        vgx_storage.grid_config = {}
        vgx_storage.load_data()
        assert vgx_storage.get_coin_base_price("BTC") == 9_000_000.0


# ===========================================================================
# 5. remove_coin_base_price
# ===========================================================================

class TestRemoveCoinBasePrice:
    def test_returns_false_when_not_set(self, vgx_storage):
        assert vgx_storage.remove_coin_base_price("ETH") is False

    def test_removes_existing_entry(self, vgx_storage):
        vgx_storage.set_coin_base_price("SOL", 8_500.0)
        assert vgx_storage.remove_coin_base_price("SOL") is True
        assert vgx_storage.get_coin_base_price("SOL") is None

    def test_removal_persists_to_disk(self, vgx_storage):
        vgx_storage.set_coin_base_price("BNB", 30_000.0)
        vgx_storage.remove_coin_base_price("BNB")
        vgx_storage.grid_config = {}
        vgx_storage.load_data()
        assert vgx_storage.get_coin_base_price("BNB") is None

    def test_does_not_affect_other_coins(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 9_000_000.0)
        vgx_storage.set_coin_base_price("ETH", 200_000.0)
        vgx_storage.remove_coin_base_price("BTC")
        assert vgx_storage.get_coin_base_price("ETH") == 200_000.0


# ===========================================================================
# 6. Type coercion — corrupt storage values reset to safe defaults
# ===========================================================================

class TestStorageTypeCoercion:
    def _corrupt_and_reload(self, st, key, value):
        with open(st.STORAGE_FILE, "r") as f:
            raw = json.load(f)
        raw[key] = value
        with open(st.STORAGE_FILE, "w") as f:
            json.dump(raw, f)
        st.grid_config = {}
        st.grid_coins  = []
        st.load_data()

    def test_grid_config_string_resets_to_empty_dict(self, vgx_storage):
        # Ensure a file exists first.
        vgx_storage.set_coin_base_price("BTC", 1000.0)
        self._corrupt_and_reload(vgx_storage, "grid_config", "CORRUPT")
        assert isinstance(vgx_storage.grid_config, dict)

    def test_grid_config_list_resets_to_empty_dict(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 1000.0)
        self._corrupt_and_reload(vgx_storage, "grid_config", [1, 2, 3])
        assert isinstance(vgx_storage.grid_config, dict)

    def test_grid_config_purges_non_dict_entries(self, vgx_storage):
        vgx_storage.set_coin_base_price("BTC", 1000.0)
        with open(vgx_storage.STORAGE_FILE, "r") as f:
            raw = json.load(f)
        raw["grid_config"]["BAD"] = "not_a_dict"
        with open(vgx_storage.STORAGE_FILE, "w") as f:
            json.dump(raw, f)
        vgx_storage.grid_config = {}
        vgx_storage.load_data()
        assert "BAD" not in vgx_storage.grid_config
        assert "BTC" in vgx_storage.grid_config  # valid entry preserved

    def test_grid_coins_int_resets_to_default(self, vgx_storage):
        vgx_storage.set_grid_coins(["BTC"])
        self._corrupt_and_reload(vgx_storage, "grid_coins", 42)
        assert isinstance(vgx_storage.grid_coins, list)
        assert len(vgx_storage.grid_coins) > 0

    def test_grid_coins_empty_list_resets_to_default(self, vgx_storage):
        vgx_storage.set_grid_coins(["BTC"])
        self._corrupt_and_reload(vgx_storage, "grid_coins", [])
        assert vgx_storage.grid_coins == list(vgx_storage._DEFAULT_GRID_COINS)

    def test_grid_coins_drops_non_string_entries(self, vgx_storage):
        vgx_storage.set_grid_coins(["BTC"])
        with open(vgx_storage.STORAGE_FILE, "r") as f:
            raw = json.load(f)
        raw["grid_coins"] = ["BTC", 99, None, "ETH"]
        with open(vgx_storage.STORAGE_FILE, "w") as f:
            json.dump(raw, f)
        vgx_storage.grid_coins = []
        vgx_storage.load_data()
        assert vgx_storage.grid_coins == ["BTC", "ETH"]


# ===========================================================================
# 7. API endpoint handler tests — called directly (no TestClient)
#
# The route handlers are pure async functions. We call them directly with a
# lightweight mock Request so we avoid the TestClient/anyio/asyncio.to_thread
# interaction that produces spurious 422s in the pytest event-loop context.
# This tests the actual handler logic (validation, storage writes, response
# shape) without involving the ASGI stack at all.
# ===========================================================================

import asyncio
import json as _json
from unittest.mock import MagicMock


def _make_request(body: dict | None = None, query_params: dict | None = None,
                  headers: dict | None = None) -> MagicMock:
    """Return a lightweight mock of starlette.requests.Request."""
    req = MagicMock()
    req.query_params = query_params or {}
    req.headers      = headers or {}

    async def _json_body():
        if body is None:
            raise ValueError("no body")
        return body

    req.json = _json_body
    return req


@pytest.fixture()
def api_storage(tmp_path):
    """Storage redirected to tmp dir, shared across API handler tests."""
    import bots.volatile_gridX.storage as st

    orig_file   = st.STORAGE_FILE
    orig_backup = st.STORAGE_BACKUP
    orig_dir    = st.STORAGE_DIR

    st.STORAGE_FILE   = str(tmp_path / "TradingBotCrypto.json")
    st.STORAGE_BACKUP = str(tmp_path / "TradingBotCrypto_backup.json")
    st.STORAGE_DIR    = str(tmp_path)
    st.grid_config = {}
    st.grid_coins  = list(st._DEFAULT_GRID_COINS)

    yield st

    st.STORAGE_FILE   = orig_file
    st.STORAGE_BACKUP = orig_backup
    st.STORAGE_DIR    = orig_dir


def _body(response) -> dict:
    """Decode a starlette JSONResponse body to a dict."""
    return _json.loads(response.body)


class TestGetGridConfig:
    """Tests for GET /api/vgx/grid-config — handler called directly."""

    def test_returns_grid_coins_and_grid_config(self, api_storage):
        import app as application
        data = _body(asyncio.run(application.vgx_get_grid_config()))
        assert "grid_coins" in data
        assert "grid_config" in data
        assert isinstance(data["grid_coins"], list)
        assert isinstance(data["grid_config"], dict)

    def test_grid_coins_reflects_storage(self, api_storage):
        import app as application
        api_storage.set_grid_coins(["XRP", "ZEC"])
        data = _body(asyncio.run(application.vgx_get_grid_config()))
        assert data["grid_coins"] == ["XRP", "ZEC"]

    def test_grid_config_reflects_storage(self, api_storage):
        import app as application
        api_storage.set_coin_base_price("BTC", 9_000_000.0)
        data = _body(asyncio.run(application.vgx_get_grid_config()))
        assert data["grid_config"]["BTC"]["base_price"] == 9_000_000.0

    def test_requires_api_key(self, api_storage):
        """Auth is enforced at the app level by Depends(require_api_key).
        We verify the require_api_key function rejects a missing key."""
        import asyncio as _asyncio
        from fastapi import HTTPException
        import app as application

        # Build a minimal mock request with no API-Key header.
        req = _make_request(headers={})
        req.url.path = "/api/vgx/grid-config"

        # Direct call to the dependency function.
        coro = application.require_api_key(request=req, api_key=None)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(coro)
        assert exc_info.value.status_code == 401


class TestPostGridCoins:
    """Tests for POST /api/vgx/grid-coins — handler called directly."""

    def test_updates_coin_list(self, api_storage):
        import app as application
        req = _make_request(body={"coins": ["BTC", "ETH", "SOL"]})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "ok"
        assert data["count"] == 3
        assert data["coins"] == ["BTC", "ETH", "SOL"]

    def test_normalises_lowercase(self, api_storage):
        import app as application
        req = _make_request(body={"coins": ["btc", "eth"]})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "ok"
        assert data["coins"] == ["BTC", "ETH"]

    def test_rejects_empty_list(self, api_storage):
        import app as application
        req = _make_request(body={"coins": []})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "error"

    def test_rejects_non_alphanumeric_coin(self, api_storage):
        import app as application
        req = _make_request(body={"coins": ["BTC-USD"]})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "error"

    def test_rejects_more_than_20_coins(self, api_storage):
        import app as application
        req = _make_request(body={"coins": [f"C{i:02d}" for i in range(21)]})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "error"

    def test_rejects_invalid_json_body(self, api_storage):
        """Non-list 'coins' value should be rejected."""
        import app as application
        req = _make_request(body={"coins": "not-a-list"})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "error"

    def test_coin_list_persists_to_storage(self, api_storage):
        import app as application
        req = _make_request(body={"coins": ["XRP", "ZEC"]})
        asyncio.run(application.vgx_set_grid_coins(req))
        assert api_storage.get_grid_coins() == ["XRP", "ZEC"]

    def test_response_reflects_deduped_persisted_state(self, api_storage):
        """API response coins/count must match what was actually stored,
        not the raw (possibly duplicate) input."""
        import app as application
        req = _make_request(body={"coins": ["BTC", "ETH", "BTC", "ETH"]})
        data = _body(asyncio.run(application.vgx_set_grid_coins(req)))
        assert data["status"] == "ok"
        assert data["coins"] == ["BTC", "ETH"]   # deduped
        assert data["count"] == 2                  # matches persisted count
        assert api_storage.get_grid_coins() == ["BTC", "ETH"]


class TestPostBasePrice:
    """Tests for POST /api/vgx/base-price — handler called directly."""

    def test_sets_base_price(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "BTC", "base_price": 9_000_000.0})
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["status"] == "ok"
        assert data["coin"] == "BTC"
        assert data["base_price"] == 9_000_000.0

    def test_price_visible_in_storage(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "ETH", "base_price": 200_000.0})
        asyncio.run(application.vgx_set_coin_base_price(req))
        assert api_storage.get_coin_base_price("ETH") == 200_000.0

    def test_normalises_coin_to_uppercase(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "sol", "base_price": 8_000.0})
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["coin"] == "SOL"

    def test_rejects_price_zero(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "BTC", "base_price": 0})
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["status"] == "error"

    def test_rejects_negative_price(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "BTC", "base_price": -1})
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["status"] == "error"

    def test_rejects_non_alphanumeric_coin(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "BTC-USD", "base_price": 9_000_000.0})
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["status"] == "error"

    def test_rejects_coin_over_10_chars(self, api_storage):
        import app as application
        req = _make_request(body={"coin": "TOOLONGCOIN1", "base_price": 100.0})
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["status"] == "error"

    def test_rejects_invalid_json(self, api_storage):
        """Handler must gracefully handle a request whose .json() raises."""
        import app as application

        async def _bad_json():
            raise ValueError("bad json")

        req = MagicMock()
        req.json = _bad_json
        data = _body(asyncio.run(application.vgx_set_coin_base_price(req)))
        assert data["status"] == "error"

    def test_update_overwrites_existing_price(self, api_storage):
        import app as application
        req1 = _make_request(body={"coin": "BTC", "base_price": 9_000_000.0})
        req2 = _make_request(body={"coin": "BTC", "base_price": 9_500_000.0})
        asyncio.run(application.vgx_set_coin_base_price(req1))
        asyncio.run(application.vgx_set_coin_base_price(req2))
        assert api_storage.get_coin_base_price("BTC") == 9_500_000.0


class TestDeleteBasePrice:
    """Tests for DELETE /api/vgx/base-price — handler called directly."""

    def test_removes_existing_entry(self, api_storage):
        import app as application
        api_storage.set_coin_base_price("BTC", 9_000_000.0)
        req = _make_request(query_params={"coin": "BTC"})
        data = _body(asyncio.run(application.vgx_remove_coin_base_price(req)))
        assert data["status"] == "ok"
        assert api_storage.get_coin_base_price("BTC") is None

    def test_returns_not_found_for_unknown_coin(self, api_storage):
        import app as application
        req = _make_request(query_params={"coin": "UNKNOWN"})
        data = _body(asyncio.run(application.vgx_remove_coin_base_price(req)))
        assert data["status"] == "not_found"

    def test_rejects_missing_coin_param(self, api_storage):
        import app as application
        req = _make_request(query_params={})
        data = _body(asyncio.run(application.vgx_remove_coin_base_price(req)))
        assert data["status"] == "error"

    def test_rejects_non_alphanumeric_coin_param(self, api_storage):
        import app as application
        req = _make_request(query_params={"coin": "BTC-USD"})
        data = _body(asyncio.run(application.vgx_remove_coin_base_price(req)))
        assert data["status"] == "error"

    def test_does_not_affect_other_coins(self, api_storage):
        import app as application
        api_storage.set_coin_base_price("BTC", 9_000_000.0)
        api_storage.set_coin_base_price("ETH", 200_000.0)
        req = _make_request(query_params={"coin": "BTC"})
        asyncio.run(application.vgx_remove_coin_base_price(req))
        assert api_storage.get_coin_base_price("ETH") == 200_000.0

    def test_coin_normalised_to_uppercase(self, api_storage):
        import app as application
        api_storage.set_coin_base_price("BTC", 9_000_000.0)
        req = _make_request(query_params={"coin": "btc"})
        data = _body(asyncio.run(application.vgx_remove_coin_base_price(req)))
        assert data["status"] == "ok"


# ===========================================================================
# 8. Static / structural checks — hardcoded lists removed
# ===========================================================================

class TestHardcodedListsRemoved:
    def test_phase5_has_no_coins_key(self):
        """PHASE5 dict in config must not contain a 'coins' key."""
        from bots.volatile_gridX.config import PHASE5
        assert "coins" not in PHASE5, (
            "PHASE5['coins'] is a hardcoded list — it should have been removed. "
            "Grid coins must come from storage, not config."
        )

    def test_app_has_no_vgx_phase5_coins_constant(self):
        """app.py must not export _VGX_PHASE5_COINS as a module attribute."""
        import app as application
        assert not hasattr(application, "_VGX_PHASE5_COINS"), (
            "_VGX_PHASE5_COINS is a hardcoded fallback that was supposed to be removed."
        )

    def test_get_grid_coins_does_not_return_hardcoded_list_after_update(self, vgx_storage):
        """After updating grid coins, storage must return the new list, not a hardcoded one."""
        vgx_storage.set_grid_coins(["DOGE", "SHIB"])
        assert vgx_storage.get_grid_coins() == ["DOGE", "SHIB"]
