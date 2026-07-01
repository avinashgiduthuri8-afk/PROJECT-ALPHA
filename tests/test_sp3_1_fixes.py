"""
SP3.1 regression tests.

BUG-37: status_cmd / signals_cmd unwrap {"signals": [...]} correctly.
BUG-38: refresh_cmd uses already-imported scanner functions (no scanner_main).
BUG-39: startup_event / shutdown_event wire scanner Telegram bot into lifespan.
BUG-40: health_cmd uses elite_signals / high_signals / medium_signals keys.
"""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_update(captured: list | None = None) -> MagicMock:
    """Return a fake Telegram Update whose reply_text is an AsyncMock."""
    update = MagicMock()
    replies = captured if captured is not None else []

    async def _reply(text, **kwargs):
        replies.append(text)

    update.message.reply_text = AsyncMock(side_effect=_reply)
    return update, replies


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-37 — status_cmd: unwrap {"signals": [...]}
# ─────────────────────────────────────────────────────────────────────────────

class TestBug37StatusCmd:

    def test_total_signals_and_live_count_reflect_wrapped_list(self):
        """status_cmd must report len of the inner list, not 1 (the dict itself)."""
        from bots.scanner_bot.telegram_bot import status_cmd

        fake_signals = {"signals": [{"coin": "BTC"}, {"coin": "ETH"}]}
        fake_live    = {"signals": [{"coin": "SOL"}]}
        fake_wl      = {"coins": ["BTC", "ETH", "SOL"]}
        fake_stats   = {"last_scan_time": "2026-06-30", "total_scans": 5}

        update, replies = _make_update()

        with (
            patch("bots.scanner_bot.telegram_bot.get_signals",      return_value=fake_signals),
            patch("bots.scanner_bot.telegram_bot.get_live_signals",  return_value=fake_live),
            patch("bots.scanner_bot.telegram_bot.get_watchlist",     return_value=fake_wl),
            patch("bots.scanner_bot.telegram_bot.get_stats",         return_value=fake_stats),
        ):
            _run(status_cmd(update, None))

        assert replies, "No reply sent by status_cmd"
        msg = replies[0]
        assert "Active Signals: `2`" in msg, f"Expected 2 signals in reply, got: {msg}"
        assert "Live Signals*: `1`"  in msg, f"Expected 1 live signal in reply, got: {msg}"

    def test_status_cmd_does_not_raise_on_empty_signals(self):
        """Empty {"signals": []} must not crash status_cmd."""
        from bots.scanner_bot.telegram_bot import status_cmd

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signals",      return_value={"signals": []}),
            patch("bots.scanner_bot.telegram_bot.get_live_signals",  return_value={"signals": []}),
            patch("bots.scanner_bot.telegram_bot.get_watchlist",     return_value={"coins": []}),
            patch("bots.scanner_bot.telegram_bot.get_stats",         return_value={}),
        ):
            _run(status_cmd(update, None))

        assert replies
        assert "Active Signals: `0`" in replies[0]


# ─────────────────────────────────────────────────────────────────────────────
# BUG-37 — signals_cmd: unwrap {"signals": [...]}
# ─────────────────────────────────────────────────────────────────────────────

class TestBug37SignalsCmd:

    def test_signals_cmd_formats_list_from_wrapped_dict(self):
        """signals_cmd must display coin names from the inner list."""
        from bots.scanner_bot.telegram_bot import signals_cmd

        fake_signals = {"signals": [
            {"coin": "BTC", "score": 95, "tier": "ELITE",  "action": "BUY"},
            {"coin": "ETH", "score": 80, "tier": "HIGH",   "action": "BUY"},
        ]}

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signals",     return_value=fake_signals),
            patch("bots.scanner_bot.telegram_bot.get_live_signals", return_value={"signals": []}),
        ):
            _run(signals_cmd(update, None))

        assert replies, "No reply from signals_cmd"
        msg = replies[0]
        assert "BTC" in msg, f"BTC missing from signals reply: {msg}"
        assert "ETH" in msg, f"ETH missing from signals reply: {msg}"

    def test_signals_cmd_shows_no_signals_message_when_both_empty(self):
        """Both empty lists → 'No active signals' reply, no crash."""
        from bots.scanner_bot.telegram_bot import signals_cmd

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signals",     return_value={"signals": []}),
            patch("bots.scanner_bot.telegram_bot.get_live_signals", return_value={"signals": []}),
        ):
            _run(signals_cmd(update, None))

        assert replies
        assert "No active signals" in replies[0]

    def test_signals_cmd_dedupes_by_coin(self):
        """Same coin in both signals and live_signals → appears only once."""
        from bots.scanner_bot.telegram_bot import signals_cmd

        sig  = {"coin": "BTC", "score": 90, "tier": "ELITE", "action": "BUY"}
        live = {"coin": "BTC", "score": 92, "tier": "ELITE", "action": "BUY"}

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signals",     return_value={"signals": [sig]}),
            patch("bots.scanner_bot.telegram_bot.get_live_signals", return_value={"signals": [live]}),
        ):
            _run(signals_cmd(update, None))

        msg = replies[0]
        assert msg.count("BTC") == 1, f"BTC appeared more than once: {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-40 — health_cmd: elite_signals / high_signals / medium_signals keys
# ─────────────────────────────────────────────────────────────────────────────

class TestBug40HealthCmd:

    def test_health_cmd_reads_correct_signal_stat_keys(self):
        """health_cmd must display counts from elite_signals/high_signals/medium_signals."""
        from bots.scanner_bot.telegram_bot import health_cmd

        fake_signal_stats = {
            "elite_signals":  7,
            "high_signals":   12,
            "medium_signals": 4,
        }
        fake_stats = {"total_scans": 100, "successful_scans": 95, "failed_scans": 5}

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signal_stats", return_value=fake_signal_stats),
            patch("bots.scanner_bot.telegram_bot.get_stats",         return_value=fake_stats),
            patch("bots.scanner_bot.telegram_bot.get_market_state",  return_value={}),
        ):
            _run(health_cmd(update, None))

        assert replies, "No reply from health_cmd"
        msg = replies[0]
        assert "Elite: `7`"  in msg, f"Elite count wrong: {msg}"
        assert "High: `12`"  in msg, f"High count wrong: {msg}"
        assert "Medium: `4`" in msg, f"Medium count wrong: {msg}"

    def test_health_cmd_shows_zero_not_from_old_keys(self):
        """Old short keys (elite/high/medium) must not produce non-zero counts."""
        from bots.scanner_bot.telegram_bot import health_cmd

        # Provide only the OLD (wrong) keys — correct code must return 0 for all
        fake_signal_stats = {"elite": 99, "high": 99, "medium": 99}
        fake_stats = {"total_scans": 10}

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signal_stats", return_value=fake_signal_stats),
            patch("bots.scanner_bot.telegram_bot.get_stats",         return_value=fake_stats),
            patch("bots.scanner_bot.telegram_bot.get_market_state",  return_value={}),
        ):
            _run(health_cmd(update, None))

        msg = replies[0]
        assert "Elite: `0`"  in msg, f"Expected 0 for elite with old key, got: {msg}"
        assert "High: `0`"   in msg, f"Expected 0 for high with old key, got: {msg}"
        assert "Medium: `0`" in msg, f"Expected 0 for medium with old key, got: {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# BUG-38 — refresh_cmd: uses already-imported scanner functions
# ─────────────────────────────────────────────────────────────────────────────

class TestBug38RefreshCmd:

    def test_refresh_cmd_reports_correct_signal_count(self):
        """refresh_cmd must report len of the inner list, not crash on missing scanner_main."""
        from bots.scanner_bot.telegram_bot import refresh_cmd

        fake_signals = {"signals": [{"coin": "BTC"}, {"coin": "ETH"}, {"coin": "SOL"}]}

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signals", return_value=fake_signals),
            patch("bots.scanner_bot.telegram_bot.get_stats",   return_value={}),
        ):
            _run(refresh_cmd(update, None))

        full_reply = " ".join(replies)
        assert "Signals: `3`" in full_reply, f"Expected 3 signals in refresh reply: {full_reply}"

    def test_refresh_cmd_does_not_import_scanner_main(self):
        """refresh_cmd must not reach into scanner_main (those functions don't exist there)."""
        import bots.scanner_bot.telegram_bot as tg_mod
        import inspect
        src = inspect.getsource(tg_mod.refresh_cmd)
        assert "scanner_main" not in src, (
            "refresh_cmd still references scanner_main — BUG-38 fix incomplete"
        )

    def test_refresh_cmd_does_not_raise_on_empty(self):
        """Empty signal list → reply with 0, no exception."""
        from bots.scanner_bot.telegram_bot import refresh_cmd

        update, replies = _make_update()
        with (
            patch("bots.scanner_bot.telegram_bot.get_signals", return_value={"signals": []}),
            patch("bots.scanner_bot.telegram_bot.get_stats",   return_value={}),
        ):
            _run(refresh_cmd(update, None))

        full_reply = " ".join(replies)
        assert "Signals: `0`" in full_reply


# ─────────────────────────────────────────────────────────────────────────────
# BUG-39 — startup_event / shutdown_event
# ─────────────────────────────────────────────────────────────────────────────

class TestBug39LifespanHooks:

    def test_startup_does_nothing_when_no_token(self):
        """startup_event must not raise when SCANNER_BOT_TOKEN is unset."""
        import bots.scanner_bot.telegram_bot as tg_mod

        original_app = tg_mod._SCANNER_TG_APP
        try:
            with patch("bots.scanner_bot.telegram_bot.create_scanner_bot", return_value=None):
                _run(tg_mod.startup_event())
            # _SCANNER_TG_APP must remain None
            assert tg_mod._SCANNER_TG_APP is None
        finally:
            tg_mod._SCANNER_TG_APP = original_app

    def test_startup_initializes_and_starts_polling_when_token_present(self):
        """startup_event must call initialize(), start(), start_polling() on the app."""
        import bots.scanner_bot.telegram_bot as tg_mod

        original_app = tg_mod._SCANNER_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.start_polling = AsyncMock()

            fake_app = MagicMock()
            fake_app.initialize  = AsyncMock()
            fake_app.start       = AsyncMock()
            fake_app.updater     = fake_updater

            with patch("bots.scanner_bot.telegram_bot.create_scanner_bot", return_value=fake_app):
                _run(tg_mod.startup_event())

            fake_app.initialize.assert_awaited_once()
            fake_app.start.assert_awaited_once()
            fake_updater.start_polling.assert_awaited_once()
            # _SCANNER_TG_APP must be set to the running app
            assert tg_mod._SCANNER_TG_APP is fake_app
        finally:
            tg_mod._SCANNER_TG_APP = original_app

    def test_shutdown_is_safe_when_no_app_running(self):
        """shutdown_event must not raise when _SCANNER_TG_APP is None."""
        import bots.scanner_bot.telegram_bot as tg_mod

        original_app = tg_mod._SCANNER_TG_APP
        try:
            tg_mod._SCANNER_TG_APP = None
            _run(tg_mod.shutdown_event())  # must not raise
        finally:
            tg_mod._SCANNER_TG_APP = original_app

    def test_shutdown_stops_running_app(self):
        """shutdown_event must call updater.stop(), stop(), shutdown() on a running app."""
        import bots.scanner_bot.telegram_bot as tg_mod

        original_app = tg_mod._SCANNER_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.stop = AsyncMock()

            fake_app = MagicMock()
            fake_app.stop     = AsyncMock()
            fake_app.shutdown = AsyncMock()
            fake_app.updater  = fake_updater

            tg_mod._SCANNER_TG_APP = fake_app
            _run(tg_mod.shutdown_event())

            fake_updater.stop.assert_awaited_once()
            fake_app.stop.assert_awaited_once()
            fake_app.shutdown.assert_awaited_once()
        finally:
            tg_mod._SCANNER_TG_APP = original_app

    def test_app_py_wires_scanner_tg_into_lifespan(self):
        """app.py lifespan must call scanner_tg.startup_event and scanner_tg.shutdown_event."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app._app_lifespan)
        assert "scanner_tg.startup_event"  in src, "scanner_tg.startup_event not found in lifespan"
        assert "scanner_tg.shutdown_event" in src, "scanner_tg.shutdown_event not found in lifespan"

    def test_telegram_bot_status_is_dynamic(self):
        """app.py telegram_bot status must depend on _SCANNER_TG_APP, not be hardcoded 'ONLINE'."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app.pull_state_payload)
        assert "_SCANNER_TG_APP" in src, (
            "Hardcoded 'ONLINE' string not replaced with real _SCANNER_TG_APP check"
        )
