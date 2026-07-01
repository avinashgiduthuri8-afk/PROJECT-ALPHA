"""
SP4.1 regression tests.

BUG-47: VGX scanner_bridge.normalize_signal() defaulted action to ""
        causing process_scanner_signal() to reject all scanner signals.
        Fixed: default now "BUY" (matching MTB/PMB bridge pattern).

BUG-48: LATEST_SCANNER_SIGNALS alias already present in scanner_bot/main.py
        (resolved during SP2.4/2.5); verified here that both names are in
        sync and the getattr path used by the VGX bridge works correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# BUG-47 — normalize_signal() action default
# ─────────────────────────────────────────────────────────────────────────────

class TestBug47NormalizeSignal:

    def _norm(self, signal: dict) -> dict | None:
        from bots.volatile_gridX.scanner_bridge import normalize_signal
        return normalize_signal(signal)

    def test_defaults_action_to_buy_when_key_absent(self):
        """A scanner-shaped signal with no 'action' key must produce action='BUY'."""
        result = self._norm({"coin": "BTC", "score": 85.0})
        assert result is not None
        assert result["action"] == "BUY", (
            f"Expected action='BUY', got {result['action']!r}"
        )

    def test_preserves_explicit_action_key(self):
        """An explicit 'action' key must not be overridden by the default."""
        result = self._norm({"coin": "ETH", "score": 80.0, "action": "SELL"})
        assert result is not None
        assert result["action"] == "SELL", (
            f"Expected action='SELL', got {result['action']!r}"
        )

    def test_explicit_buy_action_preserved(self):
        """An explicit 'action': 'buy' must normalise to 'BUY'."""
        result = self._norm({"coin": "SOL", "score": 75.0, "action": "buy"})
        assert result is not None
        assert result["action"] == "BUY"

    def test_empty_signal_returns_none(self):
        """Non-dict input must still return None (no regression)."""
        from bots.volatile_gridX.scanner_bridge import normalize_signal
        assert normalize_signal("bad") is None
        assert normalize_signal(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# BUG-47 — process_scanner_signal() end-to-end acceptance
# ─────────────────────────────────────────────────────────────────────────────

class TestBug47ProcessScannerSignal:

    def _scanner_signal(self, coin: str = "BTC", score: float = 85.0) -> dict:
        """Minimal scanner-shaped signal — no 'action' key."""
        return {"coin": coin, "score": score, "source": "SCANNER"}

    def test_scanner_signal_not_rejected_for_action(self):
        """process_scanner_signal() must not reject a signal for action != 'BUY'."""
        from bots.volatile_gridX import scanner_bridge

        fake_validate = MagicMock(return_value=(True, "OK", {}))
        fake_execute  = MagicMock(return_value=(True, "Executed"))

        with patch.object(scanner_bridge, "validate_signal",  fake_validate), \
             patch.object(scanner_bridge, "paper_execute_signal", fake_execute):
            result = scanner_bridge.process_scanner_signal(
                self._scanner_signal("BTC", 85.0)
            )

        assert result.get("result") != "REJECTED" or \
               result.get("reason") != "Only BUY Signals Allowed", (
            f"Signal was incorrectly rejected for action: {result}"
        )

    def test_scanner_signal_reaches_validate_stage(self):
        """validate_signal must be called when action defaults to BUY."""
        from bots.volatile_gridX import scanner_bridge

        fake_validate = MagicMock(return_value=(False, "Score too low", {}))

        with patch.object(scanner_bridge, "validate_signal", fake_validate):
            scanner_bridge.process_scanner_signal(
                self._scanner_signal("ETH", 50.0)
            )

        fake_validate.assert_called_once()

    def test_scanner_signal_accepted_end_to_end(self):
        """Full pipeline: scanner signal with no action key returns ACCEPTED."""
        from bots.volatile_gridX import scanner_bridge

        fake_validate = MagicMock(return_value=(True, "OK", {}))
        fake_execute  = MagicMock(return_value=(True, "Paper trade executed"))

        with patch.object(scanner_bridge, "validate_signal",  fake_validate), \
             patch.object(scanner_bridge, "paper_execute_signal", fake_execute):
            result = scanner_bridge.process_scanner_signal(
                self._scanner_signal("SOL", 90.0)
            )

        assert result["result"] == "ACCEPTED", (
            f"Expected ACCEPTED, got: {result}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-48 — LATEST_SCANNER_SIGNALS alias verification
# ─────────────────────────────────────────────────────────────────────────────

class TestBug48ScannerSignalsAlias:

    def test_latest_scanner_signals_exists_on_module(self):
        """scanner_bot.main must expose LATEST_SCANNER_SIGNALS via getattr."""
        from bots.scanner_bot import main as scanner_main
        assert hasattr(scanner_main, "LATEST_SCANNER_SIGNALS"), (
            "LATEST_SCANNER_SIGNALS not found on bots.scanner_bot.main"
        )

    def test_latest_mtb_signals_exists_on_module(self):
        """scanner_bot.main must still expose LATEST_MTB_SIGNALS (compatibility)."""
        from bots.scanner_bot import main as scanner_main
        assert hasattr(scanner_main, "LATEST_MTB_SIGNALS"), (
            "LATEST_MTB_SIGNALS not found on bots.scanner_bot.main"
        )

    def test_alias_is_same_object_at_module_load(self):
        """At module load time, LATEST_SCANNER_SIGNALS and LATEST_MTB_SIGNALS
        must be the same list object."""
        from bots.scanner_bot import main as scanner_main
        assert scanner_main.LATEST_SCANNER_SIGNALS is scanner_main.LATEST_MTB_SIGNALS, (
            "LATEST_SCANNER_SIGNALS and LATEST_MTB_SIGNALS are not the same object"
        )

    def test_vgx_bridge_getattr_path_resolves(self):
        """_signals_from_module() must find LATEST_SCANNER_SIGNALS without
        falling through to LATEST_MTB_SIGNALS."""
        from bots.scanner_bot import main as scanner_main
        result = getattr(scanner_main, "LATEST_SCANNER_SIGNALS", None)
        assert result is not None, (
            "getattr(scanner_main, 'LATEST_SCANNER_SIGNALS') returned None"
        )
