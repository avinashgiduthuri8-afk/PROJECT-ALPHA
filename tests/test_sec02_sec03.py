"""
Tests for SEC-02 and SEC-03 security fixes in bots/risk_engine/config.py
and bots/risk_engine/engine.py.

SEC-02: TRADING_ENABLED must default to False (deny-by-default).
SEC-03: BOT_MODE values must be validated; invalid values clamped to DISABLED
        and a WARNING logged.
"""

from __future__ import annotations

import importlib
import logging
import sys
import types
from unittest.mock import patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _reload_config(env: dict) -> types.ModuleType:
    """Re-import bots.risk_engine.config under a patched environment."""
    mod_name = "bots.risk_engine.config"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    with patch.dict("os.environ", env, clear=False):
        mod = importlib.import_module(mod_name)
    return mod


def _reload_engine(env: dict) -> types.ModuleType:
    """Re-import both config and engine under a patched environment."""
    for name in ("bots.risk_engine.config", "bots.risk_engine.engine"):
        sys.modules.pop(name, None)
    with patch.dict("os.environ", env, clear=False):
        mod = importlib.import_module("bots.risk_engine.engine")
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# SEC-02 tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSec02TradingEnabledDefault:

    def test_trading_disabled_when_env_var_absent(self):
        """SEC-02: TRADING_ENABLED must be False when env var is not set."""
        env = {}
        env.pop("TRADING_ENABLED", None)
        with patch.dict("os.environ", {}, clear=True):
            # Remove TRADING_ENABLED entirely
            import os
            saved = os.environ.pop("TRADING_ENABLED", None)
            try:
                cfg = _reload_config({})
                assert cfg.TRADING_ENABLED is False, (
                    f"Expected TRADING_ENABLED=False when env var absent, got {cfg.TRADING_ENABLED}"
                )
            finally:
                if saved is not None:
                    os.environ["TRADING_ENABLED"] = saved

    def test_trading_enabled_when_set_true(self):
        """SEC-02: TRADING_ENABLED=true must be respected."""
        cfg = _reload_config({"TRADING_ENABLED": "true"})
        assert cfg.TRADING_ENABLED is True

    def test_trading_enabled_case_insensitive_true(self):
        """SEC-02: TRADING_ENABLED=TRUE must be accepted."""
        cfg = _reload_config({"TRADING_ENABLED": "TRUE"})
        assert cfg.TRADING_ENABLED is True

    def test_trading_disabled_when_set_false(self):
        """SEC-02: TRADING_ENABLED=false must be respected."""
        cfg = _reload_config({"TRADING_ENABLED": "false"})
        assert cfg.TRADING_ENABLED is False

    def test_trading_disabled_when_set_zero(self):
        """SEC-02: TRADING_ENABLED=0 must evaluate to False (not 'true')."""
        cfg = _reload_config({"TRADING_ENABLED": "0"})
        assert cfg.TRADING_ENABLED is False


# ─────────────────────────────────────────────────────────────────────────────
# SEC-03 tests — config layer
# ─────────────────────────────────────────────────────────────────────────────

class TestSec03BotModeValidationConfig:

    def test_valid_paper_mode_accepted(self):
        """SEC-03: PAPER is a valid mode and must not be clamped."""
        cfg = _reload_config({"VGX_BOT_MODE": "PAPER"})
        assert cfg.BOT_MODE["VGX"] == "PAPER"

    def test_valid_live_mode_accepted(self):
        """SEC-03: LIVE is a valid mode and must not be clamped."""
        cfg = _reload_config({"MTB_BOT_MODE": "LIVE"})
        assert cfg.BOT_MODE["MTB"] == "LIVE"

    def test_valid_disabled_mode_accepted(self):
        """SEC-03: DISABLED is a valid mode and must not be clamped."""
        cfg = _reload_config({"PMB_BOT_MODE": "DISABLED"})
        assert cfg.BOT_MODE["PMB"] == "DISABLED"

    def test_valid_paused_mode_accepted(self):
        """SEC-03: PAUSED is a valid mode and must not be clamped."""
        cfg = _reload_config({"VGX_BOT_MODE": "PAUSED"})
        assert cfg.BOT_MODE["VGX"] == "PAUSED"

    def test_invalid_mode_typo_clamped_to_disabled(self):
        """SEC-03: Typo 'PAPPER' must be clamped to DISABLED."""
        cfg = _reload_config({"VGX_BOT_MODE": "PAPPER"})
        assert cfg.BOT_MODE["VGX"] == "DISABLED"

    def test_invalid_mode_lowercase_paper_clamped(self):
        """SEC-03: Lowercase 'paper' must be normalised to PAPER (valid)."""
        cfg = _reload_config({"VGX_BOT_MODE": "paper"})
        assert cfg.BOT_MODE["VGX"] == "PAPER"

    def test_invalid_mode_mixed_case_live_clamped(self):
        """SEC-03: Mixed-case 'Live' must be normalised to LIVE (valid)."""
        cfg = _reload_config({"MTB_BOT_MODE": "Live"})
        assert cfg.BOT_MODE["MTB"] == "LIVE"

    def test_invalid_mode_garbage_clamped_to_disabled(self):
        """SEC-03: Garbage value 'XYZZY' must be clamped to DISABLED."""
        cfg = _reload_config({"PMB_BOT_MODE": "XYZZY"})
        assert cfg.BOT_MODE["PMB"] == "DISABLED"

    def test_invalid_mode_empty_string_clamped_to_disabled(self):
        """SEC-03: Empty string must be clamped to DISABLED."""
        cfg = _reload_config({"VGX_BOT_MODE": ""})
        assert cfg.BOT_MODE["VGX"] == "DISABLED"

    def test_invalid_mode_logs_warning(self, caplog):
        """SEC-03: Invalid BOT_MODE must produce a WARNING log entry."""
        with caplog.at_level(logging.WARNING, logger="risk_engine.config"):
            _reload_config({"VGX_BOT_MODE": "PAPPER"})
        assert any(
            "SEC-03" in r.message and "VGX" in r.message and "PAPPER" in r.message
            for r in caplog.records
        ), f"Expected SEC-03 warning about VGX/PAPPER. Got: {[r.message for r in caplog.records]}"

    def test_invalid_mode_warning_includes_env_var_name(self, caplog):
        """SEC-03: Warning must name the env var (VGX_BOT_MODE) and bad value."""
        with caplog.at_level(logging.WARNING, logger="risk_engine.config"):
            _reload_config({"MTB_BOT_MODE": "GARBAGE"})
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("MTB_BOT_MODE" in m and "GARBAGE" in m for m in warning_messages), (
            f"Warning must contain env var name and bad value. Got: {warning_messages}"
        )

    def test_all_bots_default_to_paper(self):
        """SEC-03: When no env vars set, all bots default to PAPER (valid)."""
        import os
        # Remove all BOT_MODE env vars
        saved = {k: os.environ.pop(k, None) for k in ("VGX_BOT_MODE", "PMB_BOT_MODE", "MTB_BOT_MODE")}
        try:
            cfg = _reload_config({})
            for bot in ("VGX", "PMB", "MTB"):
                assert cfg.BOT_MODE[bot] == "PAPER", f"{bot} default should be PAPER, got {cfg.BOT_MODE[bot]}"
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# SEC-03 tests — engine layer (check_trade_allowed)
# ─────────────────────────────────────────────────────────────────────────────

class TestSec03UnknownModeBlockedInEngine:

    def test_unknown_mode_blocked_after_clamping(self):
        """SEC-03: A bot whose mode was clamped to DISABLED must be blocked by check_trade_allowed."""
        engine = _reload_engine({
            "TRADING_ENABLED": "true",
            "VGX_BOT_MODE": "PAPPER",
        })
        decision = engine.check_trade_allowed("VGX", 100.0)
        assert decision.allowed is False
        assert decision.code == "BOT_INACTIVE"

    def test_valid_paper_mode_passes_mode_check(self):
        """SEC-03: A bot in PAPER mode must pass the mode check (capital limits aside)."""
        engine = _reload_engine({
            "TRADING_ENABLED": "true",
            "VGX_BOT_MODE": "PAPER",
            "VGX_CAPITAL_LIMIT": "999999",
            "TOTAL_CAPITAL_LIMIT": "999999",
        })
        with patch.object(engine, "_load_bot_positions", return_value=[]):
            decision = engine.check_trade_allowed("VGX", 100.0)
        assert decision.allowed is True
        assert decision.code == "OK"

    def test_trading_disabled_by_default_blocks_all(self):
        """SEC-02+engine: With no TRADING_ENABLED env var, check_trade_allowed must deny."""
        import os
        saved = os.environ.pop("TRADING_ENABLED", None)
        try:
            engine = _reload_engine({"VGX_BOT_MODE": "PAPER"})
            decision = engine.check_trade_allowed("VGX", 100.0)
            assert decision.allowed is False
            assert decision.code == "TRADING_DISABLED"
        finally:
            if saved is not None:
                os.environ["TRADING_ENABLED"] = saved


# ─────────────────────────────────────────────────────────────────────────────
# SEC-03 tests — startup log lines in engine.py
# ─────────────────────────────────────────────────────────────────────────────

class TestSec03StartupLogs:

    def test_startup_logs_resolved_mode_for_each_bot(self, caplog):
        """engine.py must log the resolved BOT_MODE for VGX, PMB, and MTB at startup."""
        with caplog.at_level(logging.INFO, logger="risk_engine"):
            _reload_engine({
                "TRADING_ENABLED": "true",
                "VGX_BOT_MODE": "PAPER",
                "PMB_BOT_MODE": "DISABLED",
                "MTB_BOT_MODE": "LIVE",
            })
        messages = " ".join(r.message for r in caplog.records)
        for bot, expected_mode in [("VGX", "PAPER"), ("PMB", "DISABLED"), ("MTB", "LIVE")]:
            assert bot in messages, f"Startup log missing bot name: {bot}"
            assert expected_mode in messages, f"Startup log missing resolved mode: {expected_mode}"

    def test_startup_logs_trading_enabled_state(self, caplog):
        """engine.py must log the TRADING_ENABLED state at startup."""
        with caplog.at_level(logging.INFO, logger="risk_engine"):
            _reload_engine({"TRADING_ENABLED": "true"})
        messages = " ".join(r.message for r in caplog.records)
        assert "TRADING_ENABLED" in messages
