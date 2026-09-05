"""
Phase 2 Execution Engine Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. Precision & Notional Enforcement (tick size, lot step size, min ₹100 notional rejection).
  2. Sub-account Routing (STE, HDA, VCP, BBS isolated clients + HMAC signatures).
  3. Bracket & Trailing SL/TP Evaluation.
  4. Statutory Fee Deduction (1.572% round-trip drag).
  5. Restart Recovery & Reconciliation (SQLite persistence, idempotency, desync detection).
"""

from __future__ import annotations

import asyncio
import inspect
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.types import BotMode, BotName, ExitReason, Position, PositionStatus, Signal
from v2.repository.db import Database
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.services.trading_service.auto_trader import AutoTradeRouter
from v2.services.trading_service.position_manager import (
    STATUTORY_ROUND_TRIP_DRAG_RATE, PositionManager, PositionState
)
from v2.services.trading_service.reconciliation import ReconciliationService
from v2.services.trading_service.recovery import RestartRecoveryService
from v2.trading.precision_rules import get_pair_spec, round_price, round_qty, validate_order_notional
from v2.trading.subaccount_manager import CoinDCXSubAccountClient, CoinDCXSubAccountManager, SubAccountConfig


async def _create_test_db(tmp_path):
    db_path = str(tmp_path / f"test_exec_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    conn = db.connection
    pos_repo = PositionRepository(conn)
    trade_repo = TradeRepository(conn)
    return db, pos_repo, trade_repo


# =============================================================================
# 1. Precision & Notional Enforcement Tests
# =============================================================================

class TestPrecisionAndNotionalEnforcement:

    def test_tier_1_2_3_precision_rounding(self):
        """Verify tick size and lot step size rounding across Tier 1, Tier 2, and Tier 3 pairs."""
        # Tier 1: BTC/INR (tick ₹0.01, step 0.00001 BTC)
        assert round_price("BTC/INR", 8234567.8912) == 8234567.89
        assert round_qty("BTC/INR", 0.000123456) == 0.00012

        # Tier 2: SOL/INR (tick ₹0.10, step 0.01 SOL)
        assert round_price("SOL/INR", 12543.67) == 12543.7
        assert round_qty("SOL/INR", 1.2345) == 1.23

        # Tier 3: SHIB/INR (tick ₹0.000001, step 1000 SHIB)
        assert round_price("SHIB/INR", 0.0018456) == 0.001846
        assert round_qty("SHIB/INR", 12345.67) == 12000.0

    def test_rejects_order_below_100_inr_notional(self):
        """Assert orders with notional value < ₹100.0 are rejected pre-flight."""
        # Price = 50.0, Qty = 1.0 -> Notional = 50.0 (< 100.0)
        assert not validate_order_notional("BTC/INR", 50.0, 1.0)
        # Price = 8000000.0, Qty = 0.00001 -> Notional = 80.0 (< 100.0)
        assert not validate_order_notional("BTC/INR", 8000000.0, 0.00001)
        # Valid order >= 100.0
        assert validate_order_notional("BTC/INR", 8000000.0, 0.00002)

    @pytest.mark.anyio
    async def test_auto_trader_rejects_notional_below_100(self):
        """AutoTradeRouter rejects signals resulting in < ₹100 notional value."""
        bus = EventBus()
        mgr = CoinDCXSubAccountManager()
        router = AutoTradeRouter(bus=bus, subaccount_manager=mgr, dry_run=True)

        small_signal = {
            "id": "SIG_SMALL_01",
            "coin": "BTC",
            "price": 8000000.0,
            "trade_amount": 50.0,  # ₹50 trade amount < ₹100 minimum
        }

        result = await router.handle_signal(small_signal)
        assert result is not None
        assert result["success"] is False
        assert result["error"] == "ORDER_NOTIONAL_BELOW_MINIMUM"


# =============================================================================
# 2. Sub-account Routing & HMAC Signature Tests
# =============================================================================

class TestSubAccountRoutingAndHMAC:

    def test_subaccount_manager_initializes_4_isolated_clients(self):
        """Verify subaccount manager configures isolated clients for STE, HDA, VCP, and BBS."""
        mgr = CoinDCXSubAccountManager()
        telemetry = mgr.get_all_subaccount_telemetry()

        assert "STE" in telemetry
        assert "HDA" in telemetry
        assert "VCP" in telemetry
        assert "BBS" in telemetry

        assert telemetry["STE"]["wallet_balance_inr"] == 35000.0
        assert telemetry["HDA"]["wallet_balance_inr"] == 30000.0
        assert telemetry["VCP"]["wallet_balance_inr"] == 15000.0
        assert telemetry["BBS"]["wallet_balance_inr"] == 20000.0

    def test_hmac_sha256_header_generation(self):
        """Verify CoinDCXSubAccountClient generates valid X-AUTH-APIKEY and X-AUTH-SIGNATURE headers."""
        config = SubAccountConfig(
            bot_name=BotName.STE,
            subaccount_id="TEST_STE_01",
            api_key="test_api_key",
            api_secret="test_secret_key",
            allocated_wallet_inr=10000.0,
            max_positions=3,
            default_trade_amount_inr=500.0,
        )
        client = CoinDCXSubAccountClient(config)

        headers = client.generate_auth_headers({"side": "buy", "market": "BTCINR"})
        assert "X-AUTH-APIKEY" in headers
        assert "X-AUTH-SIGNATURE" in headers
        assert headers["X-AUTH-APIKEY"] == "test_api_key"
        assert len(headers["X-AUTH-SIGNATURE"]) == 64  # SHA256 hex digest length

    @pytest.mark.anyio
    async def test_subaccount_order_dispatch_and_routing(self):
        """Verify orders are dispatched to the correct sub-account client."""
        mgr = CoinDCXSubAccountManager()
        ste_client = mgr.get_client(BotName.STE)

        order_res = ste_client.place_order("BTC/INR", "BUY", 8000000.0, 0.0001)
        if inspect.isawaitable(order_res):
            order_res = await order_res
        assert order_res["success"] is True
        assert order_res["order"]["subaccount_id"] == "ALPHA_STE_01"
        assert order_res["order"]["bot_name"] == "STE"

    @pytest.mark.anyio
    async def test_live_microcash_http_post_dispatch(self, monkeypatch):
        """Verify that in LIVE_MICROCASH mode, orders are dispatched over async HTTP to CoinDCX."""
        monkeypatch.setenv("DEPLOYMENT_MODE", "LIVE_MICROCASH")
        config = SubAccountConfig(
            bot_name=BotName.STE,
            subaccount_id="ALPHA_STE_01",
            api_key="live_key_123",
            api_secret="live_secret_456",
            allocated_wallet_inr=35000.0,
            max_positions=3,
            default_trade_amount_inr=500.0,
        )
        client = CoinDCXSubAccountClient(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"orders": [{"id": "CDX_ORD_999", "status": "open"}]}
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            res = await client.place_order_async("BTC/INR", "BUY", 8000000.0, 0.0001)
            assert res["success"] is True
            assert res["order"]["live_dispatched"] is True
            assert res["order"]["exchange_response"] == {"orders": [{"id": "CDX_ORD_999", "status": "open"}]}

            # Verify HTTP call arguments
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_headers = mock_post.call_args[1]["headers"]
            assert call_url == "https://api.coindcx.com/exchange/v1/orders/create"
            assert call_headers["X-AUTH-APIKEY"] == "live_key_123"
            assert "X-AUTH-SIGNATURE" in call_headers

    @pytest.mark.anyio
    async def test_paper_mode_bypasses_http_network(self, monkeypatch):
        """Verify that in PAPER mode, no outbound HTTP network socket requests are made."""
        monkeypatch.setenv("DEPLOYMENT_MODE", "PAPER")
        mgr = CoinDCXSubAccountManager()
        client = mgr.get_client(BotName.HDA)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            res = client.place_order("ETH/INR", "BUY", 300000.0, 0.001)
            if inspect.isawaitable(res):
                res = await res
            assert res["success"] is True
            assert res["order"]["status"] == "FILLED"
            mock_post.assert_not_called()

    @pytest.mark.anyio
    async def test_exchange_error_handling_429_and_timeout(self, monkeypatch):
        """Verify graceful error handling on HTTP 429 rate limit and timeout."""
        monkeypatch.setenv("DEPLOYMENT_MODE", "LIVE_MICROCASH")
        config = SubAccountConfig(
            bot_name=BotName.VCP,
            subaccount_id="ALPHA_VCP_01",
            api_key="key",
            api_secret="secret",
            allocated_wallet_inr=15000.0,
            max_positions=2,
            default_trade_amount_inr=400.0,
        )
        client = CoinDCXSubAccountClient(config)

        # 1. Test 429 Rate Limit
        mock_429 = MagicMock()
        mock_429.status_code = 429
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_429):
            res_429 = await client.place_order_async("SOL/INR", "BUY", 12000.0, 0.02)
            assert res_429["success"] is False
            assert res_429["error"] == "RATE_LIMITED"

        # 2. Test Timeout
        import httpx
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Timeout")):
            res_timeout = await client.place_order_async("SOL/INR", "BUY", 12000.0, 0.02)
            assert res_timeout["success"] is False
            assert res_timeout["error"] == "TIMEOUT"


# =============================================================================
# 3. Bracket & Trailing SL/TP Evaluation Tests
# =============================================================================

class TestBracketAndTrailingEvaluation:

    @pytest.mark.anyio
    async def test_take_profit_and_stop_loss_evaluation(self, tmp_path):
        """Assert PositionManager triggers TP and SL correctly on price evaluation."""
        db, pos_repo, trade_repo = await _create_test_db(tmp_path)
        try:
            pm = PositionManager(position_repo=pos_repo, trade_repo=trade_repo)

            pos = await pm.register_position(
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                entry_price=50000.0,
                qty=0.01,
                stop_loss=48000.0,
                take_profit=55000.0,
            )

            # 1. Price at 52000 (No trigger)
            triggers_normal = await pm.evaluate_brackets("BTC/INR", 52000.0)
            assert len(triggers_normal) == 0

            # 2. Price hits Take Profit @ 56000
            triggers_tp = await pm.evaluate_brackets("BTC/INR", 56000.0)
            assert len(triggers_tp) == 1
            assert triggers_tp[0][1] == ExitReason.TAKE_PROFIT

            # 3. Price drops to Stop Loss @ 47000
            triggers_sl = await pm.evaluate_brackets("BTC/INR", 47000.0)
            assert len(triggers_sl) == 1
            assert triggers_sl[0][1] == ExitReason.STOP_LOSS
        finally:
            await db.close()

    @pytest.mark.anyio
    async def test_dynamic_trailing_stop_updates(self, tmp_path):
        """Assert trailing stop moves higher as peak price increases."""
        db, pos_repo, trade_repo = await _create_test_db(tmp_path)
        try:
            pm = PositionManager(position_repo=pos_repo, trade_repo=trade_repo)

            pos = await pm.register_position(
                bot=BotName.HDA,
                coin="ETH",
                pair="ETH/INR",
                entry_price=100000.0,
                qty=0.1,
                stop_loss=90000.0,
            )

            # Update price to 110000 -> Peak = 110000, 3% Trailing Stop = 106700
            ts1 = await pm.update_trailing_stop(pos.id, 110000.0, trailing_pct=0.03)
            assert ts1 == 106700.0

            # Update price to 120000 -> Peak = 120000, 3% Trailing Stop = 116400
            ts2 = await pm.update_trailing_stop(pos.id, 120000.0, trailing_pct=0.03)
            assert ts2 == 116400.0

            # Evaluate at price 115000 (breaches trailing stop of 116400)
            triggers = await pm.evaluate_brackets("ETH/INR", 115000.0)
            assert len(triggers) == 1
            assert triggers[0][1] == ExitReason.STOP_LOSS
        finally:
            await db.close()


# =============================================================================
# 4. Statutory Fee Deduction Tests
# =============================================================================

class TestStatutoryFeeDeduction:

    @pytest.mark.anyio
    async def test_statutory_1_572_pct_drag_deduction(self, tmp_path):
        """Assert 1.572% statutory round-trip drag friction is deducted from realized PnL."""
        db, pos_repo, trade_repo = await _create_test_db(tmp_path)
        try:
            pm = PositionManager(position_repo=pos_repo, trade_repo=trade_repo)

            pos = await pm.register_position(
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                entry_price=100000.0,
                qty=1.0,
            )

            # Close position at 110000.0
            # Entry notional = 100000, Exit notional = 110000, Total traded = 210000
            # Statutory drag = 210000 * (0.01572 / 2) = 1650.60
            # Gross PnL = 10000.0
            # Net PnL = 10000.0 - 1650.60 = 8349.40
            closed_pos, trade = await pm.close_position(pos.id, exit_price=110000.0, exit_reason=ExitReason.TAKE_PROFIT)

            assert trade is not None
            expected_fee_drag = (100000.0 + 110000.0) * (STATUTORY_ROUND_TRIP_DRAG_RATE / 2.0)
            expected_net_pnl = round(10000.0 - expected_fee_drag, 2)

            assert abs(trade.pnl - expected_net_pnl) < 0.05
        finally:
            await db.close()


# =============================================================================
# 5. Restart Recovery & Reconciliation Tests
# =============================================================================

class TestRestartRecoveryAndReconciliation:

    @pytest.mark.anyio
    async def test_restart_recovery_rehydrates_open_positions(self, tmp_path):
        """Assert RestartRecoveryService rehydrates unclosed positions from SQLite."""
        db, pos_repo, trade_repo = await _create_test_db(tmp_path)
        try:
            mgr = CoinDCXSubAccountManager()

            # Insert 2 open positions directly
            p1 = Position(
                id="RECOVER_POS_01",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                qty=0.01,
                entry_price=8000000.0,
                entry_time=None,
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            p2 = Position(
                id="RECOVER_POS_02",
                bot=BotName.HDA,
                coin="ETH",
                pair="ETH/INR",
                qty=0.1,
                entry_price=260000.0,
                entry_time=None,
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            await pos_repo.insert(p1)
            await pos_repo.insert(p2)

            recovery = RestartRecoveryService(position_repo=pos_repo, subaccount_manager=mgr)
            rehydrated = await recovery.rehydrate_state()

            assert len(rehydrated) == 2
            ids = [pos.id for pos in rehydrated]
            assert "RECOVER_POS_01" in ids
            assert "RECOVER_POS_02" in ids
        finally:
            await db.close()

    @pytest.mark.anyio
    async def test_idempotency_prevents_duplicate_orders(self):
        """Assert idempotency key prevents executing duplicate signals."""
        bus = EventBus()
        mgr = CoinDCXSubAccountManager()
        router = AutoTradeRouter(bus=bus, subaccount_manager=mgr, dry_run=True)

        signal = {
            "id": "SIG_DUP_01",
            "coin": "SOL",
            "price": 12000.0,
            "trade_amount": 500.0,
        }

        r1 = await router.handle_signal(signal)
        r2 = await router.handle_signal(signal)

        assert r1["success"] is True
        assert r2["success"] is False
        assert r2["error"] == "DUPLICATE_SIGNAL"

    @pytest.mark.anyio
    async def test_reconciliation_service_runs_and_verifies_clean_state(self, tmp_path):
        """Assert ReconciliationService checks active positions against subaccount telemetry."""
        db, pos_repo, trade_repo = await _create_test_db(tmp_path)
        try:
            mgr = CoinDCXSubAccountManager()

            rec_service = ReconciliationService(position_repo=pos_repo, subaccount_manager=mgr)
            result = await rec_service.reconcile_positions()

            assert "is_clean" in result
            assert result["is_clean"] is True
            assert result["total_active_positions"] == 0
        finally:
            await db.close()
