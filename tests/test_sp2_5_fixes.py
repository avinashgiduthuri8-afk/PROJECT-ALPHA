"""
SP2.5 regression tests.

BUG-34: VGX emergency_close_all() — native v1 implementation using _TRADE_LOCK.
BUG-35: VGX buy_position() rejects a second BUY for same coin from a different source.
"""

from __future__ import annotations

from unittest.mock import patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_position(coin: str, buy_price: float, amount: float, source: str = "SCANNER") -> dict:
    qty = amount / buy_price
    return {
        "coin":            coin,
        "buy_price":       buy_price,
        "qty":             qty,
        "amount":          amount,
        "time":            0.0,
        "peak":            buy_price,
        "trailing_active": False,
        "trade_source":    source,
    }


def _setup_positions(positions: dict[str, dict]):
    """Inject synthetic positions into VGX storage and return the original dict."""
    import bots.volatile_gridX.storage as st
    original = dict(st.positions)
    st.positions.clear()
    st.positions.update(positions)
    return original


def _restore_positions(original: dict):
    import bots.volatile_gridX.storage as st
    st.positions.clear()
    st.positions.update(original)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-34 — emergency_close_all (native v1)
# ─────────────────────────────────────────────────────────────────────────────

class TestBug34EmergencyCloseAll:
    """emergency_close_all() must close every open position and return correct totals."""

    def test_closes_all_positions_returns_correct_pnl(self):
        """All open positions are closed; total_pnl matches sum of individual PnLs."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import emergency_close_all

        fake_positions = {
            "BTC_SCANNER": _make_position("BTC", buy_price=50_000.0, amount=500.0),
            "ETH_SCANNER": _make_position("ETH", buy_price=3_000.0,  amount=300.0),
        }
        original_positions = _setup_positions(fake_positions)
        original_balance = st.virtual_balance
        st.virtual_balance = 10_000.0

        try:
            # BTC current price → +10 % profit, ETH current price → -5 % loss
            def fake_price(coin: str) -> float:
                return {"BTC": 55_000.0, "ETH": 2_850.0}.get(coin, 0)

            with (
                patch("bots.volatile_gridX.trading_engine.get_cached_price_safe", side_effect=fake_price),
                patch("bots.volatile_gridX.storage.save_data"),
            ):
                result = emergency_close_all("TEST")

            assert result["closed"] == 2,  f"Expected 2 closed, got {result['closed']}"
            assert result["failed"] == 0,  f"Expected 0 failed, got {result['failed']}"
            assert result["reason"] == "TEST"

            # BTC: qty = 500/50000 = 0.01  receive = 0.01*55000 = 550  pnl = +50
            # ETH: qty = 300/3000  = 0.1   receive = 0.1*2850  = 285  pnl = -15
            expected_pnl = round(50.0 + (-15.0), 4)
            assert abs(result["total_pnl"] - expected_pnl) < 0.01, (
                f"Expected total_pnl≈{expected_pnl}, got {result['total_pnl']}"
            )
            assert len(result["details"]) == 2

            # All positions must be gone from storage
            assert len(st.positions) == 0, "Positions dict should be empty after emergency close"

        finally:
            _restore_positions(original_positions)
            st.virtual_balance = original_balance

    def test_empty_positions_returns_zero_totals(self):
        """No positions → closed=0, failed=0, total_pnl=0."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import emergency_close_all

        original = _setup_positions({})
        try:
            with patch("bots.volatile_gridX.storage.save_data"):
                result = emergency_close_all("EMPTY_TEST")
            assert result["closed"] == 0
            assert result["failed"] == 0
            assert result["total_pnl"] == 0.0
            assert result["details"] == []
        finally:
            _restore_positions(original)

    def test_fallback_to_buy_price_when_no_live_price(self):
        """If get_cached_price_safe returns 0, position is closed at buy_price * 0.95."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import emergency_close_all

        buy_price = 1_000.0
        fake_positions = {
            "SOL_SCANNER": _make_position("SOL", buy_price=buy_price, amount=200.0),
        }
        original_positions = _setup_positions(fake_positions)
        original_balance = st.virtual_balance
        st.virtual_balance = 5_000.0

        try:
            with (
                patch("bots.volatile_gridX.trading_engine.get_cached_price_safe", return_value=0),
                patch("bots.volatile_gridX.storage.save_data"),
            ):
                result = emergency_close_all("NO_PRICE_TEST")

            # Must not raise; must close the position using fallback price
            assert result["closed"] == 1, f"Expected 1 closed, got {result['closed']}"
            assert result["failed"] == 0

            # qty = 200/1000 = 0.2  receive = 0.2 * (1000*0.95) = 190  pnl = -10
            expected_pnl = round(0.2 * (buy_price * 0.95) - 200.0, 4)
            assert abs(result["total_pnl"] - expected_pnl) < 0.01, (
                f"Expected total_pnl≈{expected_pnl}, got {result['total_pnl']}"
            )
            assert len(st.positions) == 0

        finally:
            _restore_positions(original_positions)
            st.virtual_balance = original_balance

    def test_return_shape_compatible_with_v2(self):
        """Return dict must contain all keys expected by safety_integration."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import emergency_close_all

        original = _setup_positions({})
        try:
            with patch("bots.volatile_gridX.storage.save_data"):
                result = emergency_close_all()
            assert set(result.keys()) >= {"closed", "failed", "total_pnl", "reason", "details"}
        finally:
            _restore_positions(original)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-35 — coin-level duplicate check in buy_position()
# ─────────────────────────────────────────────────────────────────────────────

class TestBug35CoinLevelDuplicateCheck:
    """buy_position() must reject a second BUY for the same coin from any source."""

    def test_rejects_same_coin_different_source(self):
        """BTC_SCANNER position open → BTC_MANUAL buy must be rejected."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import buy_position

        original_positions = _setup_positions({
            "BTC_SCANNER": _make_position("BTC", buy_price=50_000.0, amount=500.0, source="SCANNER"),
        })
        original_balance = st.virtual_balance
        st.virtual_balance = 100_000.0

        try:
            result = buy_position("BTC", price=50_000.0, amount=500.0, source="MANUAL")
            assert result is False, "Expected False (duplicate coin), got True"
            # Position dict should still have only the original entry
            assert len(st.positions) == 1
        finally:
            _restore_positions(original_positions)
            st.virtual_balance = original_balance

    def test_rejects_same_coin_same_source(self):
        """Existing BTC_SCANNER → another BTC_SCANNER must also be rejected."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import buy_position

        original_positions = _setup_positions({
            "BTC_SCANNER": _make_position("BTC", buy_price=50_000.0, amount=500.0),
        })
        original_balance = st.virtual_balance
        st.virtual_balance = 100_000.0

        try:
            result = buy_position("BTC", price=50_500.0, amount=500.0, source="SCANNER")
            assert result is False
        finally:
            _restore_positions(original_positions)
            st.virtual_balance = original_balance

    def test_allows_different_coin(self):
        """BTC open → ETH buy must be allowed (different coin)."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import buy_position

        original_positions = _setup_positions({
            "BTC_SCANNER": _make_position("BTC", buy_price=50_000.0, amount=500.0),
        })
        original_balance = st.virtual_balance
        st.virtual_balance = 100_000.0

        try:
            with patch("bots.volatile_gridX.storage.save_data"):
                result = buy_position("ETH", price=3_000.0, amount=300.0, source="SCANNER")
            assert result is True, "Expected True (different coin), got False"
            assert "ETH_SCANNER" in st.positions
        finally:
            _restore_positions(original_positions)
            st.virtual_balance = original_balance

    def test_empty_positions_allows_buy(self):
        """No existing positions → buy must succeed."""
        import bots.volatile_gridX.storage as st
        from bots.volatile_gridX.trading_engine import buy_position

        original_positions = _setup_positions({})
        original_balance = st.virtual_balance
        st.virtual_balance = 100_000.0

        try:
            with patch("bots.volatile_gridX.storage.save_data"):
                result = buy_position("BTC", price=50_000.0, amount=500.0, source="SCANNER")
            assert result is True
        finally:
            _restore_positions(original_positions)
            st.virtual_balance = original_balance


# ─────────────────────────────────────────────────────────────────────────────
# production_validation.py renamed check
# ─────────────────────────────────────────────────────────────────────────────

class TestProductionValidationRenamedCheck:
    """The 'VGX emergency_close_all available' check exists and passes."""

    def test_emergency_close_all_check_passes(self):
        """validate_trading_engine() must contain the renamed check and pass it."""
        from monitoring.production_validation import validate_trading_engine
        result = validate_trading_engine()
        check_names = [c["name"] for c in result.checks]
        assert "VGX emergency_close_all available" in check_names, (
            f"Check not found. Available checks: {check_names}"
        )
        ec_check = next(c for c in result.checks if c["name"] == "VGX emergency_close_all available")
        assert ec_check["passed"] is True, (
            f"Check failed with message: {ec_check.get('message', '')}"
        )

    def test_old_check_name_gone(self):
        """The old 'VGX trading_engine_v2 import' label must no longer appear."""
        from monitoring.production_validation import validate_trading_engine
        result = validate_trading_engine()
        check_names = [c["name"] for c in result.checks]
        assert "VGX trading_engine_v2 import" not in check_names, (
            "Old check name still present — rename was not applied"
        )
