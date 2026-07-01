"""
SP3.3 regression tests.

BUG-44: status_cmd() watchlist label changed from "Watchlist: X coins"
         to "Scanner Coins: X".
BUG-43: PMB Telegram bot never started — startup_event/shutdown_event
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


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — module must import cleanly
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleImport:

    def test_import_succeeds_without_error(self):
        """Importing pmb_telegram_bot must not raise any ImportError."""
        import bots.pmb_bot.pmb_telegram_bot  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# BUG-44 — status_cmd label fix
# ─────────────────────────────────────────────────────────────────────────────

class TestBug44StatusLabel:

    def _fake_snapshot(self, watchlist_size: int = 5) -> dict:
        return {
            "status": "ONLINE",
            "open_positions": [],
            "closed_trades": [],
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
            "cash_balance": 10_000.0,
            "watchlist": ["BTC", "ETH", "SOL", "BNB", "ADA"][:watchlist_size],
            "last_updated": "2026-06-30 18:00:00",
        }

    def test_status_cmd_uses_scanner_coins_label(self):
        """status_cmd reply must contain 'Scanner Coins', not 'Watchlist'."""
        from bots.pmb_bot.pmb_telegram_bot import status_cmd

        update, replies = _make_update()
        with patch("bots.pmb_bot.pmb_telegram_bot.storage") as mock_storage:
            mock_storage.snapshot.return_value = self._fake_snapshot(3)
            _run(status_cmd(update, None))

        assert replies, "status_cmd sent no reply"
        msg = replies[0]
        assert "Scanner Coins" in msg, (
            f"'Scanner Coins' label not found in reply: {msg}"
        )

    def test_status_cmd_old_watchlist_label_gone(self):
        """The old 'Watchlist:' label must not appear in the reply."""
        from bots.pmb_bot.pmb_telegram_bot import status_cmd

        update, replies = _make_update()
        with patch("bots.pmb_bot.pmb_telegram_bot.storage") as mock_storage:
            mock_storage.snapshot.return_value = self._fake_snapshot(4)
            _run(status_cmd(update, None))

        msg = replies[0]
        assert "Watchlist:" not in msg, (
            f"Old 'Watchlist:' label still present in reply: {msg}"
        )

    def test_status_cmd_shows_correct_count(self):
        """Scanner Coins count must reflect len(watchlist) from snapshot."""
        from bots.pmb_bot.pmb_telegram_bot import status_cmd

        update, replies = _make_update()
        with patch("bots.pmb_bot.pmb_telegram_bot.storage") as mock_storage:
            mock_storage.snapshot.return_value = self._fake_snapshot(5)
            _run(status_cmd(update, None))

        msg = replies[0]
        assert "Scanner Coins: `5`" in msg, (
            f"Expected 'Scanner Coins: `5`' in reply: {msg}"
        )

    def test_label_in_source_not_old_string(self):
        """Source code must contain new label and not the old one."""
        import inspect
        import bots.pmb_bot.pmb_telegram_bot as tg
        src = inspect.getsource(tg.status_cmd)
        assert "Scanner Coins" in src, "New label missing from source"
        assert "Watchlist: `{len(watchlist)} coins`" not in src, (
            "Old label still present in source"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-43 — startup_event / shutdown_event lifespan hooks
# ─────────────────────────────────────────────────────────────────────────────

class TestBug43LifespanHooks:

    def test_startup_does_nothing_when_no_token(self):
        """startup_event must not raise and must leave _PMB_TG_APP as None."""
        import bots.pmb_bot.pmb_telegram_bot as tg

        original = tg._PMB_TG_APP
        try:
            with patch("bots.pmb_bot.pmb_telegram_bot.create_pmb_bot",
                       return_value=None):
                _run(tg.startup_event())
            assert tg._PMB_TG_APP is None
        finally:
            tg._PMB_TG_APP = original

    def test_startup_sets_pmb_tg_app_when_token_present(self):
        """startup_event must call initialize(), start(), start_polling() and set _PMB_TG_APP."""
        import bots.pmb_bot.pmb_telegram_bot as tg

        original = tg._PMB_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.start_polling = AsyncMock()

            fake_app = MagicMock()
            fake_app.initialize = AsyncMock()
            fake_app.start      = AsyncMock()
            fake_app.updater    = fake_updater

            with patch("bots.pmb_bot.pmb_telegram_bot.create_pmb_bot",
                       return_value=fake_app):
                _run(tg.startup_event())

            fake_app.initialize.assert_awaited_once()
            fake_app.start.assert_awaited_once()
            fake_updater.start_polling.assert_awaited_once()
            assert tg._PMB_TG_APP is fake_app
        finally:
            tg._PMB_TG_APP = original

    def test_shutdown_safe_when_no_app(self):
        """shutdown_event must not raise when _PMB_TG_APP is None."""
        import bots.pmb_bot.pmb_telegram_bot as tg

        original = tg._PMB_TG_APP
        try:
            tg._PMB_TG_APP = None
            _run(tg.shutdown_event())  # must not raise
        finally:
            tg._PMB_TG_APP = original

    def test_shutdown_stops_app_and_clears_reference(self):
        """shutdown_event must call updater.stop(), stop(), shutdown() and set _PMB_TG_APP = None."""
        import bots.pmb_bot.pmb_telegram_bot as tg

        original = tg._PMB_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.stop = AsyncMock()

            fake_app = MagicMock()
            fake_app.stop     = AsyncMock()
            fake_app.shutdown = AsyncMock()
            fake_app.updater  = fake_updater

            tg._PMB_TG_APP = fake_app
            _run(tg.shutdown_event())

            fake_updater.stop.assert_awaited_once()
            fake_app.stop.assert_awaited_once()
            fake_app.shutdown.assert_awaited_once()
            assert tg._PMB_TG_APP is None, "_PMB_TG_APP not cleared after shutdown"
        finally:
            tg._PMB_TG_APP = original

    def test_app_py_wires_pmb_tg_into_lifespan(self):
        """app.py lifespan must call pmb_tg.startup_event and pmb_tg.shutdown_event."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app._app_lifespan)
        assert "pmb_tg.startup_event"  in src, "pmb_tg.startup_event not found in lifespan"
        assert "pmb_tg.shutdown_event" in src, "pmb_tg.shutdown_event not found in lifespan"

    def test_pmb_telegram_bot_status_is_dynamic(self):
        """app.py service_statuses must include a real pmb_telegram_bot check."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app.pull_state_payload)
        assert "_PMB_TG_APP" in src, (
            "pmb_telegram_bot status missing or not using _PMB_TG_APP check"
        )
