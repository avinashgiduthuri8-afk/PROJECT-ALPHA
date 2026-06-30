"""
SP2.4 regression tests.

BUG-31: VGX background_loop now calls process_scanner_signal when get_signals() returns data.
BUG-32: market_intelligence() regime changes when analyze_coin's score changes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
#  BUG-32 — real analyze_coin drives market_intelligence() regime
# ─────────────────────────────────────────────────────────────────────────────

class TestBug32MarketIntelligence:
    """market_intelligence() must return the correct regime for each score band."""

    def _call_market_intelligence(self, score: int) -> dict:
        from bots.volatile_gridX.risk_engine import market_intelligence
        mock_result = {"score": score, "trend": "neutral", "rsi": 50, "ema": "flat"}
        with patch("bots.volatile_gridX.risk_engine.analyze_coin", return_value=mock_result):
            return market_intelligence()

    def test_bull_regime_when_score_ge_80(self):
        result = self._call_market_intelligence(85)
        assert result["regime"] == "BULL", f"Expected BULL, got {result['regime']}"
        assert result["score"] == 85

    def test_sideways_regime_when_score_60_to_79(self):
        result = self._call_market_intelligence(70)
        assert result["regime"] == "SIDEWAYS", f"Expected SIDEWAYS, got {result['regime']}"

    def test_bear_regime_when_score_lt_60(self):
        result = self._call_market_intelligence(40)
        assert result["regime"] == "BEAR", f"Expected BEAR, got {result['regime']}"

    def test_boundary_score_80_is_bull(self):
        result = self._call_market_intelligence(80)
        assert result["regime"] == "BULL"

    def test_boundary_score_60_is_sideways(self):
        result = self._call_market_intelligence(60)
        assert result["regime"] == "SIDEWAYS"

    def test_boundary_score_59_is_bear(self):
        result = self._call_market_intelligence(59)
        assert result["regime"] == "BEAR"

    def test_stub_score_75_would_give_sideways(self):
        """Confirm old stub value (75) yields SIDEWAYS — sanity check on thresholds."""
        result = self._call_market_intelligence(75)
        assert result["regime"] == "SIDEWAYS"

    def test_analyze_coin_not_stubbed_returns_score_key(self):
        """analyze_coin_simple (the real impl) always returns a dict with 'score'."""
        from bots.volatile_gridX.market_analysis import analyze_coin_simple
        result = analyze_coin_simple("BTC", history=[])
        assert "score" in result, "analyze_coin_simple must return a 'score' key"
        assert isinstance(result["score"], (int, float))


# ─────────────────────────────────────────────────────────────────────────────
#  BUG-31 — background_loop calls process_scanner_signal for each signal
# ─────────────────────────────────────────────────────────────────────────────

class TestBug31BackgroundLoopSignalConsumption:
    """VGX background_loop feeds each scanner signal through process_scanner_signal."""

    def _run_one_loop_iteration(
        self,
        fake_signals: list[dict],
        scanner_side_effect=None,
    ) -> list:
        """
        Execute exactly one iteration of background_loop's inner body using
        mock collaborators.  Returns the list of calls made to
        process_scanner_signal.

        Pass scanner_side_effect=Exception(...) to simulate a scanner failure.
        """
        from unittest.mock import AsyncMock
        import bots.volatile_gridX.main as vgx_main
        import bots.volatile_gridX.scanner_bridge as sb

        process_calls = []

        def fake_get_signals():
            if scanner_side_effect is not None:
                raise scanner_side_effect
            return fake_signals

        def fake_process(sig):
            process_calls.append(sig)
            return {"result": "ACCEPTED", "reason": "mocked"}

        async def _run():
            with (
                patch.object(sb, "get_signals", side_effect=fake_get_signals),
                patch.object(sb, "process_scanner_signal", side_effect=fake_process),
                patch("bots.volatile_gridX.main.update_market_cache"),
                patch("bots.volatile_gridX.main.auto_alerts", new=AsyncMock()),
                patch("bots.volatile_gridX.main.auto_sell"),
                patch("bots.volatile_gridX.main.update_stats"),
                patch("bots.volatile_gridX.storage.save_data"),
                patch("asyncio.sleep", new=AsyncMock(side_effect=StopAsyncIteration)),
            ):
                try:
                    await vgx_main.background_loop()
                except StopAsyncIteration:
                    pass

        asyncio.new_event_loop().run_until_complete(_run())
        return process_calls

    def test_process_scanner_signal_called_for_each_signal(self):
        """One call to process_scanner_signal per signal returned by get_signals()."""
        signals = [
            {"coin": "BTC", "action": "BUY", "score": 80},
            {"coin": "ETH", "action": "BUY", "score": 75},
        ]
        calls = self._run_one_loop_iteration(signals)
        assert len(calls) == 2, f"Expected 2 calls, got {len(calls)}"

    def test_no_process_call_when_no_signals(self):
        """No calls to process_scanner_signal when get_signals() returns empty list."""
        calls = self._run_one_loop_iteration([])
        assert calls == [], f"Expected 0 calls, got {calls}"

    def test_scanner_failure_does_not_break_loop(self):
        """A scanner bridge exception must not propagate — loop continues to auto_sell."""
        from unittest.mock import AsyncMock
        import bots.volatile_gridX.scanner_bridge as sb
        import bots.volatile_gridX.main as vgx_main

        auto_sell_called = []

        async def _run():
            with (
                patch.object(sb, "get_signals", side_effect=RuntimeError("scanner down")),
                patch("bots.volatile_gridX.main.update_market_cache"),
                patch("bots.volatile_gridX.main.auto_alerts", new=AsyncMock()),
                patch("bots.volatile_gridX.main.auto_sell", side_effect=lambda: auto_sell_called.append(1)),
                patch("bots.volatile_gridX.main.update_stats"),
                patch("bots.volatile_gridX.storage.save_data"),
                patch("asyncio.sleep", new=AsyncMock(side_effect=StopAsyncIteration)),
            ):
                try:
                    await vgx_main.background_loop()
                except StopAsyncIteration:
                    pass

        asyncio.new_event_loop().run_until_complete(_run())
        assert auto_sell_called, "auto_sell must still be called after scanner failure"
