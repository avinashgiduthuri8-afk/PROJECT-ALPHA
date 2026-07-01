"""
SP5 regression tests.

BUG-53: get_current_prices() used stale entry_price; now prefers live
        "price" field from LATEST_SCANNER_SIGNALS.
BUG-54: execute_partial_sell() left position open with zero invested
        and non-zero qty; now closes when max(0, new_invested) <= 0.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# BUG-53 — get_current_prices() price priority
# ─────────────────────────────────────────────────────────────────────────────

class TestBug53GetCurrentPrices:
    """
    Patch strategy: patch.object(real_scanner_main, "LATEST_SCANNER_SIGNALS", ...)
    directly replaces the attribute on the real imported module object, which is
    what get_current_prices() reads via getattr(). This avoids sys.modules
    manipulation, which is unreliable across test-ordering boundaries when the
    import uses `from package import submodule` style.
    """

    @staticmethod
    def _real_scanner():
        import bots.scanner_bot.main as m
        return m

    def test_uses_price_from_latest_scanner_signals(self):
        """When LATEST_SCANNER_SIGNALS has a 'price' field, it must be used."""
        from bots.pmb_bot import scanner_bridge
        live_signals = [
            {"coin": "BTC", "price": 9_200_000.0, "entry_price": 9_000_000.0},
            {"coin": "ETH", "price": 210_000.0,   "entry_price": 200_000.0},
        ]
        with patch.object(self._real_scanner(), "LATEST_SCANNER_SIGNALS",
                          new=live_signals, create=True), \
             patch("bots.pmb_bot.scanner_bridge.get_signals", return_value=[]):
            result = scanner_bridge.get_current_prices()
        assert result.get("BTC") == 9_200_000.0, (
            f"Expected live price 9200000, got {result.get('BTC')}"
        )
        assert result.get("ETH") == 210_000.0

    def test_falls_back_to_entry_price_when_scanner_signals_empty(self):
        """When LATEST_SCANNER_SIGNALS is empty, fallback uses entry_price."""
        from bots.pmb_bot import scanner_bridge
        fallback = [{"coin": "BTC", "entry_price": 9_000_000.0}]
        with patch.object(self._real_scanner(), "LATEST_SCANNER_SIGNALS",
                          new=[], create=True), \
             patch("bots.pmb_bot.scanner_bridge.get_signals",
                   return_value=fallback):
            result = scanner_bridge.get_current_prices()
        assert result.get("BTC") == 9_000_000.0, (
            f"Expected fallback entry_price 9000000, got {result.get('BTC')}"
        )

    def test_excludes_coins_with_price_zero(self):
        """Coins whose price and entry_price are both 0 or absent must be excluded."""
        from bots.pmb_bot import scanner_bridge
        signals = [
            {"coin": "BTC", "price": 0.0, "entry_price": 0.0},
            {"coin": "ETH", "price": 210_000.0},
        ]
        with patch.object(self._real_scanner(), "LATEST_SCANNER_SIGNALS",
                          new=signals, create=True), \
             patch("bots.pmb_bot.scanner_bridge.get_signals", return_value=[]):
            result = scanner_bridge.get_current_prices()
        assert "BTC" not in result, "Coin with price=0 must be excluded"
        assert "ETH" in result

    def test_falls_back_when_scanner_signals_unavailable(self):
        """When LATEST_SCANNER_SIGNALS is missing entirely, fallback uses get_signals()."""
        from bots.pmb_bot import scanner_bridge
        fallback = [{"coin": "SOL", "entry_price": 8_500.0}]
        # Patch LATEST_SCANNER_SIGNALS to [] (empty) to force fallback path
        with patch.object(self._real_scanner(), "LATEST_SCANNER_SIGNALS",
                          new=[], create=True), \
             patch("bots.pmb_bot.scanner_bridge.get_signals",
                   return_value=fallback):
            result = scanner_bridge.get_current_prices()
        assert result.get("SOL") == 8_500.0

    def test_prefers_price_over_entry_price_when_both_present(self):
        """'price' key must win over 'entry_price' when both are present."""
        from bots.pmb_bot import scanner_bridge
        signals = [{"coin": "BNB", "price": 55_000.0, "entry_price": 50_000.0}]
        with patch.object(self._real_scanner(), "LATEST_SCANNER_SIGNALS",
                          new=signals, create=True), \
             patch("bots.pmb_bot.scanner_bridge.get_signals", return_value=[]):
            result = scanner_bridge.get_current_prices()
        assert result.get("BNB") == 55_000.0, (
            f"Expected 'price' 55000 to win over entry_price 50000, got {result}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-54 — execute_partial_sell() zero-invested close condition
# ─────────────────────────────────────────────────────────────────────────────

class TestBug54PartialSellZeroInvested:

    def _make_position(self, qty: float, invested: float,
                       avg_entry: float = 100.0) -> dict:
        return {
            "id":                  "test-pos-1",
            "coin":                "BTC",
            "symbol":              "BTCUSDT",
            "status":              "OPEN",
            "total_quantity":      qty,
            "total_invested":      invested,
            "avg_entry_price":     avg_entry,
            "partial_sell_count":  0,
            "next_sell_price":     0.0,
        }

    def _run_partial_sell(self, position: dict, price: float) -> dict:
        from bots.pmb_bot import trading_engine
        fake_positions = [dict(position)]
        fake_stats = {"cash_balance": 1000.0, "total_pnl": 0.0}
        fake_trades: list = []

        with patch.object(trading_engine.storage, "load_positions",
                          return_value=fake_positions), \
             patch.object(trading_engine.storage, "save_positions",
                          side_effect=lambda p: fake_positions.__setitem__(
                              slice(None), p)), \
             patch.object(trading_engine.storage, "load_stats",
                          return_value=fake_stats), \
             patch.object(trading_engine.storage, "save_stats",
                          side_effect=lambda s: fake_stats.update(s)), \
             patch.object(trading_engine.storage, "load_trades",
                          return_value=fake_trades), \
             patch.object(trading_engine.storage, "save_trades",
                          side_effect=lambda t: None):
            trading_engine.execute_partial_sell(position, price)
        return position

    def test_closes_position_when_invested_rounds_to_zero(self):
        """Position must be CLOSED when new_invested <= 0 even if qty > 0."""
        # Construct a position where avg_cost_sold ≈ total_invested
        # so new_invested rounds to zero / goes negative
        qty      = 0.001          # tiny quantity
        price    = 100_000.0      # high price → PARTIAL_SELL proceeds ≥ invested
        invested = 0.001          # cost basis so tiny that one sell wipes it out
        pos = self._make_position(qty=qty, invested=invested, avg_entry=price)

        result = self._run_partial_sell(pos, price)
        assert result["status"] == "CLOSED", (
            f"Position should be CLOSED when invested rounds to 0, "
            f"got status={result['status']!r}, "
            f"qty={result['total_quantity']}, invested={result['total_invested']}"
        )

    def test_normal_partial_sell_remains_open(self):
        """A standard partial sell with plenty of qty/invested must stay OPEN."""
        pos = self._make_position(qty=1.0, invested=90_000.0, avg_entry=90_000.0)
        result = self._run_partial_sell(pos, 100_000.0)
        # Only closed if new_qty <= 0 OR new_invested <= 0 — neither applies here
        assert result["status"] == "OPEN", (
            f"Position with remaining qty and invested should stay OPEN, "
            f"got {result['status']!r}"
        )

    def test_closes_position_when_qty_reaches_zero(self):
        """Existing close-on-zero-qty path must still work (no regression)."""
        # Very small position — PARTIAL_SELL will exceed qty
        pos = self._make_position(qty=1e-10, invested=1e-10, avg_entry=1.0)
        result = self._run_partial_sell(pos, 1.0)
        assert result["status"] == "CLOSED"
