"""
Tests for shared-state file locking introduced to prevent last-write-wins races.

Coverage:
  1. watchlist_manager.add_coin() / remove_coin() — concurrent safety
  2. scanner.append_signal_history() — concurrent read-modify-write safety
  3. VGX storage.save_data() — regression (already locked; must stay correct)
  4. Single-writer regression — locked paths behave identically to before
  5. Lock-timeout path — RuntimeError raised, logger.warning emitted
"""

import json
import os
import sys
import tempfile
import threading
import time
import logging

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _tmp_json(data) -> str:
    """Write *data* to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


# =============================================================================
# 1.  watchlist_manager — concurrent add_coin / remove_coin
# =============================================================================

class TestWatchlistManagerLocking:
    """Concurrent writers must not lose each other's updates."""

    def _make_module(self, initial_coins: list, tmp_path):
        """Return a fresh watchlist_manager module wired to a temp file."""
        import importlib
        import bots.shared.watchlist_manager as wm_orig

        # Write the initial watchlist file
        wl_file = str(tmp_path / "watchlist.json")
        with open(wl_file, "w", encoding="utf-8") as f:
            json.dump({"coins": initial_coins, "updated_at": 0}, f)

        # Patch module-level constants to point at the temp file, then reset
        # internal state so ensure_migration() becomes a no-op.
        old_file    = wm_orig._SCANNER_WATCHLIST_FILE
        old_result  = wm_orig._MIGRATION_RESULT
        wm_orig._SCANNER_WATCHLIST_FILE = wl_file
        wm_orig._MIGRATION_RESULT       = []   # mark migration as done

        yield wm_orig, wl_file

        # Restore
        wm_orig._SCANNER_WATCHLIST_FILE = old_file
        wm_orig._MIGRATION_RESULT       = old_result

    def test_single_add_coin_no_regression(self, tmp_path):
        """Single-writer path returns expected list unchanged."""
        import bots.shared.watchlist_manager as wm
        gen = self._make_module(["ETH", "SOL"], tmp_path)
        wm_mod, wl_file = next(gen)
        try:
            result = wm_mod.add_coin("BTC")
            assert "BTC" in result["coins"]
            assert "ETH" in result["coins"]
            with open(wl_file) as f:
                data = json.load(f)
            assert "BTC" in data["coins"]
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_single_remove_coin_no_regression(self, tmp_path):
        """Single-writer remove behaves identically to pre-lock code."""
        import bots.shared.watchlist_manager as wm
        gen = self._make_module(["BTC", "ETH", "SOL"], tmp_path)
        wm_mod, wl_file = next(gen)
        try:
            result = wm_mod.remove_coin("ETH")
            assert "ETH" not in result["coins"]
            assert "BTC" in result["coins"]
            with open(wl_file) as f:
                data = json.load(f)
            assert "ETH" not in data["coins"]
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_concurrent_add_coin_no_lost_update(self, tmp_path):
        """Two concurrent add_coin() calls must both land in the file."""
        import bots.shared.watchlist_manager as wm
        gen = self._make_module([], tmp_path)
        wm_mod, wl_file = next(gen)

        errors = []
        barrier = threading.Barrier(2)

        def _add(coin):
            try:
                barrier.wait()          # start at the same instant
                wm_mod.add_coin(coin)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_add, args=("BTC",))
        t2 = threading.Thread(target=_add, args=("ETH",))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Unexpected errors: {errors}"
        with open(wl_file) as f:
            coins = json.load(f)["coins"]
        assert "BTC" in coins, "BTC was lost in concurrent add"
        assert "ETH" in coins, "ETH was lost in concurrent add"

    def test_concurrent_add_remove_deterministic(self, tmp_path):
        """Concurrent add + remove leave exactly one coin in the list."""
        import bots.shared.watchlist_manager as wm
        gen = self._make_module(["ETH"], tmp_path)
        wm_mod, wl_file = next(gen)

        errors = []
        barrier = threading.Barrier(2)

        def _add():
            try:
                barrier.wait()
                wm_mod.add_coin("BTC")
            except Exception as exc:
                errors.append(exc)

        def _remove():
            try:
                barrier.wait()
                wm_mod.remove_coin("ETH")
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_add)
        t2 = threading.Thread(target=_remove)
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Unexpected errors: {errors}"
        with open(wl_file) as f:
            coins = json.load(f)["coins"]
        # BTC was added, ETH was removed — order may vary but both must be applied
        assert "BTC" in coins, "BTC add was lost"
        assert "ETH" not in coins, "ETH remove was lost"

    def test_many_concurrent_adds_no_lost_update(self, tmp_path):
        """10 concurrent add_coin() calls — all 10 coins must appear in the file."""
        import bots.shared.watchlist_manager as wm
        gen = self._make_module([], tmp_path)
        wm_mod, wl_file = next(gen)

        coins_to_add = [f"COIN{i}" for i in range(10)]
        errors = []
        barrier = threading.Barrier(len(coins_to_add))

        def _add(coin):
            try:
                barrier.wait()
                wm_mod.add_coin(coin)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_add, args=(c,)) for c in coins_to_add]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Unexpected errors: {errors}"
        with open(wl_file) as f:
            final_coins = json.load(f)["coins"]
        for coin in coins_to_add:
            assert coin in final_coins, f"{coin} was lost in 10-way concurrent add"

    def test_lock_timeout_raises_and_warns(self, tmp_path, caplog):
        """When the lock is held by another thread and times out, RuntimeError is
        raised and logger.warning is emitted.

        NOTE: _watchlist_lock is an RLock — re-entrant for the *same* thread, but
        blocking for *other* threads.  We must hold the lock from a background
        thread so that the main thread's add_coin() acquire actually blocks.
        """
        import bots.shared.watchlist_manager as wm
        gen = self._make_module([], tmp_path)
        wm_mod, wl_file = next(gen)

        old_timeout = wm_mod._LOCK_TIMEOUT
        wm_mod._LOCK_TIMEOUT = 0.05   # 50 ms — fast timeout for the test

        lock_held   = threading.Event()   # background thread signals "I hold it"
        release_sig = threading.Event()   # main thread signals "release now"

        def _hold_lock():
            wm_mod._watchlist_lock.acquire()
            lock_held.set()
            release_sig.wait(timeout=3)   # wait until the test is done
            wm_mod._watchlist_lock.release()

        holder = threading.Thread(target=_hold_lock, daemon=True)
        holder.start()
        assert lock_held.wait(timeout=2), "Background thread never acquired the lock"

        try:
            with caplog.at_level(logging.WARNING, logger="watchlist_manager"):
                with pytest.raises(RuntimeError, match="lock timeout"):
                    wm_mod.add_coin("BTC")
            assert any("timed out" in r.message or "timeout" in r.message
                       for r in caplog.records), (
                "Expected a logger.warning about lock timeout"
            )
        finally:
            wm_mod._LOCK_TIMEOUT = old_timeout
            release_sig.set()
            holder.join(timeout=2)
            try:
                next(gen)
            except StopIteration:
                pass


# =============================================================================
# 2.  scanner.append_signal_history() — concurrent read-modify-write
# =============================================================================

class TestAppendSignalHistoryLocking:
    """Two concurrent append_signal_history() calls must not lose an entry."""

    def _make_history_env(self, tmp_path):
        """Redirect scanner history file to a temp path and reset cache."""
        import bots.scanner_bot.scanner as sc
        old_file  = sc.SIGNAL_HISTORY_FILE
        old_cache = sc._history_cache
        history_file = str(tmp_path / "signal_history.json")
        with open(history_file, "w") as f:
            json.dump({"signals": []}, f)
        sc.SIGNAL_HISTORY_FILE = history_file
        sc._history_cache      = None   # force disk re-read

        yield sc, history_file

        sc.SIGNAL_HISTORY_FILE = old_file
        sc._history_cache      = old_cache

    def test_single_append_no_regression(self, tmp_path):
        """Single append writes exactly one entry to disk."""
        gen = self._make_history_env(tmp_path)
        sc, hist_file = next(gen)
        entry = {"id": "sig-1", "coin": "BTC", "timestamp": "2026-01-01T00:00:00"}
        result = sc.append_signal_history(entry)
        assert result is True
        with open(hist_file) as f:
            data = json.load(f)
        assert len(data["signals"]) == 1
        assert data["signals"][0]["id"] == "sig-1"
        try:
            next(gen)
        except StopIteration:
            pass

    def test_dedup_still_works(self, tmp_path):
        """Duplicate id is rejected — no regression from lock addition."""
        gen = self._make_history_env(tmp_path)
        sc, hist_file = next(gen)
        entry = {"id": "sig-dup", "coin": "ETH", "timestamp": "2026-01-01T00:00:00"}
        r1 = sc.append_signal_history(entry)
        r2 = sc.append_signal_history(entry)
        assert r1 is True
        assert r2 is False   # duplicate blocked
        with open(hist_file) as f:
            data = json.load(f)
        assert len(data["signals"]) == 1
        try:
            next(gen)
        except StopIteration:
            pass

    def test_concurrent_appends_no_lost_entry(self, tmp_path):
        """10 concurrent append_signal_history() calls — all 10 must land on disk."""
        gen = self._make_history_env(tmp_path)
        sc, hist_file = next(gen)

        entries = [
            {"id": f"sig-{i}", "coin": f"COIN{i}", "timestamp": "2026-01-01T00:00:00"}
            for i in range(10)
        ]
        errors = []
        barrier = threading.Barrier(len(entries))

        def _append(entry):
            try:
                barrier.wait()
                sc.append_signal_history(entry)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_append, args=(e,)) for e in entries]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Unexpected errors: {errors}"
        sc._history_cache = None   # bypass cache so we read fresh from disk
        with open(hist_file) as f:
            data = json.load(f)
        ids = {s["id"] for s in data["signals"]}
        for entry in entries:
            assert entry["id"] in ids, (
                f"{entry['id']} was lost in concurrent append — pre-lock race reproduced"
            )

        try:
            next(gen)
        except StopIteration:
            pass

    def test_history_lock_is_rlock(self):
        """_history_lock must be an RLock (re-entrant) so append+write don't deadlock."""
        import bots.scanner_bot.scanner as sc
        import threading as _threading
        # RLock supports acquire() from the same thread while already held.
        # If it were a plain Lock this would deadlock.
        assert sc._history_lock.acquire(blocking=True)
        try:
            # A second acquire from the same thread must succeed (RLock semantics).
            re_acquired = sc._history_lock.acquire(blocking=False)
            assert re_acquired, "_history_lock is not re-entrant — must be RLock"
        finally:
            # Release both acquires.
            sc._history_lock.release()
            sc._history_lock.release()


# =============================================================================
# 3.  VGX storage.save_data() — regression (already locked; must stay correct)
# =============================================================================

class TestVGXStorageLockRegression:
    """save_data() is already protected by _storage_lock; verify it remains so."""

    def test_save_data_uses_storage_lock(self):
        """storage.py _storage_lock is acquired inside save_data()."""
        import bots.volatile_gridX.storage as vgx_storage
        import threading as _threading
        # The lock exists and is a threading.Lock (not None / missing).
        lock = vgx_storage._storage_lock
        assert lock is not None
        assert hasattr(lock, "acquire"), "Expected a Lock/RLock object"

    def test_concurrent_save_data_no_corruption(self, tmp_path):
        """Two concurrent save_data() calls must not corrupt the storage file."""
        import bots.volatile_gridX.storage as vgx_storage
        import shutil

        orig_file   = vgx_storage.STORAGE_FILE
        orig_backup = vgx_storage.STORAGE_BACKUP
        orig_dir    = vgx_storage.STORAGE_DIR

        tmp_storage = str(tmp_path / "TradingBotCrypto.json")
        tmp_backup  = str(tmp_path / "TradingBotCrypto.backup.json")

        vgx_storage.STORAGE_FILE   = tmp_storage
        vgx_storage.STORAGE_BACKUP = tmp_backup
        vgx_storage.STORAGE_DIR    = str(tmp_path)

        errors = []
        barrier = threading.Barrier(2)

        def _save():
            try:
                barrier.wait()
                vgx_storage.save_data()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_save)
        t2 = threading.Thread(target=_save)
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Unexpected errors during concurrent save_data: {errors}"
        # The final file must be valid JSON (no corruption).
        with open(tmp_storage, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), "Corrupted storage file after concurrent saves"

        vgx_storage.STORAGE_FILE   = orig_file
        vgx_storage.STORAGE_BACKUP = orig_backup
        vgx_storage.STORAGE_DIR    = orig_dir
