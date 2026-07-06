"""
C-2 Fix Tests — Atomic Cash Balance Updates (PMB + MTB)

Verifies:
1. update_stats() holds _stats_lock across the entire read→modify→write
   sequence, preventing lost updates under concurrent mutation.
2. No lost updates when N threads simultaneously deduct cash.
3. Cash is always correct (sum of all deductions is exact).
4. No negative-balance race — all deductions happen atomically under the lock,
   so a cash-gate inside a callback is honoured without races.
5. PMB and MTB update_stats() are independent (separate storage files).
6. save_stats() (legacy API) still works and does not deadlock.
7. update_stats() return value reflects the saved state.
8. The daily_pnl reset logic inside an update_stats callback works correctly.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _write_stats(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_stats(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────────────
# PMB fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def pmb_storage_dir(tmp_path, monkeypatch):
    """Isolate PMB storage to a temp directory; returns (storage_module, stats_path)."""
    data_dir = tmp_path / "pmb_data"
    data_dir.mkdir()
    stats_file = data_dir / "stats.json"

    import importlib
    import bots.pmb_bot.storage as pmb_st

    monkeypatch.setattr(pmb_st, "DATA_DIR",    data_dir,  raising=True)
    monkeypatch.setattr(pmb_st, "STATS_FILE",  stats_file, raising=True)
    monkeypatch.setattr(pmb_st, "POSITIONS_FILE", data_dir / "positions.json", raising=True)
    monkeypatch.setattr(pmb_st, "TRADES_FILE",    data_dir / "trades.json",    raising=True)

    # Reset per-file locks so each test gets a fresh state
    monkeypatch.setattr(pmb_st, "_stats_lock",     threading.Lock(), raising=True)
    monkeypatch.setattr(pmb_st, "_positions_lock", threading.Lock(), raising=True)
    monkeypatch.setattr(pmb_st, "_trades_lock",    threading.Lock(), raising=True)

    yield pmb_st, stats_file


@pytest.fixture()
def pmb_with_cash(pmb_storage_dir):
    """PMB storage initialised with 10_000 cash balance."""
    pmb_st, stats_file = pmb_storage_dir
    _write_stats(stats_file, {
        "cash_balance":   10_000.0,
        "total_invested":     0.0,
        "total_pnl":          0.0,
        "daily_pnl":          0.0,
    })
    return pmb_st, stats_file


# ──────────────────────────────────────────────────────────────────────────────
# MTB fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def mtb_storage_dir(tmp_path, monkeypatch):
    """Isolate MTB storage to a temp directory; returns (storage_module, stats_path)."""
    data_dir = tmp_path / "mtb_data"
    data_dir.mkdir()
    stats_file = data_dir / "stats.json"

    import bots.mtb_bot.storage as mtb_st

    monkeypatch.setattr(mtb_st, "DATA_DIR",    data_dir,  raising=True)
    monkeypatch.setattr(mtb_st, "STATS_FILE",  stats_file, raising=True)
    monkeypatch.setattr(mtb_st, "POSITIONS_FILE", data_dir / "positions.json", raising=True)
    monkeypatch.setattr(mtb_st, "TRADES_FILE",    data_dir / "trades.json",    raising=True)

    monkeypatch.setattr(mtb_st, "_stats_lock",     threading.Lock(), raising=True)
    monkeypatch.setattr(mtb_st, "_positions_lock", threading.Lock(), raising=True)
    monkeypatch.setattr(mtb_st, "_trades_lock",    threading.Lock(), raising=True)

    yield mtb_st, stats_file


@pytest.fixture()
def mtb_with_cash(mtb_storage_dir):
    """MTB storage initialised with 10_000 cash balance."""
    mtb_st, stats_file = mtb_storage_dir
    _write_stats(stats_file, {
        "cash_balance":  10_000.0,
        "trade_amount":      0.0,
        "total_pnl":         0.0,
        "daily_pnl":         0.0,
    })
    return mtb_st, stats_file


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — update_stats() basic contract (PMB)
# ══════════════════════════════════════════════════════════════════════════════

class TestPMBUpdateStatsContract:

    def test_mutates_cash_balance(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 9_000.0))
        assert _read_stats(stats_file)["cash_balance"] == 9_000.0

    def test_returns_saved_dict(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        result = pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 8_500.0))
        assert isinstance(result, dict)
        assert result["cash_balance"] == 8_500.0

    def test_stamps_last_updated(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        result = pmb_st.update_stats(lambda s: None)
        assert "last_updated" in result
        saved = _read_stats(stats_file)
        assert "last_updated" in saved

    def test_does_not_clobber_other_fields(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 7_000.0))
        saved = _read_stats(stats_file)
        assert "total_pnl" in saved
        assert "daily_pnl" in saved

    def test_no_deadlock_with_sequential_calls(self, pmb_with_cash):
        """Two sequential update_stats() calls must not deadlock."""
        pmb_st, _ = pmb_with_cash
        pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 9_000.0))
        pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 8_000.0))
        assert pmb_st.load_stats()["cash_balance"] == 8_000.0

    def test_save_stats_still_works(self, pmb_with_cash):
        """save_stats() (legacy path) must not deadlock after update_stats()."""
        pmb_st, stats_file = pmb_with_cash
        pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 5_000.0))
        stats = pmb_st.load_stats()
        stats["cash_balance"] = 4_000.0
        pmb_st.save_stats(stats)
        assert _read_stats(stats_file)["cash_balance"] == 4_000.0


# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — update_stats() basic contract (MTB)
# ══════════════════════════════════════════════════════════════════════════════

class TestMTBUpdateStatsContract:

    def test_mutates_cash_balance(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        mtb_st.update_stats(lambda s: s.__setitem__("cash_balance", 9_000.0))
        assert _read_stats(stats_file)["cash_balance"] == 9_000.0

    def test_returns_saved_dict(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        result = mtb_st.update_stats(lambda s: s.__setitem__("cash_balance", 8_500.0))
        assert isinstance(result, dict)
        assert result["cash_balance"] == 8_500.0

    def test_stamps_last_updated(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        result = mtb_st.update_stats(lambda s: None)
        assert "last_updated" in result

    def test_save_stats_still_works(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        mtb_st.update_stats(lambda s: s.__setitem__("cash_balance", 5_000.0))
        stats = mtb_st.load_stats()
        stats["cash_balance"] = 4_000.0
        mtb_st.save_stats(stats)
        assert _read_stats(stats_file)["cash_balance"] == 4_000.0

    def test_trade_amount_field_persisted(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        result = mtb_st.update_stats(lambda s: s.__setitem__("trade_amount", 1_000.0))
        assert _read_stats(stats_file)["trade_amount"] == 1_000.0


# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — Concurrent stress tests (no lost updates)
# ══════════════════════════════════════════════════════════════════════════════

_THREAD_TIMEOUT = 15.0  # seconds — generous for constrained CI runners


def _join_all(threads: list[threading.Thread], timeout: float = _THREAD_TIMEOUT) -> None:
    """Join every thread; assert none are still alive (hangs surface as failures)."""
    for t in threads:
        t.join(timeout=timeout)
    alive = [t.name for t in threads if t.is_alive()]
    assert not alive, f"Threads still alive after {timeout}s: {alive}"


def _run_concurrent_deductions(storage_module, n_threads: int, deduct: float) -> None:
    """Launch *n_threads* threads each deducting *deduct* from cash_balance
    using update_stats().  Each thread records success or failure."""
    barrier = threading.Barrier(n_threads)
    errors: list[Exception] = []

    def _worker():
        try:
            barrier.wait(timeout=_THREAD_TIMEOUT)  # all threads start simultaneously
        except threading.BrokenBarrierError:
            return
        try:
            def _deduct(s):
                s["cash_balance"] = round(
                    float(s.get("cash_balance", 0.0)) - deduct, 8
                )
            storage_module.update_stats(_deduct)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, daemon=True) for _ in range(n_threads)]
    for t in threads:
        t.start()
    _join_all(threads)

    if errors:
        raise errors[0]


class TestConcurrentDeductionsNoLostUpdates:
    """
    Stress: N threads each deduct D from cash simultaneously.
    Expected final balance = initial − N * D (exact; no lost update).
    """

    # ── PMB ──────────────────────────────────────────────────────────────────

    def test_pmb_10_threads_exact_balance(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        initial   = 10_000.0
        n         = 10
        per_trade = 100.0
        _run_concurrent_deductions(pmb_st, n, per_trade)
        final = _read_stats(stats_file)["cash_balance"]
        expected = round(initial - n * per_trade, 8)
        assert final == expected, f"Lost update detected: expected {expected}, got {final}"

    def test_pmb_50_threads_exact_balance(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        initial   = 10_000.0
        n         = 50
        per_trade = 100.0
        _run_concurrent_deductions(pmb_st, n, per_trade)
        final = _read_stats(stats_file)["cash_balance"]
        expected = round(initial - n * per_trade, 8)
        assert final == expected, f"Lost update: expected {expected}, got {final}"

    def test_pmb_no_lost_update_mixed_deduct_credit(self, pmb_with_cash):
        """Interleave deductions and credits under concurrent load."""
        pmb_st, stats_file = pmb_with_cash
        n_each = 20
        amount = 50.0
        barrier = threading.Barrier(n_each * 2)

        def _deduct():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            pmb_st.update_stats(lambda s: s.__setitem__(
                "cash_balance", round(float(s.get("cash_balance", 0.0)) - amount, 8)
            ))

        def _credit():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            pmb_st.update_stats(lambda s: s.__setitem__(
                "cash_balance", round(float(s.get("cash_balance", 0.0)) + amount, 8)
            ))

        threads = (
            [threading.Thread(target=_deduct, daemon=True) for _ in range(n_each)] +
            [threading.Thread(target=_credit, daemon=True) for _ in range(n_each)]
        )
        for t in threads:
            t.start()
        _join_all(threads)

        # Net change = 0 → balance unchanged
        final = _read_stats(stats_file)["cash_balance"]
        assert final == 10_000.0, f"Net balance wrong: {final}"

    # ── MTB ──────────────────────────────────────────────────────────────────

    def test_mtb_10_threads_exact_balance(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        initial   = 10_000.0
        n         = 10
        per_trade = 100.0
        _run_concurrent_deductions(mtb_st, n, per_trade)
        final = _read_stats(stats_file)["cash_balance"]
        expected = round(initial - n * per_trade, 8)
        assert final == expected, f"Lost update: expected {expected}, got {final}"

    def test_mtb_50_threads_exact_balance(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        initial   = 10_000.0
        n         = 50
        per_trade = 100.0
        _run_concurrent_deductions(mtb_st, n, per_trade)
        final = _read_stats(stats_file)["cash_balance"]
        expected = round(initial - n * per_trade, 8)
        assert final == expected, f"Lost update: expected {expected}, got {final}"

    def test_mtb_no_lost_update_mixed_deduct_credit(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        n_each = 20
        amount = 50.0
        barrier = threading.Barrier(n_each * 2)

        def _deduct():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            mtb_st.update_stats(lambda s: s.__setitem__(
                "cash_balance", round(float(s.get("cash_balance", 0.0)) - amount, 8)
            ))

        def _credit():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            mtb_st.update_stats(lambda s: s.__setitem__(
                "cash_balance", round(float(s.get("cash_balance", 0.0)) + amount, 8)
            ))

        threads = (
            [threading.Thread(target=_deduct, daemon=True) for _ in range(n_each)] +
            [threading.Thread(target=_credit, daemon=True) for _ in range(n_each)]
        )
        for t in threads:
            t.start()
        _join_all(threads)

        final = _read_stats(stats_file)["cash_balance"]
        assert final == 10_000.0, f"Net balance wrong: {final}"


# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — No negative-balance race (cash gate inside callback)
# ══════════════════════════════════════════════════════════════════════════════

class TestNoNegativeBalanceRace:
    """
    Cash gate: callback checks balance BEFORE deducting.
    With the lock held across the full RMW, only as many deductions as
    the balance can cover should succeed — balance never goes negative.
    """

    def _gated_deduct(self, storage_module, amount: float) -> bool:
        """Deduct *amount* only if sufficient cash; return True if deducted."""
        deducted = False

        def _fn(s):
            nonlocal deducted
            if float(s.get("cash_balance", 0.0)) >= amount:
                s["cash_balance"] = round(
                    float(s.get("cash_balance", 0.0)) - amount, 8
                )
                deducted = True

        storage_module.update_stats(_fn)
        return deducted

    def test_pmb_never_goes_negative(self, pmb_with_cash):
        """50 threads each try to deduct 300 from a 10_000 balance (max 33 can succeed)."""
        pmb_st, stats_file = pmb_with_cash
        n       = 50
        amount  = 300.0
        success_count = 0
        lock    = threading.Lock()
        barrier = threading.Barrier(n)

        def _worker():
            nonlocal success_count
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            if self._gated_deduct(pmb_st, amount):
                with lock:
                    success_count += 1

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(n)]
        for t in threads:
            t.start()
        _join_all(threads)

        final = _read_stats(stats_file)["cash_balance"]
        assert final >= 0, f"Balance went negative: {final}"
        assert round(success_count * amount, 8) == round(10_000.0 - final, 8), \
            f"Balance mismatch: {success_count} deductions × {amount} != 10000 - {final}"

    def test_mtb_never_goes_negative(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        n       = 50
        amount  = 300.0
        success_count = 0
        lock    = threading.Lock()
        barrier = threading.Barrier(n)

        def _worker():
            nonlocal success_count
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            if self._gated_deduct(mtb_st, amount):
                with lock:
                    success_count += 1

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(n)]
        for t in threads:
            t.start()
        _join_all(threads)

        final = _read_stats(stats_file)["cash_balance"]
        assert final >= 0, f"Balance went negative: {final}"
        assert round(success_count * amount, 8) == round(10_000.0 - final, 8)

    def test_pmb_exactly_one_succeeds_when_only_one_can_afford(self, pmb_with_cash):
        """Only one thread can afford the trade when balance == trade_amount."""
        pmb_st, stats_file = pmb_with_cash
        # Set balance to exactly one trade
        pmb_st.update_stats(lambda s: s.__setitem__("cash_balance", 100.0))
        n       = 10
        amount  = 100.0
        successes = []
        lock    = threading.Lock()
        barrier = threading.Barrier(n)

        def _worker():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            ok = self._gated_deduct(pmb_st, amount)
            if ok:
                with lock:
                    successes.append(True)

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(n)]
        for t in threads:
            t.start()
        _join_all(threads)

        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
        assert _read_stats(stats_file)["cash_balance"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — Independence: PMB and MTB locks don't interfere
# ══════════════════════════════════════════════════════════════════════════════

class TestPMBMTBStorageIndependence:

    def test_concurrent_pmb_and_mtb_deductions_are_independent(
        self, pmb_with_cash, mtb_with_cash
    ):
        """Concurrent PMB and MTB updates must not interfere with each other."""
        pmb_st, pmb_file = pmb_with_cash
        mtb_st, mtb_file = mtb_with_cash

        n       = 20
        amount  = 100.0
        barrier = threading.Barrier(n * 2)

        def _pmb_worker():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            pmb_st.update_stats(lambda s: s.__setitem__(
                "cash_balance", round(float(s.get("cash_balance", 0.0)) - amount, 8)
            ))

        def _mtb_worker():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return
            mtb_st.update_stats(lambda s: s.__setitem__(
                "cash_balance", round(float(s.get("cash_balance", 0.0)) - amount, 8)
            ))

        threads = (
            [threading.Thread(target=_pmb_worker, daemon=True) for _ in range(n)] +
            [threading.Thread(target=_mtb_worker, daemon=True) for _ in range(n)]
        )
        for t in threads:
            t.start()
        _join_all(threads)

        pmb_final = _read_stats(pmb_file)["cash_balance"]
        mtb_final = _read_stats(mtb_file)["cash_balance"]

        assert pmb_final == round(10_000.0 - n * amount, 8)
        assert mtb_final == round(10_000.0 - n * amount, 8)


# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — daily_pnl reset logic inside callback
# ══════════════════════════════════════════════════════════════════════════════

class TestDailyPnLResetInsideCallback:
    """
    The daily_pnl reset (new day → zero, stamp date) happens inside the
    update_stats callback.  Verify it works correctly when called
    concurrently with deductions.
    """

    def test_pmb_daily_pnl_accumulates_correctly_single_thread(self, pmb_with_cash):
        """Single-threaded: three PnL credits accumulate correctly."""
        from datetime import datetime, timezone
        pmb_st, stats_file = pmb_with_cash

        today = datetime.now(timezone.utc).date().isoformat()
        for pnl in [10.0, 20.0, 30.0]:
            _pnl = pnl  # capture

            def _fn(s, _p=_pnl):
                _t = datetime.now(timezone.utc).date().isoformat()
                if s.get("daily_pnl_date") != _t:
                    s["daily_pnl"]      = 0.0
                    s["daily_pnl_date"] = _t
                s["daily_pnl"] = round(float(s.get("daily_pnl", 0.0)) + _p, 8)
                s["total_pnl"] = round(float(s.get("total_pnl", 0.0)) + _p, 8)

            pmb_st.update_stats(_fn)

        saved = _read_stats(stats_file)
        assert saved["daily_pnl"] == 60.0
        assert saved["total_pnl"] == 60.0

    def test_mtb_daily_pnl_accumulates_correctly_single_thread(self, mtb_with_cash):
        from datetime import datetime, timezone
        mtb_st, stats_file = mtb_with_cash

        for pnl in [5.0, 15.0, 25.0]:
            _pnl = pnl

            def _fn(s, _p=_pnl):
                _t = datetime.now(timezone.utc).date().isoformat()
                if s.get("daily_pnl_date") != _t:
                    s["daily_pnl"]      = 0.0
                    s["daily_pnl_date"] = _t
                s["daily_pnl"] = round(float(s.get("daily_pnl", 0.0)) + _p, 8)
                s["total_pnl"] = round(float(s.get("total_pnl", 0.0)) + _p, 8)

            mtb_st.update_stats(_fn)

        saved = _read_stats(stats_file)
        assert saved["daily_pnl"] == 45.0
        assert saved["total_pnl"] == 45.0

    def test_pmb_daily_pnl_no_lost_updates_concurrent(self, pmb_with_cash):
        """30 threads each add 1.0 to daily_pnl; result must be exactly 30.0."""
        from datetime import datetime, timezone
        pmb_st, stats_file = pmb_with_cash

        n       = 30
        barrier = threading.Barrier(n)

        def _worker():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return

            def _fn(s):
                from datetime import datetime, timezone
                _t = datetime.now(timezone.utc).date().isoformat()
                if s.get("daily_pnl_date") != _t:
                    s["daily_pnl"]      = 0.0
                    s["daily_pnl_date"] = _t
                s["daily_pnl"] = round(float(s.get("daily_pnl", 0.0)) + 1.0, 8)

            pmb_st.update_stats(_fn)

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(n)]
        for t in threads:
            t.start()
        _join_all(threads)

        assert _read_stats(stats_file)["daily_pnl"] == float(n)


# ══════════════════════════════════════════════════════════════════════════════
# Section 7 — High-volume stress (100 concurrent deductions)
# ══════════════════════════════════════════════════════════════════════════════

class TestHighVolumeStress:

    def test_pmb_100_threads_all_deduct_no_lost_update(self, pmb_with_cash):
        pmb_st, stats_file = pmb_with_cash
        n         = 100
        per_trade = 50.0
        _run_concurrent_deductions(pmb_st, n, per_trade)
        final    = _read_stats(stats_file)["cash_balance"]
        expected = round(10_000.0 - n * per_trade, 8)
        assert final == expected, f"Expected {expected}, got {final} — lost update!"

    def test_mtb_100_threads_all_deduct_no_lost_update(self, mtb_with_cash):
        mtb_st, stats_file = mtb_with_cash
        n         = 100
        per_trade = 50.0
        _run_concurrent_deductions(mtb_st, n, per_trade)
        final    = _read_stats(stats_file)["cash_balance"]
        expected = round(10_000.0 - n * per_trade, 8)
        assert final == expected, f"Expected {expected}, got {final} — lost update!"

    def test_pmb_multiple_fields_all_consistent_under_load(self, pmb_with_cash):
        """Under concurrent load, cash_balance + total_invested must always
        sum to the initial cash (no deduction happened without a matching
        total_invested increment)."""
        pmb_st, stats_file = pmb_with_cash
        n      = 50
        amount = 100.0
        barrier = threading.Barrier(n)

        def _worker():
            try:
                barrier.wait(timeout=_THREAD_TIMEOUT)
            except threading.BrokenBarrierError:
                return

            def _fn(s, _a=amount):
                s["cash_balance"]   = round(float(s.get("cash_balance",   0.0)) - _a, 8)
                s["total_invested"] = round(float(s.get("total_invested", 0.0)) + _a, 8)

            pmb_st.update_stats(_fn)

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(n)]
        for t in threads:
            t.start()
        _join_all(threads)

        saved = _read_stats(stats_file)
        cash     = saved["cash_balance"]
        invested = saved["total_invested"]
        assert round(cash + invested, 4) == 10_000.0, \
            f"cash({cash}) + invested({invested}) != 10000 — fields drifted apart"
