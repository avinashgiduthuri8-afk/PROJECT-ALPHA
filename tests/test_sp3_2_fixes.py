"""
SP3.2 regression tests.

BUG-41: vgx_telegram_bot.py hard ImportError — from .risk_engine import get_risk_status
         (function does not exist). Fix: use check_cooldown() / market_intelligence()
         via a local _get_risk_status() helper.
BUG-42: VGX Telegram bot never started — startup_event/shutdown_event added and
         wired into app.py lifespan.
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
# BUG-41 — import no longer crashes; _get_risk_status returns correct shape
# ─────────────────────────────────────────────────────────────────────────────

class TestBug41ImportFixed:

    def test_module_imports_without_error(self):
        """Importing vgx_telegram_bot must not raise ImportError."""
        import bots.volatile_gridX.vgx_telegram_bot  # must not raise

    def test_get_risk_status_returns_required_keys(self):
        """_get_risk_status() must return market_regime, trading_allowed, cooldown."""
        from bots.volatile_gridX.vgx_telegram_bot import _get_risk_status

        with (
            patch("bots.volatile_gridX.vgx_telegram_bot.check_cooldown",
                  return_value=(False, "OK")),
            patch("bots.volatile_gridX.vgx_telegram_bot.market_intelligence",
                  return_value={"regime": "BULL", "score": 85}),
        ):
            result = _get_risk_status()

        assert "market_regime"   in result
        assert "trading_allowed" in result
        assert "cooldown"        in result
        assert "active"      in result["cooldown"]
        assert "loss_streak" in result["cooldown"]

    def test_get_risk_status_reflects_bull_market(self):
        """market_regime comes from market_intelligence()['regime']."""
        from bots.volatile_gridX.vgx_telegram_bot import _get_risk_status

        with (
            patch("bots.volatile_gridX.vgx_telegram_bot.check_cooldown",
                  return_value=(False, "OK")),
            patch("bots.volatile_gridX.vgx_telegram_bot.market_intelligence",
                  return_value={"regime": "BULL", "score": 85}),
        ):
            result = _get_risk_status()

        assert result["market_regime"] == "BULL"
        assert result["trading_allowed"] is True
        assert result["cooldown"]["active"] is False

    def test_get_risk_status_reflects_active_cooldown(self):
        """cooldown_active comes from check_cooldown()[0]."""
        from bots.volatile_gridX.vgx_telegram_bot import _get_risk_status
        import bots.volatile_gridX.risk_engine as re_mod

        original_streak = re_mod.loss_streak
        re_mod.loss_streak = 3
        try:
            with (
                patch("bots.volatile_gridX.vgx_telegram_bot.check_cooldown",
                      return_value=(True, "Cooldown Active (120s)")),
                patch("bots.volatile_gridX.vgx_telegram_bot.market_intelligence",
                      return_value={"regime": "BEAR", "score": 40}),
            ):
                result = _get_risk_status()
        finally:
            re_mod.loss_streak = original_streak

        assert result["trading_allowed"] is False
        assert result["cooldown"]["active"] is True
        assert result["cooldown"]["loss_streak"] == 3
        assert result["market_regime"] == "BEAR"


class TestBug41SafetyCmd:

    def test_safety_cmd_does_not_raise(self):
        """safety_cmd() must complete without raising; reply contains Safety Systems."""
        from bots.volatile_gridX.vgx_telegram_bot import safety_cmd

        update, replies = _make_update()
        with (
            patch("bots.volatile_gridX.vgx_telegram_bot._get_risk_status",
                  return_value={
                      "market_regime": "BULL",
                      "trading_allowed": True,
                      "cooldown": {"active": False, "loss_streak": 0},
                  }),
            patch("bots.volatile_gridX.vgx_telegram_bot.get_breaker_status",
                  return_value={
                      "trading_state": "ACTIVE",
                      "can_trade": True,
                      "daily_pnl_pct": 0.5,
                      "weekly_pnl_pct": 1.2,
                      "drawdown_pct": 0.3,
                      "total_trades_blocked": 0,
                      "daily_pnl": 50.0,
                  }),
        ):
            _run(safety_cmd(update, None))

        assert replies, "safety_cmd sent no reply"
        assert "Safety Systems" in replies[0]

    def test_safety_cmd_shows_market_regime(self):
        """Market regime from _get_risk_status must appear in the reply."""
        from bots.volatile_gridX.vgx_telegram_bot import safety_cmd

        update, replies = _make_update()
        with (
            patch("bots.volatile_gridX.vgx_telegram_bot._get_risk_status",
                  return_value={
                      "market_regime": "SIDEWAYS",
                      "trading_allowed": True,
                      "cooldown": {"active": False, "loss_streak": 0},
                  }),
            patch("bots.volatile_gridX.vgx_telegram_bot.get_breaker_status",
                  return_value={"trading_state": "ACTIVE", "can_trade": True,
                                "daily_pnl_pct": 0, "weekly_pnl_pct": 0,
                                "drawdown_pct": 0, "total_trades_blocked": 0,
                                "daily_pnl": 0}),
        ):
            _run(safety_cmd(update, None))

        assert "SIDEWAYS" in replies[0]

    def test_old_get_risk_status_name_gone_from_source(self):
        """The broken 'get_risk_status' name must not appear in the module source."""
        import inspect
        import bots.volatile_gridX.vgx_telegram_bot as tg
        src = inspect.getsource(tg)
        # 'get_risk_status' must only appear as the helper name _get_risk_status
        # (which contains the substring but is a different identifier)
        assert "from .risk_engine import get_risk_status" not in src, (
            "Broken import line still present"
        )
        # Confirm the replacement functions are imported
        assert "check_cooldown" in src
        assert "market_intelligence" in src


# ─────────────────────────────────────────────────────────────────────────────
# BUG-42 — startup_event / shutdown_event lifespan hooks
# ─────────────────────────────────────────────────────────────────────────────

class TestBug42LifespanHooks:

    def test_startup_does_nothing_when_no_token(self):
        """startup_event must not raise when VGX_BOT_TOKEN is unset."""
        import bots.volatile_gridX.vgx_telegram_bot as tg

        original = tg._VGX_TG_APP
        try:
            with patch("bots.volatile_gridX.vgx_telegram_bot.create_vgx_bot",
                       return_value=None):
                _run(tg.startup_event())
            assert tg._VGX_TG_APP is None
        finally:
            tg._VGX_TG_APP = original

    def test_startup_initializes_and_starts_polling(self):
        """startup_event must call initialize(), start(), start_polling()."""
        import bots.volatile_gridX.vgx_telegram_bot as tg

        original = tg._VGX_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.start_polling = AsyncMock()

            fake_app = MagicMock()
            fake_app.initialize = AsyncMock()
            fake_app.start      = AsyncMock()
            fake_app.updater    = fake_updater

            with patch("bots.volatile_gridX.vgx_telegram_bot.create_vgx_bot",
                       return_value=fake_app):
                _run(tg.startup_event())

            fake_app.initialize.assert_awaited_once()
            fake_app.start.assert_awaited_once()
            fake_updater.start_polling.assert_awaited_once()
            assert tg._VGX_TG_APP is fake_app
        finally:
            tg._VGX_TG_APP = original

    def test_shutdown_safe_when_no_app(self):
        """shutdown_event must not raise when _VGX_TG_APP is None."""
        import bots.volatile_gridX.vgx_telegram_bot as tg

        original = tg._VGX_TG_APP
        try:
            tg._VGX_TG_APP = None
            _run(tg.shutdown_event())  # must not raise
        finally:
            tg._VGX_TG_APP = original

    def test_shutdown_stops_running_app(self):
        """shutdown_event must call updater.stop(), stop(), shutdown()."""
        import bots.volatile_gridX.vgx_telegram_bot as tg

        original = tg._VGX_TG_APP
        try:
            fake_updater = MagicMock()
            fake_updater.stop = AsyncMock()

            fake_app = MagicMock()
            fake_app.stop     = AsyncMock()
            fake_app.shutdown = AsyncMock()
            fake_app.updater  = fake_updater

            tg._VGX_TG_APP = fake_app
            _run(tg.shutdown_event())

            fake_updater.stop.assert_awaited_once()
            fake_app.stop.assert_awaited_once()
            fake_app.shutdown.assert_awaited_once()
        finally:
            tg._VGX_TG_APP = original

    def test_app_py_wires_vgx_tg_into_lifespan(self):
        """app.py lifespan must call vgx_tg.startup_event and vgx_tg.shutdown_event."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app._app_lifespan)
        assert "vgx_tg.startup_event"  in src, "vgx_tg.startup_event not found in lifespan"
        assert "vgx_tg.shutdown_event" in src, "vgx_tg.shutdown_event not found in lifespan"

    def test_vgx_telegram_bot_status_is_dynamic(self):
        """app.py service_statuses must include a real vgx_telegram_bot check."""
        import inspect
        import app as main_app
        src = inspect.getsource(main_app.pull_state_payload)
        assert "vgx_tg._VGX_TG_APP" in src, (
            "vgx_telegram_bot status is missing or still hardcoded"
        )
