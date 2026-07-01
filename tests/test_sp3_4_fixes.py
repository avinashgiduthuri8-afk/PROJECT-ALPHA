"""
SP3.4 regression tests.

BUG-46: status_cmd() watchlist label changed from "Watchlist: X coins"
         to "Scanner Coins: X".
BUG-45: MTB Telegram bot never started — startup_event/shutdown_event
         added and wired into app.py lifespan.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_update() -> tuple:
    replies: list[str] = []

    async def _reply(text, **kwargs):
        replies.append(text)

    update = MagicMock()
    update.message.reply_text = AsyncMock(side_effect=_reply)
    return update, replies


def _fake_snapshot(watchlist_size: int = 4) -> dict:
    return {
        "status":        "ONLINE",
        "open_positions": [],
        "closed_trades":  [],
        "daily_pnl":      0.0,
        "total_pnl":      0.0,
        "cash_balance":   10_000.0,
        "trade_amount":   500.0,
        "watchlist":      ["BTC", "ETH", "SOL", "BNB"][:watchlist_size],
        "last_updated":   "2026-06-30 18:00:00",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleImport:

    def test_import_succeeds_without_error(self):
        """Importing mtb_telegram_bot must not raise any ImportError."""
        import bots.mtb_bot.mtb_telegram_bot  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# BUG-46 — status_cmd label fix
# ─────────────────────────────────────────────────────────────────────────────

class TestBug46StatusLabel:

    def test_uses_scanner_coins_label(self):
        """status_cmd reply must contain 'Scanner Coins', not 'Watchlist'."""
        from bots.mtb_bot.mtb_telegram_bot import status_cmd

        update, replies = _make_update()
        with patch("bots.mtb_bot.mtb_telegram_bot.storage") as mock_storage:
            mock_storage.snapshot.return_value = _fake_snapshot(3)
            _run(status_cmd(update, None))

        assert replies, "status_cmd sent no reply"
        msg = replies[0]
        assert "Scanner Coins" in msg, (
            f"'Scanner Coins' label not found in reply: {msg}"
        )

    def test_old_watchlist_label_gone(self):
        """The old 'Watchlist:' label must not appear in the reply."""
        from bots.mtb_bot.mtb_telegram_bot import status_cmd

        update, replies = _make_update()
        with patch("bots.mtb_bot.mtb_telegram_bot.storage") as mock_storage:
            mock_storage.snapshot.return_value = _fake_snapshot(4)
            _run(status_cmd(update, None))

        assert "Watchlist:" not in replies[0], (
            f"Old 'Watchlist:' label still present: {replies[0]}"
        )

    def test_shows_correct_count(self):
        """Scanner Coins count must match len(watchlist) from snapshot."""
        from bots.mtb_bot.mtb_telegram_bot import status_cmd

        update, replies = _make_update()
        with patch("bots.mtb_bot.mtb_telegram_bot.storage") as mock_storage:
            mock_storage.snapshot.return_value = _fake_snapshot(4)
            _run(status_cmd(update, None))

        assert "Scanner Coins: `4`" in replies[0], (
            f"Expected 'Scanner Coins: `4`' in reply: {replies[0]}"
        )

    def test_label_in_source(self):
        """Source of status_cmd must use new label, not old one."""
        import inspect
        import bots.mtb_bot.mtb_telegram_bot as tg
        src = inspect.getsource(tg.status_cmd)
        assert "Scanner Coins" in src
        assert "Watchlist: `{len(watchlist)} coins`" not in src


# ─────────────────────────────────────────────────────────────────────────────
# BUG-45 — startup_event / shutdown_event lifespan hooks
# ─────────────────────────────────────────────────────────────────────────────

class TestBug45LifespanHooks:

    def test_startup_does_nothing_when_no_token(self):
        """startup_event must not raise and must leave _MTB_TG_APP as None."""
        import bots.mtb_bot.mtb_telegram_bot as tg

        original = tg._MTB_TG_APP
        try:
            with patch("bots.mtb_bot.mtb_telegram_bot.create_mtb_bot",
                       return_value=None):
                _run(tg.startup_event())
            assert tg._MTB_TG_APP is None
        finally:
            tg._MTB_TG_APP = original

    def test_startup_sets_mtb_tg_app_when_token_present(self):
        """startup_event must call initialize(), start(), start_polling() and set _MTB_TG_APP."""
        import bots.mtb_bot.mtb_telegram_bot as tg

        original = tg._MTB_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.start_polling = AsyncMock()

            fake_app = MagicMock()
            fake_app.initialize = AsyncMock()
            fake_app.start      = AsyncMock()
            fake_app.updater    = fake_updater

            with patch("bots.mtb_bot.mtb_telegram_bot.create_mtb_bot",
                       return_value=fake_app):
                _run(tg.startup_event())

            fake_app.initialize.assert_awaited_once()
            fake_app.start.assert_awaited_once()
            fake_updater.start_polling.assert_awaited_once()
            assert tg._MTB_TG_APP is fake_app
        finally:
            tg._MTB_TG_APP = original

    def test_shutdown_safe_when_no_app(self):
        """shutdown_event must not raise when _MTB_TG_APP is None."""
        import bots.mtb_bot.mtb_telegram_bot as tg

        original = tg._MTB_TG_APP
        try:
            tg._MTB_TG_APP = None
            _run(tg.shutdown_event())  # must not raise
        finally:
            tg._MTB_TG_APP = original

    def test_shutdown_stops_app_and_clears_reference(self):
        """shutdown_event must call updater.stop(), stop(), shutdown() and set _MTB_TG_APP = None."""
        import bots.mtb_bot.mtb_telegram_bot as tg

        original = tg._MTB_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.stop = AsyncMock()

            fake_app = MagicMock()
            fake_app.stop     = AsyncMock()
            fake_app.shutdown = AsyncMock()
            fake_app.updater  = fake_updater

            tg._MTB_TG_APP = fake_app
            _run(tg.shutdown_event())

            fake_updater.stop.assert_awaited_once()
            fake_app.stop.assert_awaited_once()
            fake_app.shutdown.assert_awaited_once()
            assert tg._MTB_TG_APP is None, "_MTB_TG_APP not cleared after shutdown"
        finally:
            tg._MTB_TG_APP = original

    def test_app_py_wires_mtb_tg_into_lifespan(self):
        """app.py lifespan must call mtb_tg.startup_event and mtb_tg.shutdown_event."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app._app_lifespan)
        assert "mtb_tg.startup_event"  in src, "mtb_tg.startup_event not found in lifespan"
        assert "mtb_tg.shutdown_event" in src, "mtb_tg.shutdown_event not found in lifespan"

    def test_mtb_telegram_bot_status_is_dynamic(self):
        """app.py service_statuses must include a live mtb_telegram_bot check."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app.pull_state_payload)
        assert "mtb_tg._MTB_TG_APP" in src, (
            "mtb_telegram_bot status missing or not using _MTB_TG_APP check"
        )
