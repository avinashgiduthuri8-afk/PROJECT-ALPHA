"""
Part 0.6 — Configuration Safety (Deny-by-Default) validation tests.

Covers all required scenarios:
  1. Configured — valid limits — trading allowed
  2. Missing env vars — trading denied — CAPITAL_LIMIT_NOT_CONFIGURED
  3. Zero limits — trading denied
  4. Invalid (non-numeric) values — trading denied with proper logging
"""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_risk_engine(env: dict):
    """Re-import risk_engine.config and risk_engine.engine under a given env."""
    # Stub out the bot storage modules so engine.py can import cleanly.
    for mod in ("bots.pmb_bot.storage", "bots.mtb_bot.storage",
                "bots.volatile_gridX.storage"):
        stub = types.ModuleType(mod)
        stub.get_open_positions = lambda: []          # type: ignore[attr-defined]
        if mod.endswith("volatile_gridX.storage"):
            stub.VGXStorageError = Exception          # type: ignore[attr-defined]
        sys.modules[mod] = stub

    # Remove cached risk_engine modules so they re-execute with the new env.
    for key in list(sys.modules):
        if key.startswith("bots.risk_engine"):
            del sys.modules[key]

    with patch.dict("os.environ", env, clear=True):
        import bots.risk_engine.config as cfg
        importlib.reload(cfg)
        import bots.risk_engine.engine as eng
        importlib.reload(eng)
    return cfg, eng


def _decision(env: dict, bot: str = "PMB", amount: float = 100.0):
    """Return (cfg, engine, RiskDecision) under the given env."""
    cfg, eng = _reload_risk_engine(env)
    # Patch get_trading_enabled to return True so we test capital-limit path.
    with patch.object(eng, "get_trading_enabled", return_value=True), \
         patch.object(eng, "EMERGENCY_STOP", False), \
         patch.object(eng, "BOT_MODE", {bot: "PAPER"}), \
         patch.object(eng, "TOTAL_CAPITAL_LIMIT", cfg.TOTAL_CAPITAL_LIMIT), \
         patch.object(eng, "BOT_CAPITAL_LIMIT", cfg.BOT_CAPITAL_LIMIT), \
         patch.object(eng, "_load_bot_positions", return_value=[]):
        result = eng.check_trade_allowed(bot, amount)
    return cfg, eng, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDenyByDefaultCapitalLimits(unittest.TestCase):

    # ── Scenario 1: Configured — valid limits — trading allowed ──────────────
    def test_configured_limits_allows_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "10000",
            "PMB_CAPITAL_LIMIT": "3000",
            "PMB_BOT_MODE": "PAPER",
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        self.assertEqual(cfg.TOTAL_CAPITAL_LIMIT, 10000.0)
        self.assertEqual(cfg.BOT_CAPITAL_LIMIT["PMB"], 3000.0)
        self.assertTrue(decision.allowed, f"Expected allowed=True, got: {decision}")
        self.assertEqual(decision.code, "OK")

    # ── Scenario 2a: Missing TOTAL_CAPITAL_LIMIT env var ─────────────────────
    def test_missing_total_capital_limit_denies_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "PMB_CAPITAL_LIMIT": "3000",
            "PMB_BOT_MODE": "PAPER",
            # TOTAL_CAPITAL_LIMIT intentionally absent
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        self.assertEqual(cfg.TOTAL_CAPITAL_LIMIT, 0.0,
                         "Missing env var must default to 0")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED")

    # ── Scenario 2b: Missing BOT_CAPITAL_LIMIT env var ───────────────────────
    def test_missing_bot_capital_limit_denies_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "10000",
            "PMB_BOT_MODE": "PAPER",
            # PMB_CAPITAL_LIMIT intentionally absent
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        self.assertEqual(cfg.BOT_CAPITAL_LIMIT["PMB"], 0.0,
                         "Missing env var must default to 0")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED")

    # ── Scenario 3a: TOTAL_CAPITAL_LIMIT explicitly zero ─────────────────────
    def test_zero_total_capital_limit_denies_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "0",
            "PMB_CAPITAL_LIMIT": "3000",
            "PMB_BOT_MODE": "PAPER",
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        self.assertEqual(cfg.TOTAL_CAPITAL_LIMIT, 0.0)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED")

    # ── Scenario 3b: BOT_CAPITAL_LIMIT explicitly zero ───────────────────────
    def test_zero_bot_capital_limit_denies_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "10000",
            "PMB_CAPITAL_LIMIT": "0",
            "PMB_BOT_MODE": "PAPER",
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        self.assertEqual(cfg.BOT_CAPITAL_LIMIT["PMB"], 0.0)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED")

    # ── Scenario 4a: Invalid (non-numeric) TOTAL_CAPITAL_LIMIT ───────────────
    def test_invalid_total_capital_limit_denies_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "not_a_number",
            "PMB_CAPITAL_LIMIT": "3000",
            "PMB_BOT_MODE": "PAPER",
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        # Bad value must parse to 0, not crash.
        self.assertEqual(cfg.TOTAL_CAPITAL_LIMIT, 0.0,
                         "Invalid env var must fall to 0")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED")

    # ── Scenario 4b: Invalid (non-numeric) BOT_CAPITAL_LIMIT ─────────────────
    def test_invalid_bot_capital_limit_denies_trade(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "10000",
            "PMB_CAPITAL_LIMIT": "three_thousand",
            "PMB_BOT_MODE": "PAPER",
        }
        cfg, eng, decision = _decision(env, bot="PMB", amount=100.0)

        self.assertEqual(cfg.BOT_CAPITAL_LIMIT["PMB"], 0.0,
                         "Invalid env var must fall to 0")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED")

    # ── Reason string content check ───────────────────────────────────────────
    def test_decision_reason_mentions_capital_limit(self):
        env = {
            "TRADING_ENABLED": "true",
            "TOTAL_CAPITAL_LIMIT": "0",
            "PMB_CAPITAL_LIMIT": "3000",
            "PMB_BOT_MODE": "PAPER",
        }
        _, _, decision = _decision(env, bot="PMB", amount=100.0)
        self.assertIn("TOTAL_CAPITAL_LIMIT", decision.reason)

    # ── All three bots denied when limits are unconfigured ───────────────────
    def test_all_bots_denied_when_no_limits_configured(self):
        env = {"TRADING_ENABLED": "true"}
        cfg, eng = _reload_risk_engine(env)

        for bot in ("VGX", "PMB", "MTB"):
            with patch.object(eng, "get_trading_enabled", return_value=True), \
                 patch.object(eng, "EMERGENCY_STOP", False), \
                 patch.object(eng, "BOT_MODE", {bot: "PAPER"}), \
                 patch.object(eng, "TOTAL_CAPITAL_LIMIT", cfg.TOTAL_CAPITAL_LIMIT), \
                 patch.object(eng, "BOT_CAPITAL_LIMIT", cfg.BOT_CAPITAL_LIMIT), \
                 patch.object(eng, "_load_bot_positions", return_value=[]):
                decision = eng.check_trade_allowed(bot, 100.0)
            self.assertFalse(decision.allowed,
                             f"{bot} should be denied when limits are 0")
            self.assertEqual(decision.code, "CAPITAL_LIMIT_NOT_CONFIGURED",
                             f"{bot} code mismatch: {decision.code}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
