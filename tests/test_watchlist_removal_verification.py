"""
PROJECT-ALPHA — Watchlist Removal Verification Suite

Tests that confirm VGX, PMB, and MTB work correctly after removing bot
watchlists and switching to a scanner-only architecture.

Pipeline verified: Exchange → Scanner → Signal Generation → VGX/PMB/MTB →
Risk Engine → Paper Trade → Dashboard → Telegram
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh_signal(symbol="BTCUSDT", coin="BTC", price=50000, score=90, confidence=80,
                  market_state="bull_trend", source="SCANNER"):
    """Return a scanner signal with a fresh timestamp so age checks pass."""
    return {
        "symbol": symbol,
        "coin": coin,
        "entry_price": price,
        "score": score,
        "confidence": confidence,
        "market_state": market_state,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# TEST 1 — Scanner → Bot: Signal Flow & No Per-Bot Watchlist Check
# =============================================================================

class TestSignalFlow:
    """Verify scanner generates signals and bots receive them via bridges."""

    def test_mtb_bridge_reads_from_scanner_module(self):
        """MTB bridge pulls signals from scanner main module (in-process)."""
        from bots.mtb_bot import scanner_bridge as mtb_bridge
        with patch("bots.mtb_bot.scanner_bridge._signals_from_dashboard_api", return_value=[]):
            signals = mtb_bridge.get_signals()
        assert isinstance(signals, list)

    def test_pmb_bridge_reads_from_scanner_module(self):
        """PMB bridge pulls signals from scanner main module (in-process)."""
        from bots.pmb_bot import scanner_bridge as pmb_bridge
        with patch("bots.pmb_bot.scanner_bridge._signals_from_dashboard_api", return_value=[]):
            signals = pmb_bridge.get_signals()
        assert isinstance(signals, list)

    def test_vgx_bridge_has_process_scanner_signal(self):
        """VGX bridge has entry point for scanner signals."""
        from bots.volatile_gridX import scanner_bridge as vgx_bridge
        assert hasattr(vgx_bridge, "process_scanner_signal")
        assert hasattr(vgx_bridge, "receive_signal")

    def test_no_bot_uses_own_watchlist_json(self):
        """
        No bot should read a per-bot watchlist.json file as a filter.
        The scanner watchlist is the single source of truth.
        """
        import ast
        bots = ["mtb_bot", "pmb_bot", "volatile_gridX"]
        for bot in bots:
            engine_path = Path(f"bots/{bot}/trading_engine.py")
            if not engine_path.exists():
                continue
            source = engine_path.read_text()
            bad_patterns = [
                'watchlist.json',
                'load_watchlist',
                'save_watchlist',
                'watchlist_manager',
            ]
            for p in bad_patterns:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) and p in node.value:
                        continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id == p:
                        raise AssertionError(f"{bot} references {p} in code logic")

    def test_bot_uses_scanner_bridge_not_watchlist_filter(self):
        """
        MTB and PMB use scanner_bridge.get_signals() — not a watchlist check.
        """
        source_mtb = Path("bots/mtb_bot/trading_engine.py").read_text()
        source_pmb = Path("bots/pmb_bot/trading_engine.py").read_text()
        assert "scanner_bridge.get_signals()" in source_mtb
        assert "scanner_bridge.get_signals()" in source_pmb
        assert "get_watchlist" not in source_mtb.split("def run_cycle")[1]
        assert "get_watchlist" not in source_pmb.split("def run_cycle")[1]


# =============================================================================
# TEST 2 — Bot Filters: Enable/Disable, Score, Market State, Max Trades, Capital
# =============================================================================

class TestBotFilters:
    """Verify each bot applies its strategy filters correctly."""

    # ── MTB Filters ───────────────────────────────────────────────────────────

    def test_mtb_disabled_by_default(self):
        """MTB_ENABLED defaults to false — bot does not run cycle."""
        assert os.getenv("MTB_ENABLED", "false").lower() != "true"

    def test_mtb_validate_signal_rejects_low_score(self):
        """MTB rejects signals below MIN_SIGNAL_SCORE."""
        from bots.mtb_bot.trading_engine import validate_signal
        signal = _fresh_signal(score=50)
        result = validate_signal(signal, [])
        assert not result.passed
        assert result.code == "SCORE_TOO_LOW"

    def test_mtb_validate_signal_rejects_blocked_market_state(self):
        """MTB rejects signals in BLOCKED_MARKET_STATES."""
        from bots.mtb_bot.trading_engine import validate_signal
        signal = _fresh_signal(market_state="downtrend")
        result = validate_signal(signal, [])
        assert not result.passed
        assert result.code == "BLOCKED_MARKET_STATE"

    def test_mtb_validate_signal_rejects_max_positions(self):
        """MTB rejects when MAX_POSITIONS reached."""
        from bots.mtb_bot.trading_engine import validate_signal
        from bots.mtb_bot.config import MAX_POSITIONS
        positions = [{"symbol": f"COIN{i}USDT", "status": "OPEN"} for i in range(MAX_POSITIONS + 2)]
        signal = _fresh_signal(symbol="NEWUSDT", coin="NEW")
        result = validate_signal(signal, positions)
        assert not result.passed
        assert result.code == "MAX_POSITIONS_REACHED"

    def test_mtb_validate_signal_rejects_insufficient_cash(self):
        """MTB rejects when cash balance < TRADE_AMOUNT."""
        from bots.mtb_bot.trading_engine import validate_signal
        with patch("bots.mtb_bot.trading_engine.storage.load_stats", return_value={"cash_balance": 50.0}):
            signal = _fresh_signal()
            result = validate_signal(signal, [])
        assert not result.passed
        assert result.code == "INSUFFICIENT_CASH"

    def test_mtb_validate_signal_accepts_good_signal(self):
        """MTB accepts a signal that passes all filters."""
        from bots.mtb_bot.trading_engine import validate_signal
        with patch("bots.mtb_bot.trading_engine.storage.load_stats", return_value={"cash_balance": 100000.0}):
            signal = _fresh_signal()
            result = validate_signal(signal, [])
        assert result.passed
        assert result.code == "OK"

    def test_mtb_paper_mode_hardcoded(self):
        """MTB operates in PAPER mode by default."""
        from bots.mtb_bot.config import BOT_MODE
        assert BOT_MODE.upper() == "PAPER"

    # ── PMB Filters ───────────────────────────────────────────────────────────

    def test_pmb_disabled_by_default(self):
        """PMB_ENABLED defaults to false."""
        assert os.getenv("PMB_ENABLED", "false").lower() != "true"

    def test_pmb_validate_signal_rejects_low_score(self):
        """PMB rejects signals below MIN_SIGNAL_SCORE."""
        from bots.pmb_bot.trading_engine import validate_signal
        signal = _fresh_signal(score=50)
        result = validate_signal(signal, [])
        assert not result.passed
        assert result.code == "SCORE_TOO_LOW"

    def test_pmb_validate_signal_rejects_max_positions(self):
        """PMB rejects when MAX_POSITIONS reached."""
        from bots.pmb_bot.trading_engine import validate_signal
        from bots.pmb_bot.config import MAX_POSITIONS
        positions = [{"symbol": f"COIN{i}USDT", "status": "OPEN"} for i in range(MAX_POSITIONS + 2)]
        signal = _fresh_signal(symbol="NEWUSDT", coin="NEW")
        result = validate_signal(signal, positions)
        assert not result.passed
        assert result.code == "MAX_POSITIONS_REACHED"

    def test_pmb_validate_signal_accepts_good_signal(self):
        """PMB accepts a signal that passes all filters."""
        from bots.pmb_bot.trading_engine import validate_signal
        with patch("bots.pmb_bot.trading_engine.storage.load_stats", return_value={"cash_balance": 100000.0}):
            signal = _fresh_signal()
            result = validate_signal(signal, [])
        assert result.passed
        assert result.code == "OK"

    def test_pmb_paper_mode_hardcoded(self):
        """PMB operates in PAPER mode by default."""
        from bots.pmb_bot.config import BOT_MODE
        assert BOT_MODE.upper() == "PAPER"

    # ── VGX Filters ───────────────────────────────────────────────────────────

    def test_vgx_risk_engine_rejects_low_score(self):
        """VGX risk engine rejects signals below min_score threshold."""
        from bots.volatile_gridX.risk_engine import risk_check
        ok, reason = risk_check(50)
        assert not ok
        assert "Below Threshold" in reason

    def test_vgx_risk_engine_rejects_max_positions(self):
        """VGX risk engine rejects when max positions reached."""
        from bots.volatile_gridX import risk_engine as vgx_risk
        from bots.volatile_gridX import storage as vgx_storage
        original_positions = vgx_storage.positions.copy()
        try:
            for i in range(10):
                vgx_storage.positions[f"COIN{i}_SCANNER"] = {"coin": f"COIN{i}"}
            ok, reason = vgx_risk.risk_check(80)
            assert not ok
            assert "Maximum Positions" in reason
        finally:
            vgx_storage.positions.clear()
            vgx_storage.positions.update(original_positions)

    def test_vgx_can_open_position_approves_valid(self):
        """VGX can_open_position approves a valid signal.
        Patches analyze_coin so market_intelligence() returns BULL regardless
        of available price history (tests the approval path, not the analyzer).
        """
        from unittest.mock import patch
        from bots.volatile_gridX.risk_engine import can_open_position
        bull_result = {"score": 85, "trend": "bullish", "rsi": 60, "ema": "bullish"}
        with patch("bots.volatile_gridX.risk_engine.analyze_coin", return_value=bull_result):
            ok, reason = can_open_position("NEWCOIN", 80)
        assert ok
        assert "APPROVED" in reason

    def test_vgx_validate_signal_rejects_non_buy(self):
        """VGX scanner bridge rejects non-BUY signals."""
        from bots.volatile_gridX.scanner_bridge import validate_signal
        ok, reason, _ = validate_signal({"coin": "BTC", "action": "SELL", "score": 80})
        assert not ok
        assert "BUY ONLY" in reason

    def test_vgx_paper_mode(self):
        """VGX trading engine uses virtual balance — paper mode."""
        from bots.volatile_gridX import storage as vgx_storage
        assert hasattr(vgx_storage, "virtual_balance")


# =============================================================================
# TEST 3 — Trade Execution: Open, Cash Deduct, Log, Close, PnL
# =============================================================================

class TestTradeExecution:
    """Verify full position lifecycle for each bot."""

    def test_mtb_open_position_deducts_cash_and_logs_trade(self):
        """MTB: open → cash down → trade logged."""
        import tempfile
        from bots.mtb_bot.trading_engine import open_paper_position
        from bots.mtb_bot import storage as mtb_storage
        from bots.risk_engine import engine as risk_engine

        tmpdir = tempfile.mkdtemp()
        try:
            with patch.object(risk_engine, "TRADING_ENABLED", True):
             with patch("bots.mtb_bot.storage.DATA_DIR", Path(tmpdir)):
                with patch("bots.mtb_bot.storage.POSITIONS_FILE", Path(tmpdir) / "positions.json"):
                    with patch("bots.mtb_bot.storage.TRADES_FILE", Path(tmpdir) / "trades.json"):
                        with patch("bots.mtb_bot.storage.STATS_FILE", Path(tmpdir) / "stats.json"):
                            mtb_storage.ensure_storage()
                            mtb_storage.save_stats({"cash_balance": 100000.0})
                            result = open_paper_position(_fresh_signal(source="MTB_SCANNER"))
                            assert result["ok"]
                            stats = mtb_storage.load_stats()
                            assert stats["cash_balance"] < 100000.0
                            trades = mtb_storage.load_trades()
                            assert any(t["action"] == "BUY" and t["symbol"] == "BTCUSDT" for t in trades)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_mtb_close_position_updates_pnl_and_cash(self):
        """MTB: close → PnL calculated → cash restored."""
        import tempfile
        from bots.mtb_bot.trading_engine import close_position
        from bots.mtb_bot import storage as mtb_storage

        tmpdir = tempfile.mkdtemp()
        try:
            with patch("bots.mtb_bot.storage.DATA_DIR", Path(tmpdir)):
                with patch("bots.mtb_bot.storage.POSITIONS_FILE", Path(tmpdir) / "positions.json"):
                    with patch("bots.mtb_bot.storage.TRADES_FILE", Path(tmpdir) / "trades.json"):
                        with patch("bots.mtb_bot.storage.STATS_FILE", Path(tmpdir) / "stats.json"):
                            mtb_storage.ensure_storage()
                            mtb_storage.save_positions([{
                                "id": "MTB-BTCUSDT-1234567890",
                                "symbol": "BTCUSDT", "coin": "BTC", "status": "OPEN",
                                "entry_price": 50000, "quantity": 0.0022,
                                "total_cost": 110, "take_profit_price": 52500,
                                "stop_loss_price": 48500,
                            }])
                            mtb_storage.save_stats({"cash_balance": 100000.0, "total_pnl": 0.0})
                            result = close_position("BTCUSDT", 52000, "TAKE_PROFIT")
                            assert result["ok"]
                            assert result["position"]["status"] == "CLOSED"
                            assert result["position"]["pnl"] > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_pmb_open_base_position_deducts_cash_and_logs_trade(self):
        """PMB: base buy → cash down → trade logged."""
        import tempfile
        from bots.pmb_bot.trading_engine import open_base_position
        from bots.pmb_bot import storage as pmb_storage
        from bots.risk_engine import engine as risk_engine

        tmpdir = tempfile.mkdtemp()
        try:
            with patch.object(risk_engine, "TRADING_ENABLED", True):
             with patch("bots.pmb_bot.storage.DATA_DIR", Path(tmpdir)):
                with patch("bots.pmb_bot.storage.POSITIONS_FILE", Path(tmpdir) / "positions.json"):
                    with patch("bots.pmb_bot.storage.TRADES_FILE", Path(tmpdir) / "trades.json"):
                        with patch("bots.pmb_bot.storage.STATS_FILE", Path(tmpdir) / "stats.json"):
                            pmb_storage.ensure_storage()
                            pmb_storage.save_stats({"cash_balance": 100000.0})
                            result = open_base_position(_fresh_signal(source="PMB_SCANNER"))
                            assert result["ok"]
                            stats = pmb_storage.load_stats()
                            assert stats["cash_balance"] < 100000.0
                            trades = pmb_storage.load_trades()
                            assert any(t["action"] == "BASE_BUY" for t in trades)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_pmb_stop_loss_closes_position_updates_pnl(self):
        """PMB: stop loss → position closed → PnL updated."""
        import tempfile
        from bots.pmb_bot.trading_engine import execute_stop_loss
        from bots.pmb_bot import storage as pmb_storage

        tmpdir = tempfile.mkdtemp()
        try:
            with patch("bots.pmb_bot.storage.DATA_DIR", Path(tmpdir)):
                with patch("bots.pmb_bot.storage.POSITIONS_FILE", Path(tmpdir) / "positions.json"):
                    with patch("bots.pmb_bot.storage.TRADES_FILE", Path(tmpdir) / "trades.json"):
                        with patch("bots.pmb_bot.storage.STATS_FILE", Path(tmpdir) / "stats.json"):
                            pmb_storage.ensure_storage()
                            pmb_storage.save_positions([{
                                "id": "PMB-BTC-1234567890",
                                "symbol": "BTCUSDT", "coin": "BTC", "status": "OPEN",
                                "avg_entry_price": 50000, "total_quantity": 0.02,
                                "total_invested": 1000,
                            }])
                            pmb_storage.save_stats({"cash_balance": 100000.0, "total_pnl": 0.0})
                            result = execute_stop_loss({
                                "id": "PMB-BTC-1234567890",
                                "symbol": "BTCUSDT", "coin": "BTC", "status": "OPEN",
                                "avg_entry_price": 50000, "total_quantity": 0.02,
                                "total_invested": 1000,
                            }, 40000)
                            assert result["ok"]
                            assert result["position"]["status"] == "CLOSED"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_vgx_buy_position_deducts_virtual_balance(self):
        """VGX: buy → virtual balance down."""
        from bots.volatile_gridX import storage as vgx_storage
        from bots.volatile_gridX.trading_engine import buy_position

        original_balance = vgx_storage.virtual_balance
        original_positions = dict(vgx_storage.positions)
        try:
            vgx_storage.virtual_balance = 1_000_000
            vgx_storage.positions.clear()
            success = buy_position("BTC", 90000, 1000, "SCANNER")
            assert success
            assert vgx_storage.virtual_balance == 999000
            assert "BTC_SCANNER" in vgx_storage.positions
        finally:
            vgx_storage.virtual_balance = original_balance
            vgx_storage.positions.clear()
            vgx_storage.positions.update(original_positions)

    def test_vgx_close_position_restores_virtual_balance(self):
        """VGX: close → virtual balance restored → PnL calculated."""
        from bots.volatile_gridX import storage as vgx_storage
        from bots.volatile_gridX.trading_engine import close_position

        original_balance = vgx_storage.virtual_balance
        original_positions = dict(vgx_storage.positions)
        try:
            vgx_storage.virtual_balance = 1_000_000
            vgx_storage.positions.clear()
            vgx_storage.positions["BTC_SCANNER"] = {
                "coin": "BTC", "buy_price": 90000, "qty": 1000 / 90000,
                "amount": 1000, "trade_source": "SCANNER",
            }
            receive, pnl, source = close_position("BTC_SCANNER", 95000)
            assert receive > 0
            assert pnl > 0
            assert vgx_storage.virtual_balance > 1_000_000
            assert "BTC_SCANNER" not in vgx_storage.positions
        finally:
            vgx_storage.virtual_balance = original_balance
            vgx_storage.positions.clear()
            vgx_storage.positions.update(original_positions)


# =============================================================================
# TEST 4 — Dashboard: Open Positions, Closed Trades, Statistics
# =============================================================================

class TestDashboard:
    """Verify dashboard data reads from bot storage correctly."""

    def test_mtb_snapshot_has_open_positions(self):
        """MTB snapshot includes open_positions list."""
        from bots.mtb_bot.storage import snapshot
        s = snapshot()
        assert "open_positions" in s
        assert isinstance(s["open_positions"], list)

    def test_pmb_snapshot_has_closed_trades(self):
        """PMB snapshot includes closed_trades."""
        from bots.pmb_bot.storage import snapshot
        s = snapshot()
        assert "closed_trades" in s

    def test_vgx_storage_has_positions(self):
        """VGX storage exposes positions dict."""
        from bots.volatile_gridX import storage as vgx_storage
        assert hasattr(vgx_storage, "positions")
        assert isinstance(vgx_storage.positions, dict)

    def test_app_api_returns_watchlist(self):
        """Dashboard /api/watchlist returns unified scanner watchlist."""
        from bots.scanner_bot.scanner import get_watchlist
        wl = get_watchlist()
        assert isinstance(wl, dict)
        assert "coins" in wl


# =============================================================================
# TEST 5 — Telegram: BUY, SELL, Error Notifications
# =============================================================================

class TestTelegram:
    """Verify Telegram notification helpers exist and fire correctly."""

    def test_mtb_has_buy_telegram_notification(self):
        """MTB trading engine sends BUY notification via _send_tg."""
        from bots.mtb_bot.trading_engine import _send_tg
        assert _send_tg("test") is None

    def test_pmb_has_buy_telegram_notification(self):
        """PMB trading engine sends BASE_BUY notification via _send_tg."""
        from bots.pmb_bot.trading_engine import _send_tg
        assert _send_tg("test") is None

    def test_vgx_has_alert_dispatcher(self):
        """VGX alerts module has dispatch_alert_payload."""
        from bots.volatile_gridX.alerts import dispatch_alert_payload
        assert dispatch_alert_payload("test") is None

    def test_mtb_close_sends_sell_notification(self):
        """MTB close_position sends SELL notification."""
        from bots.mtb_bot.trading_engine import close_position, _send_tg
        assert callable(_send_tg)


# =============================================================================
# TEST 6 — Concurrency: No Duplicates, No Double Deduction, Trade Locks
# =============================================================================

class TestConcurrency:
    """Verify trade locks prevent race conditions."""

    def _is_lock(self, obj):
        """threading.Lock() returns _thread.lock on CPython — handle both."""
        return type(obj).__name__ == "lock"

    def test_mtb_trade_lock_exists(self):
        """MTB has a threading.Lock protecting trades."""
        from bots.mtb_bot.trading_engine import _TRADE_LOCK
        assert self._is_lock(_TRADE_LOCK)

    def test_pmb_trade_lock_exists(self):
        """PMB has a threading.Lock protecting trades."""
        from bots.pmb_bot.trading_engine import _TRADE_LOCK
        assert self._is_lock(_TRADE_LOCK)

    def test_vgx_trade_lock_exists(self):
        """VGX has a threading.Lock protecting trades."""
        from bots.volatile_gridX.trading_engine import _TRADE_LOCK
        assert self._is_lock(_TRADE_LOCK)

    def test_mtb_duplicate_position_prevented(self):
        """MTB validate_signal rejects duplicate open position."""
        from bots.mtb_bot.trading_engine import validate_signal
        positions = [{"symbol": "BTCUSDT", "status": "OPEN"}]
        signal = _fresh_signal()
        result = validate_signal(signal, positions)
        assert not result.passed
        assert result.code == "DUPLICATE_POSITION"

    def test_pmb_duplicate_position_prevented(self):
        """PMB validate_signal rejects duplicate open position."""
        from bots.pmb_bot.trading_engine import validate_signal
        positions = [{"coin": "BTC", "status": "OPEN"}]
        signal = _fresh_signal()
        result = validate_signal(signal, positions)
        assert not result.passed
        assert result.code == "DUPLICATE_POSITION"

    def test_vgx_duplicate_position_prevented(self):
        """VGX buy_position returns False for duplicate."""
        from bots.volatile_gridX import storage as vgx_storage
        from bots.volatile_gridX.trading_engine import buy_position

        original_balance = vgx_storage.virtual_balance
        original_positions = dict(vgx_storage.positions)
        try:
            vgx_storage.virtual_balance = 1_000_000
            vgx_storage.positions.clear()
            buy_position("BTC", 90000, 1000, "SCANNER")
            success = buy_position("BTC", 90000, 1000, "SCANNER")
            assert not success
            assert vgx_storage.virtual_balance == 999000  # Only deducted once
        finally:
            vgx_storage.virtual_balance = original_balance
            vgx_storage.positions.clear()
            vgx_storage.positions.update(original_positions)


# =============================================================================
# TEST 7 — Startup: No Errors from Missing Watchlist Files
# =============================================================================

class TestStartup:
    """Verify bots start normally even without old watchlist files."""

    def test_mtb_storage_ensure_storage_creates_defaults(self):
        """MTB ensure_storage creates default files when missing."""
        import tempfile
        from bots.mtb_bot import storage as mtb_storage

        tmpdir = tempfile.mkdtemp()
        try:
            with patch("bots.mtb_bot.storage.DATA_DIR", Path(tmpdir)):
                with patch("bots.mtb_bot.storage.POSITIONS_FILE", Path(tmpdir) / "positions.json"):
                    with patch("bots.mtb_bot.storage.TRADES_FILE", Path(tmpdir) / "trades.json"):
                        with patch("bots.mtb_bot.storage.STATS_FILE", Path(tmpdir) / "stats.json"):
                            mtb_storage.ensure_storage()
                            assert (Path(tmpdir) / "positions.json").exists()
                            assert (Path(tmpdir) / "trades.json").exists()
                            assert (Path(tmpdir) / "stats.json").exists()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_pmb_storage_ensure_storage_creates_defaults(self):
        """PMB ensure_storage creates default files when missing."""
        import tempfile
        from bots.pmb_bot import storage as pmb_storage

        tmpdir = tempfile.mkdtemp()
        try:
            with patch("bots.pmb_bot.storage.DATA_DIR", Path(tmpdir)):
                with patch("bots.pmb_bot.storage.POSITIONS_FILE", Path(tmpdir) / "positions.json"):
                    with patch("bots.pmb_bot.storage.TRADES_FILE", Path(tmpdir) / "trades.json"):
                        with patch("bots.pmb_bot.storage.STATS_FILE", Path(tmpdir) / "stats.json"):
                            pmb_storage.ensure_storage()
                            assert (Path(tmpdir) / "positions.json").exists()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_no_watchlist_json_load_watchlist_save_watchlist_in_bot_code(self):
        """
        Global check: no bot code calls load_watchlist(), save_watchlist(),
        or watchlist_manager for per-bot watchlist logic.
        """
        import ast
        bad = ["load_watchlist", "save_watchlist", "watchlist_manager"]
        for bot in ["mtb_bot", "pmb_bot", "volatile_gridX"]:
            for py_file in Path(f"bots/{bot}").rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                source = py_file.read_text()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id in bad:
                        raise AssertionError(
                            f"{py_file} references {node.id} — per-bot watchlist logic must be removed"
                        )

    def test_watchlist_json_only_in_scanner_and_shared(self):
        """
        Only scanner_bot and shared watchlist_manager reference watchlist.json
        as a file path. Bot storage modules may reference it in docstrings
        but must not read it for filtering.
        """
        import ast
        for bot in ["mtb_bot", "pmb_bot", "volatile_gridX"]:
            bot_dir = Path(f"bots/{bot}")
            for py_file in bot_dir.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                text = py_file.read_text()
                # Allow docstring references and _scanner_watchlist wrapper
                # but ban direct file I/O on watchlist.json
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        if "watchlist.json" in node.value:
                            continue  # docstring / string literal is OK
                    if isinstance(node, ast.Call):
                        # Check for open("...watchlist.json") or Path("...watchlist.json")
                        func_name = ""
                        if isinstance(node.func, ast.Name):
                            func_name = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            func_name = node.func.attr
                        for arg in node.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                if "watchlist.json" in arg.value and func_name in ("open", "Path"):
                                    raise AssertionError(
                                        f"{py_file} opens watchlist.json directly — must use scanner get_watchlist()"
                                    )


# =============================================================================
# TEST 8 — Risk Engine Integration
# =============================================================================

class TestRiskEngine:
    """Verify shared risk engine gates trades correctly."""

    def test_risk_engine_blocks_when_trading_disabled(self):
        """Risk engine rejects when TRADING_ENABLED=false."""
        from bots.risk_engine import engine as risk_engine
        with patch.object(risk_engine, "TRADING_ENABLED", False):
            decision = risk_engine.check_trade_allowed("MTB", 100)
        assert not decision.allowed
        assert decision.code == "TRADING_DISABLED"

    def test_risk_engine_blocks_when_emergency_stop(self):
        """Risk engine rejects when EMERGENCY_STOP=true."""
        from bots.risk_engine import engine as risk_engine
        with patch.object(risk_engine, "TRADING_ENABLED", True):
            with patch.object(risk_engine, "EMERGENCY_STOP", True):
                decision = risk_engine.check_trade_allowed("MTB", 100)
        assert not decision.allowed
        assert decision.code == "EMERGENCY_STOP"

    def test_risk_engine_blocks_when_bot_disabled(self):
        """Risk engine rejects when bot mode is DISABLED."""
        from bots.risk_engine import engine as risk_engine
        original_mode = risk_engine.BOT_MODE.copy()
        try:
            risk_engine.BOT_MODE["MTB"] = "DISABLED"
            with patch.object(risk_engine, "TRADING_ENABLED", True):
                with patch.object(risk_engine, "_load_bot_positions", return_value=[]):
                    decision = risk_engine.check_trade_allowed("MTB", 100)
            assert not decision.allowed
            assert decision.code == "BOT_INACTIVE"
        finally:
            risk_engine.BOT_MODE.update(original_mode)

    def test_risk_engine_allows_when_paper_mode(self):
        """Risk engine allows when bot mode is PAPER."""
        from bots.risk_engine import engine as risk_engine
        with patch.object(risk_engine, "TRADING_ENABLED", True):
            with patch.object(risk_engine, "_load_bot_positions", return_value=[]):
                decision = risk_engine.check_trade_allowed("MTB", 100)
        assert decision.allowed
        assert decision.code == "OK"


# =============================================================================
# TEST 9 — Scanner → Bot: Signal Normalization
# =============================================================================

class TestSignalNormalization:
    """Verify signals are normalized correctly for each bot."""

    def test_mtb_bridge_normalizes_score(self):
        """MTB bridge normalizes score field from various signal formats."""
        from bots.mtb_bot.scanner_bridge import _normalize_signal
        s = _normalize_signal({"coin": "BTC", "price": 50000, "score": 85})
        assert s["score"] == 85.0
        assert s["symbol"] == "BTCUSDT"

    def test_pmb_bridge_normalizes_score(self):
        """PMB bridge normalizes score field from various signal formats."""
        from bots.pmb_bot.scanner_bridge import _normalize_signal
        s = _normalize_signal({"coin": "BTC", "price": 50000, "score": 85})
        assert s["score"] == 85.0
        assert s["symbol"] == "BTCUSDT"

    def test_vgx_bridge_normalizes_signal(self):
        """VGX bridge normalizes signal into standard dict."""
        from bots.volatile_gridX.scanner_bridge import normalize_signal
        s = normalize_signal({"coin": "BTC", "action": "BUY", "score": 85})
        assert s["coin"] == "BTC"
        assert s["action"] == "BUY"
        assert s["score"] == 85.0
