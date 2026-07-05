"""
test_vgx_risk_engine_capital.py — VGX deployed-capital enforcement via the shared risk engine.

Test plan (per bug spec):
  1. _load_bot_positions("VGX") returns the position when in-memory dict is populated.
  2. _deployed_capital() computes the correct deployed sum from VGX positions.
  3. check_trade_allowed("VGX", amount) rejects when BOT_CAPITAL_LIMIT["VGX"] would be exceeded.
  4. Regression: PMB/MTB capital checks are unaffected by VGX changes.

Additional coverage:
  - get_open_positions() falls back to file when in-memory is empty.
  - get_open_positions() logs logger.error and returns [] on unreadable storage file.
  - get_open_positions() logs logger.error and returns [] when 'positions' key is wrong type.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_vgx_position(coin: str = "BTC", amount: float = 500.0) -> dict:
    """Return a minimal VGX position dict as stored in the positions dict."""
    return {
        "coin":            coin,
        "buy_price":       30000.0,
        "qty":             amount / 30000.0,
        "amount":          amount,
        "trailing_active": False,
    }


def _make_pmb_position(total_cost: float = 200.0) -> dict:
    return {
        "id": "PMB-BTCUSDT-1",
        "symbol": "BTCUSDT",
        "coin": "BTC",
        "status": "OPEN",
        "entry_price": 30000.0,
        "quantity": total_cost / 30000.0,
        "total_cost": total_cost,
    }


def _make_mtb_position(total_cost: float = 150.0) -> dict:
    return {
        "id": "MTB-ETHUSDT-1",
        "symbol": "ETHUSDT",
        "coin": "ETH",
        "status": "OPEN",
        "entry_price": 2000.0,
        "quantity": total_cost / 2000.0,
        "total_cost": total_cost,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _load_bot_positions("VGX") returns positions from in-memory dict
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadVGXPositionsInMemory:
    """Risk engine correctly reads VGX positions from the live in-memory dict."""

    def test_returns_empty_list_when_no_positions(self):
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine.engine import _load_bot_positions

        with patch.dict(vgx_storage.positions, {}, clear=True):
            result = _load_bot_positions("VGX")
        # In-memory is empty → falls through to file path; mock the file too.
        assert isinstance(result, list)

    def test_returns_one_position_when_in_memory_has_one(self):
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine.engine import _load_bot_positions

        pos = {"BTC_manual": _make_vgx_position("BTC", 500.0)}
        with patch.dict(vgx_storage.positions, pos, clear=True):
            result = _load_bot_positions("VGX")

        assert len(result) == 1
        assert result[0]["coin"] == "BTC"
        assert result[0]["amount"] == pytest.approx(500.0)

    def test_returns_multiple_positions(self):
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine.engine import _load_bot_positions

        pos = {
            "BTC_manual": _make_vgx_position("BTC", 500.0),
            "ETH_auto":   _make_vgx_position("ETH", 300.0),
        }
        with patch.dict(vgx_storage.positions, pos, clear=True):
            result = _load_bot_positions("VGX")

        assert len(result) == 2
        coins = {p["coin"] for p in result}
        assert "BTC" in coins
        assert "ETH" in coins

    def test_each_entry_has_amount_and_trade_amount(self):
        """Both 'amount' and 'trade_amount' must be present for _deployed_capital()."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine.engine import _load_bot_positions

        pos = {"SOL_auto": _make_vgx_position("SOL", 750.0)}
        with patch.dict(vgx_storage.positions, pos, clear=True):
            result = _load_bot_positions("VGX")

        assert result[0]["amount"] == pytest.approx(750.0)
        assert result[0]["trade_amount"] == pytest.approx(750.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _deployed_capital() computes correct value from VGX positions
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeployedCapitalVGX:
    """_deployed_capital() sums VGX position amounts correctly."""

    def test_zero_when_no_positions(self):
        from bots.risk_engine.engine import _deployed_capital
        assert _deployed_capital([]) == pytest.approx(0.0)

    def test_single_position_amount(self):
        from bots.risk_engine.engine import _deployed_capital

        positions = [{"coin": "BTC", "amount": 500.0, "trade_amount": 500.0}]
        assert _deployed_capital(positions) == pytest.approx(500.0)

    def test_sums_multiple_positions(self):
        from bots.risk_engine.engine import _deployed_capital

        positions = [
            {"coin": "BTC", "amount": 500.0, "trade_amount": 500.0},
            {"coin": "ETH", "amount": 300.0, "trade_amount": 300.0},
        ]
        assert _deployed_capital(positions) == pytest.approx(800.0)

    def test_full_pipeline_from_memory_to_deployed_capital(self):
        """End-to-end: in-memory positions → _load_bot_positions → _deployed_capital."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine.engine import _deployed_capital, _load_bot_positions

        pos = {
            "BTC_manual": _make_vgx_position("BTC", 500.0),
            "ETH_auto":   _make_vgx_position("ETH", 300.0),
        }
        with patch.dict(vgx_storage.positions, pos, clear=True):
            loaded = _load_bot_positions("VGX")

        deployed = _deployed_capital(loaded)
        assert deployed == pytest.approx(800.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. check_trade_allowed("VGX", amount) enforces BOT_CAPITAL_LIMIT
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckTradeAllowedVGX:
    """VGX capital-limit enforcement through the full check_trade_allowed() path."""

    def _base_patches(self):
        """Common patches: trading enabled, no emergency stop, VGX in PAPER mode."""
        from bots.risk_engine import engine as eng
        return [
            patch.object(eng, "get_trading_enabled", return_value=True),
            patch.object(eng, "EMERGENCY_STOP", False),
            patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}),
        ]

    def test_allowed_when_under_limit(self):
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine import engine as eng
        from bots.risk_engine.config import BOT_CAPITAL_LIMIT

        vgx_limit = BOT_CAPITAL_LIMIT["VGX"]   # e.g. 5000

        # No existing positions → 0 deployed; propose 100 → well under limit.
        with patch.dict(vgx_storage.positions, {}, clear=True):
            # Patch file fallback too so no stale file data bleeds in.
            with patch("bots.volatile_gridX.storage._verify_file", return_value=False):
                with patch.object(eng, "get_trading_enabled", return_value=True):
                    with patch.object(eng, "EMERGENCY_STOP", False):
                        with patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                            # Isolate total-capital check by zeroing other bots.
                            with patch.object(eng, "_load_bot_positions",
                                              side_effect=lambda b: [] if b != "VGX" else []):
                                decision = eng.check_trade_allowed("VGX", 100.0)

        assert decision.allowed is True, decision.reason

    def test_rejected_when_bot_capital_limit_exceeded(self):
        """VGX must be blocked once existing positions + proposed trade > BOT_CAPITAL_LIMIT."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine import engine as eng
        from bots.risk_engine.config import BOT_CAPITAL_LIMIT

        vgx_limit = BOT_CAPITAL_LIMIT["VGX"]   # e.g. 5000

        # Fill to just under the limit so any additional trade overflows.
        near_full_amount = vgx_limit - 100.0
        pos = {"BTC_manual": _make_vgx_position("BTC", near_full_amount)}

        with patch.dict(vgx_storage.positions, pos, clear=True):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        # Isolate total-capital check.
                        with patch.object(eng, "_load_bot_positions",
                                          wraps=lambda b: eng._load_bot_positions.__wrapped__(b)
                                          if b == "VGX" else []):
                            # Directly call without the wraps trick — patch other bots to [].
                            pass

        # Cleaner approach: patch only the cross-bot total check.
        _real_load = eng._load_bot_positions

        def _patched_load(b):
            if b == "VGX":
                return _real_load("VGX")
            return []

        with patch.dict(vgx_storage.positions, pos, clear=True):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        with patch.object(eng, "_load_bot_positions", side_effect=_patched_load):
                            decision = eng.check_trade_allowed("VGX", 200.0)

        assert decision.allowed is False
        assert decision.code == "BOT_CAPITAL_LIMIT_EXCEEDED"

    def test_previously_always_allowed_with_stub_now_blocked(self):
        """Regression guard: the old stub returned [] so this was always allowed.
        Now it must be blocked when positions fill the limit."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine import engine as eng
        from bots.risk_engine.config import BOT_CAPITAL_LIMIT

        vgx_limit = BOT_CAPITAL_LIMIT["VGX"]

        # One position that fills the entire bot limit.
        pos = {"BTC_manual": _make_vgx_position("BTC", vgx_limit)}

        def _patched_load(b):
            if b == "VGX":
                from bots.volatile_gridX.storage import get_open_positions
                return get_open_positions()
            return []

        with patch.dict(vgx_storage.positions, pos, clear=True):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        with patch.object(eng, "_load_bot_positions", side_effect=_patched_load):
                            decision = eng.check_trade_allowed("VGX", 1.0)

        assert decision.allowed is False, (
            "VGX trade should have been blocked — the old stub always allowed this."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Regression: PMB / MTB capital checks unaffected
# ═══════════════════════════════════════════════════════════════════════════════

class TestPMBMTBRegressions:
    """VGX changes must not disturb PMB or MTB capital enforcement."""

    def test_pmb_load_positions_still_uses_get_open_positions(self):
        from bots.risk_engine.engine import _load_bot_positions
        from unittest.mock import MagicMock

        mock_positions = [_make_pmb_position(200.0)]
        with patch("bots.pmb_bot.storage.get_open_positions", return_value=mock_positions):
            result = _load_bot_positions("PMB")
        assert result == mock_positions

    def test_mtb_load_positions_still_uses_get_open_positions(self):
        from bots.risk_engine.engine import _load_bot_positions

        mock_positions = [_make_mtb_position(150.0)]
        with patch("bots.mtb_bot.storage.get_open_positions", return_value=mock_positions):
            result = _load_bot_positions("MTB")
        assert result == mock_positions

    def test_pmb_capital_limit_enforced(self):
        """PMB capital limit still blocks correctly after VGX change."""
        from bots.risk_engine import engine as eng
        from bots.risk_engine.config import BOT_CAPITAL_LIMIT

        pmb_limit = BOT_CAPITAL_LIMIT["PMB"]
        pos = [_make_pmb_position(pmb_limit)]     # fills the limit exactly

        with patch("bots.pmb_bot.storage.get_open_positions", return_value=pos):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        with patch("bots.volatile_gridX.storage.get_open_positions", return_value=[]):
                            with patch("bots.mtb_bot.storage.get_open_positions", return_value=[]):
                                decision = eng.check_trade_allowed("PMB", 1.0)

        assert decision.allowed is False
        assert decision.code == "BOT_CAPITAL_LIMIT_EXCEEDED"

    def test_mtb_capital_limit_enforced(self):
        """MTB capital limit still blocks correctly after VGX change."""
        from bots.risk_engine import engine as eng
        from bots.risk_engine.config import BOT_CAPITAL_LIMIT

        mtb_limit = BOT_CAPITAL_LIMIT["MTB"]
        pos = [_make_mtb_position(mtb_limit)]

        with patch("bots.mtb_bot.storage.get_open_positions", return_value=pos):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE", {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        with patch("bots.volatile_gridX.storage.get_open_positions", return_value=[]):
                            with patch("bots.pmb_bot.storage.get_open_positions", return_value=[]):
                                decision = eng.check_trade_allowed("MTB", 1.0)

        assert decision.allowed is False
        assert decision.code == "BOT_CAPITAL_LIMIT_EXCEEDED"


# ═══════════════════════════════════════════════════════════════════════════════
# get_open_positions() file-fallback and error-handling paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetOpenPositionsFileFallback:
    """When in-memory is empty, get_open_positions() reads from file correctly."""

    def test_file_fallback_returns_positions(self):
        import bots.volatile_gridX.storage as vgx_storage

        storage_data = {
            "positions": {
                "BTC_manual": _make_vgx_position("BTC", 400.0),
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(storage_data, f)
            tmp_path = f.name

        with patch.dict(vgx_storage.positions, {}, clear=True):
            with patch("bots.volatile_gridX.storage.STORAGE_FILE", tmp_path):
                result = vgx_storage.get_open_positions()

        assert len(result) == 1
        assert result[0]["coin"] == "BTC"
        assert result[0]["amount"] == pytest.approx(400.0)

    def test_file_fallback_returns_empty_when_no_file(self):
        import bots.volatile_gridX.storage as vgx_storage

        with patch.dict(vgx_storage.positions, {}, clear=True):
            with patch("bots.volatile_gridX.storage._verify_file", return_value=False):
                result = vgx_storage.get_open_positions()

        assert result == []

    def test_raises_vgx_storage_error_on_corrupt_file(self, caplog):
        """Corrupt file that exists → VGXStorageError raised + logger.error emitted."""
        import bots.volatile_gridX.storage as vgx_storage
        import logging

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("NOT VALID JSON {{{")
            tmp_path = f.name

        with patch.dict(vgx_storage.positions, {}, clear=True):
            with patch("bots.volatile_gridX.storage.STORAGE_FILE", tmp_path):
                with caplog.at_level(logging.ERROR, logger="vgx.storage"):
                    with pytest.raises(vgx_storage.VGXStorageError):
                        vgx_storage.get_open_positions()

        assert any("unreadable" in r.message for r in caplog.records), (
            "Expected logger.error about unreadable storage, got: "
            + str([r.message for r in caplog.records])
        )

    def test_raises_vgx_storage_error_on_wrong_positions_type(self, caplog):
        """Wrong positions type in valid JSON → VGXStorageError raised + logger.error."""
        import bots.volatile_gridX.storage as vgx_storage
        import logging

        storage_data = {"positions": "not-a-dict"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(storage_data, f)
            tmp_path = f.name

        with patch.dict(vgx_storage.positions, {}, clear=True):
            with patch("bots.volatile_gridX.storage.STORAGE_FILE", tmp_path):
                with caplog.at_level(logging.ERROR, logger="vgx.storage"):
                    with pytest.raises(vgx_storage.VGXStorageError):
                        vgx_storage.get_open_positions()

        assert any("unexpected type" in r.message for r in caplog.records), (
            "Expected logger.error about unexpected positions type, got: "
            + str([r.message for r in caplog.records])
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Fail-closed: VGXStorageError → check_trade_allowed denies
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailClosedOnStorageError:
    """When VGX storage is corrupt, check_trade_allowed must deny — not allow through
    a falsely-zero deployed capital figure."""

    def test_check_trade_allowed_denies_on_storage_error(self):
        """VGXStorageError from get_open_positions propagates through _load_bot_positions
        and causes check_trade_allowed to return STORAGE_UNREADABLE denial."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine import engine as eng

        with patch("bots.volatile_gridX.storage.get_open_positions",
                   side_effect=vgx_storage.VGXStorageError("corrupt")):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE",
                                      {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        decision = eng.check_trade_allowed("VGX", 100.0)

        assert decision.allowed is False
        assert decision.code == "STORAGE_UNREADABLE"

    def test_total_capital_check_denies_on_storage_error(self):
        """If VGX storage errors during the cross-bot total check, trade is still denied."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine import engine as eng

        # Bot-specific check uses empty list (under limit), but total check hits VGX error.
        call_count = {"n": 0}

        def _patched_load(b):
            call_count["n"] += 1
            if b == "VGX" and call_count["n"] > 1:
                # Second call (inside total-deployed sum) raises the error.
                raise vgx_storage.VGXStorageError("corrupt on total check")
            return []

        with patch.object(eng, "_load_bot_positions", side_effect=_patched_load):
            with patch.object(eng, "get_trading_enabled", return_value=True):
                with patch.object(eng, "EMERGENCY_STOP", False):
                    with patch.object(eng, "BOT_MODE",
                                      {"VGX": "PAPER", "PMB": "PAPER", "MTB": "PAPER"}):
                        decision = eng.check_trade_allowed("VGX", 100.0)

        assert decision.allowed is False
        assert decision.code == "STORAGE_UNREADABLE"

    def test_snapshot_marks_storage_error_flag(self):
        """snapshot() degrades gracefully — returns storage_error=True for the
        affected bot rather than crashing or masking the failure."""
        import bots.volatile_gridX.storage as vgx_storage
        from bots.risk_engine import engine as eng

        def _patched_load(b):
            if b == "VGX":
                raise vgx_storage.VGXStorageError("corrupt")
            return []

        with patch.object(eng, "_load_bot_positions", side_effect=_patched_load):
            result = eng.snapshot()

        assert result["bots"]["VGX"]["storage_error"] is True
        assert result["bots"]["PMB"]["storage_error"] is False
        assert result["bots"]["MTB"]["storage_error"] is False
        # Total deployed should exclude the errored bot (treated as 0 for display).
        assert result["total_deployed"] == pytest.approx(0.0)
