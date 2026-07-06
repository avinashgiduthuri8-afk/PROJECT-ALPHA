"""
tests/test_vgx_storage_corruption_recovery.py
==============================================
C-1 fix verification: VGX storage corruption recovery (deny-by-default).

Scenarios:
  1. Valid primary file         → loads normally, status SYNCED
  2. Corrupt primary, valid bak → recovers from bak, status RECOVERED_FROM_BACKUP
  3. Corrupt primary, corrupt bak → raises VGXStorageError, neither file touched
  4. Corrupt primary, missing bak → raises VGXStorageError, primary not overwritten
  5. Missing primary file       → fresh start, defaults persisted, status SYNCED
  6. Empty primary file         → treated as fresh start (same as missing)
  7. Restart after save_data    → state survives round-trip
  8. Corrupt file not overwritten → primary file bytes unchanged after VGXStorageError
  9. recovery_from_backup flag  → storage_state["recovered_from_backup"] set correctly
 10. get_open_positions on corrupt file → still raises VGXStorageError (unchanged)
"""
from __future__ import annotations

import json
import os

import pytest

import bots.volatile_gridX.storage as st


# ---------------------------------------------------------------------------
# Fixture: redirect VGX storage to an isolated tmp directory
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path):
    """Wire all storage paths to tmp_path and reset module globals before each test."""
    storage_dir  = tmp_path / "storage"
    storage_dir.mkdir()
    storage_file   = storage_dir / "TradingBotCrypto.json"
    storage_backup = storage_dir / "TradingBotCrypto_backup.json"

    orig_file   = st.STORAGE_FILE
    orig_backup = st.STORAGE_BACKUP
    orig_dir    = st.STORAGE_DIR

    st.STORAGE_FILE   = str(storage_file)
    st.STORAGE_BACKUP = str(storage_backup)
    st.STORAGE_DIR    = str(storage_dir)

    # Reset module globals to clean defaults before every test.
    st.virtual_balance   = 1_000_000
    st.positions         = {}
    st.trade_log         = []
    st.price_history     = {}
    st.market_cache      = {}
    st.portfolio_history = []
    st.trade_history     = []
    st.error_logs        = []
    st.metrics_summary   = {}
    st.grid_config       = {}
    st.grid_coins        = list(st._DEFAULT_GRID_COINS)
    st.storage_state["status"]                = "INITIALIZED"
    st.storage_state["last_sync"]             = 0
    st.storage_state["sync_count"]            = 0
    st.storage_state["backup_status"]         = "NONE"
    st.storage_state["recovered_from_backup"] = False

    yield storage_file, storage_backup, storage_dir

    # Restore real paths.
    st.STORAGE_FILE   = orig_file
    st.STORAGE_BACKUP = orig_backup
    st.STORAGE_DIR    = orig_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_payload(**overrides) -> dict:
    base = {
        "virtual_balance":  500_000,
        "positions":        {"BTC_SCANNER": {"coin": "BTC", "amount": 5000}},
        "trade_log":        [{"id": 1, "coin": "BTC"}],
        "price_history":    {},
        "market_cache":     {},
        "portfolio_history": [],
        "trade_history":    [{"coin": "BTC", "pnl": 100}],
        "error_logs":       [],
        "metrics_summary":  {"win_rate": 60},
        "grid_config":      {"BTC": {"base_price": 45.0}},
        "grid_coins":       ["BTC", "ETH"],
    }
    base.update(overrides)
    return base


def _write_json(path, data):
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_corrupt(path):
    with open(str(path), "w", encoding="utf-8") as f:
        f.write("{this is not valid json !!!}")


# ---------------------------------------------------------------------------
# Scenario 1: Valid primary file loads normally
# ---------------------------------------------------------------------------

class TestValidFilePath:

    def test_loads_data_from_valid_primary(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        payload = _valid_payload()
        _write_json(storage_file, payload)

        st.load_data()

        assert st.virtual_balance == 500_000
        assert "BTC_SCANNER" in st.positions
        assert len(st.trade_log) == 1
        assert st.grid_coins == ["BTC", "ETH"]

    def test_status_is_synced_after_valid_load(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_json(storage_file, _valid_payload())

        st.load_data()

        assert st.storage_state["status"] == "SYNCED"
        assert st.storage_state["recovered_from_backup"] is False

    def test_grid_config_loaded_correctly(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        payload = _valid_payload(grid_config={"ETH": {"base_price": 2000.0}})
        _write_json(storage_file, payload)

        st.load_data()

        assert st.grid_config == {"ETH": {"base_price": 2000.0}}


# ---------------------------------------------------------------------------
# Scenario 2: Corrupt primary, valid backup → recover from backup
# ---------------------------------------------------------------------------

class TestCorruptPrimaryValidBackup:

    def test_recovers_positions_from_backup(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        _write_json(storage_backup, _valid_payload())

        st.load_data()

        assert st.virtual_balance == 500_000
        assert "BTC_SCANNER" in st.positions

    def test_status_is_recovered_from_backup(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        _write_json(storage_backup, _valid_payload())

        st.load_data()

        assert st.storage_state["status"] == "RECOVERED_FROM_BACKUP"
        assert st.storage_state["backup_status"] == "RESTORED"
        assert st.storage_state["recovered_from_backup"] is True

    def test_corrupt_primary_not_overwritten_on_recovery(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        corrupt_bytes = b"{this is not valid json !!!}"
        with open(str(storage_file), "wb") as f:
            f.write(corrupt_bytes)
        _write_json(storage_backup, _valid_payload())

        st.load_data()

        # Primary file must still contain the original corrupt bytes — not overwritten.
        with open(str(storage_file), "rb") as f:
            after_bytes = f.read()
        assert after_bytes == corrupt_bytes

    def test_trade_history_restored_from_backup(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        payload = _valid_payload(trade_history=[{"coin": "ETH", "pnl": 250}])
        _write_json(storage_backup, payload)

        st.load_data()

        assert st.trade_history == [{"coin": "ETH", "pnl": 250}]

    def test_grid_config_restored_from_backup(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        payload = _valid_payload(grid_config={"SOL": {"base_price": 150.0}})
        _write_json(storage_backup, payload)

        st.load_data()

        assert st.grid_config == {"SOL": {"base_price": 150.0}}


# ---------------------------------------------------------------------------
# Scenario 3: Corrupt primary, corrupt backup → VGXStorageError
# ---------------------------------------------------------------------------

class TestCorruptPrimaryCorruptBackup:

    def test_raises_vgx_storage_error(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        _write_corrupt(storage_backup)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

    def test_status_is_corrupt_unrecoverable(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        _write_corrupt(storage_backup)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

        assert st.storage_state["status"] == "CORRUPT_UNRECOVERABLE"
        assert st.storage_state["backup_status"] == "FAILED"

    def test_primary_not_overwritten_when_both_corrupt(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        corrupt_bytes = b"{primary corrupt content}"
        with open(str(storage_file), "wb") as f:
            f.write(corrupt_bytes)
        _write_corrupt(storage_backup)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

        with open(str(storage_file), "rb") as f:
            assert f.read() == corrupt_bytes

    def test_backup_not_overwritten_when_both_corrupt(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        bak_bytes = b"{backup corrupt content}"
        with open(str(storage_backup), "wb") as f:
            f.write(bak_bytes)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

        with open(str(storage_backup), "rb") as f:
            assert f.read() == bak_bytes

    def test_error_message_mentions_corrupt(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        _write_corrupt(storage_backup)

        with pytest.raises(st.VGXStorageError, match="corrupt"):
            st.load_data()


# ---------------------------------------------------------------------------
# Scenario 4: Corrupt primary, missing backup → VGXStorageError
# ---------------------------------------------------------------------------

class TestCorruptPrimaryMissingBackup:

    def test_raises_vgx_storage_error(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        # storage_backup deliberately not created

        with pytest.raises(st.VGXStorageError):
            st.load_data()

    def test_primary_not_overwritten(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        corrupt_bytes = b"{no backup scenario}"
        with open(str(storage_file), "wb") as f:
            f.write(corrupt_bytes)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

        with open(str(storage_file), "rb") as f:
            assert f.read() == corrupt_bytes

    def test_status_is_corrupt_unrecoverable(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_corrupt(storage_file)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

        assert st.storage_state["status"] == "CORRUPT_UNRECOVERABLE"

    def test_error_message_mentions_no_backup(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_corrupt(storage_file)

        with pytest.raises(st.VGXStorageError, match="no backup"):
            st.load_data()


# ---------------------------------------------------------------------------
# Scenario 5 & 6: Missing / empty primary → fresh start
# ---------------------------------------------------------------------------

class TestFreshStart:

    def test_missing_primary_initialises_defaults(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        assert not storage_file.exists()

        st.load_data()

        assert st.virtual_balance == 1_000_000
        assert st.positions == {}
        assert st.grid_coins == list(st._DEFAULT_GRID_COINS)

    def test_missing_primary_creates_storage_file(self, isolated_storage):
        storage_file, _, _ = isolated_storage

        st.load_data()

        assert storage_file.exists()
        with open(str(storage_file)) as f:
            data = json.load(f)
        assert data["virtual_balance"] == 1_000_000

    def test_empty_primary_treated_as_fresh_start(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        storage_file.write_bytes(b"")  # zero-byte file

        st.load_data()

        # Should not raise; should initialise with defaults.
        assert st.virtual_balance == 1_000_000
        assert st.positions == {}

    def test_recovered_from_backup_is_false_on_fresh_start(self, isolated_storage):
        st.load_data()

        assert st.storage_state["recovered_from_backup"] is False


# ---------------------------------------------------------------------------
# Scenario 7: Restart persistence — state survives round-trip
# ---------------------------------------------------------------------------

class TestRestartPersistence:

    def test_positions_survive_save_and_reload(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        # Simulate a running bot that has open positions
        st.virtual_balance = 750_000
        st.positions = {"ETH_SCANNER": {"coin": "ETH", "amount": 3000}}
        st.trade_history = [{"coin": "ETH", "pnl": 50}]
        st.grid_coins = ["ETH", "SOL"]

        st.save_data()

        # Reset globals to confirm they come back from disk
        st.virtual_balance = 0
        st.positions = {}
        st.trade_history = []
        st.grid_coins = []

        st.load_data()

        assert st.virtual_balance == 750_000
        assert "ETH_SCANNER" in st.positions
        assert st.trade_history == [{"coin": "ETH", "pnl": 50}]
        assert st.grid_coins == ["ETH", "SOL"]

    def test_grid_config_survives_restart(self, isolated_storage):
        st.grid_config = {"BTC": {"base_price": 90_000.0,
                                   "base_price_set_at": "2026-01-01T00:00:00+00:00",
                                   "base_price_set_by": "dashboard"}}
        st.save_data()

        st.grid_config = {}
        st.load_data()

        assert "BTC" in st.grid_config
        assert st.grid_config["BTC"]["base_price"] == 90_000.0

    def test_save_data_creates_backup_of_previous_file(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        # First save creates the primary file
        st.save_data()
        assert storage_file.exists()

        # Second save should copy primary → backup before overwriting
        st.virtual_balance = 200_000
        st.save_data()

        assert storage_backup.exists()
        with open(str(storage_backup)) as f:
            bak_data = json.load(f)
        # Backup holds the state from the first save (balance=1_000_000 default)
        assert bak_data["virtual_balance"] == 1_000_000


# ---------------------------------------------------------------------------
# Scenario 8: get_open_positions on corrupt file still raises VGXStorageError
# ---------------------------------------------------------------------------

class TestGetOpenPositionsCorrupt:

    def test_raises_on_corrupt_file_with_empty_memory(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_corrupt(storage_file)

        # In-memory positions is empty → falls back to file read
        st.positions = {}

        with pytest.raises(st.VGXStorageError):
            st.get_open_positions()

    def test_returns_memory_positions_when_available(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_corrupt(storage_file)

        # In-memory positions are authoritative even if file is corrupt
        st.positions = {"BTC_SCANNER": {"coin": "BTC", "amount": 5000}}

        result = st.get_open_positions()

        assert len(result) == 1
        assert result[0]["coin"] == "BTC"


# ---------------------------------------------------------------------------
# Scenario 9: recovered_from_backup flag accuracy
# ---------------------------------------------------------------------------

class TestRecoveredFromBackupFlag:

    def test_flag_true_only_on_backup_recovery(self, isolated_storage):
        storage_file, storage_backup, _ = isolated_storage
        _write_corrupt(storage_file)
        _write_json(storage_backup, _valid_payload())

        st.load_data()

        assert st.storage_state["recovered_from_backup"] is True

    def test_flag_false_on_normal_load(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_json(storage_file, _valid_payload())

        st.load_data()

        assert st.storage_state["recovered_from_backup"] is False

    def test_flag_false_on_fresh_start(self, isolated_storage):
        st.load_data()

        assert st.storage_state["recovered_from_backup"] is False

    def test_flag_false_after_error(self, isolated_storage):
        storage_file, _, _ = isolated_storage
        _write_corrupt(storage_file)

        with pytest.raises(st.VGXStorageError):
            st.load_data()

        assert st.storage_state["recovered_from_backup"] is False


# ---------------------------------------------------------------------------
# Scenario 10: State-transition sequences — stale storage_state must be reset
# ---------------------------------------------------------------------------

class TestStateTransitionSequences:
    """Verify storage_state fields are fully normalised on each load_data() call,
    regardless of what the previous call left behind."""

    def test_valid_load_after_backup_recovery_resets_backup_status(
        self, isolated_storage
    ):
        """RECOVERED_FROM_BACKUP → valid load: backup_status must reset to NONE."""
        storage_file, storage_backup, _ = isolated_storage

        # First load: corrupt primary, valid backup → RECOVERED_FROM_BACKUP
        _write_corrupt(storage_file)
        _write_json(storage_backup, _valid_payload())
        st.load_data()
        assert st.storage_state["status"] == "RECOVERED_FROM_BACKUP"

        # Operator fixes primary file; second load should fully reset state
        _write_json(storage_file, _valid_payload(virtual_balance=800_000))
        st.load_data()

        assert st.storage_state["status"] == "SYNCED"
        assert st.storage_state["backup_status"] == "NONE"
        assert st.storage_state["recovered_from_backup"] is False
        assert st.virtual_balance == 800_000

    def test_valid_load_after_unrecoverable_resets_backup_status(
        self, isolated_storage
    ):
        """CORRUPT_UNRECOVERABLE → valid load: backup_status must reset to NONE."""
        storage_file, storage_backup, _ = isolated_storage

        # First load: both files corrupt → CORRUPT_UNRECOVERABLE
        _write_corrupt(storage_file)
        _write_corrupt(storage_backup)
        with pytest.raises(st.VGXStorageError):
            st.load_data()
        assert st.storage_state["status"] == "CORRUPT_UNRECOVERABLE"
        assert st.storage_state["backup_status"] == "FAILED"

        # Operator restores a valid file; next load must clear stale state
        _write_json(storage_file, _valid_payload(virtual_balance=650_000))
        st.load_data()

        assert st.storage_state["status"] == "SYNCED"
        assert st.storage_state["backup_status"] == "NONE"
        assert st.storage_state["recovered_from_backup"] is False
        assert st.virtual_balance == 650_000

    def test_fresh_start_after_backup_recovery_resets_backup_status(
        self, isolated_storage
    ):
        """RECOVERED_FROM_BACKUP → fresh start: backup_status must reset to NONE."""
        storage_file, storage_backup, _ = isolated_storage

        # First: corrupt primary, valid backup → RECOVERED_FROM_BACKUP
        _write_corrupt(storage_file)
        _write_json(storage_backup, _valid_payload())
        st.load_data()
        assert st.storage_state["status"] == "RECOVERED_FROM_BACKUP"

        # Simulate a clean environment (delete all files)
        os.remove(str(storage_file))
        os.remove(str(storage_backup))
        st.virtual_balance = 1_000_000  # reset globals

        st.load_data()

        assert st.storage_state["status"] == "SYNCED"  # after save_data() in fresh path
        assert st.storage_state["backup_status"] == "NONE"
        assert st.storage_state["recovered_from_backup"] is False

    def test_status_backup_status_recovered_always_coherent(self, isolated_storage):
        """Coherence contract: backup_status and recovered_from_backup must
        be consistent with status after every load_data() call."""
        storage_file, storage_backup, _ = isolated_storage

        # SYNCED: backup_status=NONE, recovered=False
        _write_json(storage_file, _valid_payload())
        st.load_data()
        assert st.storage_state["status"] == "SYNCED"
        assert st.storage_state["backup_status"] == "NONE"
        assert st.storage_state["recovered_from_backup"] is False

        # RECOVERED_FROM_BACKUP: backup_status=RESTORED, recovered=True
        # Explicitly write a valid backup (no save_data() was called above,
        # so the backup file does not yet exist on disk).
        _write_corrupt(storage_file)
        _write_json(storage_backup, _valid_payload(virtual_balance=900_000))
        st.load_data()
        assert st.storage_state["status"] == "RECOVERED_FROM_BACKUP"
        assert st.storage_state["backup_status"] == "RESTORED"
        assert st.storage_state["recovered_from_backup"] is True

        # CORRUPT_UNRECOVERABLE: backup_status=FAILED, recovered=False
        _write_corrupt(storage_file)
        _write_corrupt(storage_backup)
        with pytest.raises(st.VGXStorageError):
            st.load_data()
        assert st.storage_state["status"] == "CORRUPT_UNRECOVERABLE"
        assert st.storage_state["backup_status"] == "FAILED"
        assert st.storage_state["recovered_from_backup"] is False
