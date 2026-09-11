"""
tests/test_v2_challenger_m1_rep2.py
Replacement Challenger 2 Adversarial Test Suite for Milestone 1.

Covers:
  1. Dynamic Equity Formula (Cash + MTM - Friction), unrealized PnL, varying tick/lot sizes, zero-cash and drawdown states.
  2. Shared Capital Pool constraints (multi-threaded concurrency race conditions, non-negative pool, available balance clamp, ₹200 min notional).
  3. Startup Hydration Idempotency (5x successive restarts, transitional active positions, deletion/drift resistance, enum status boundaries).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timezone
import math
import os
import threading
import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from v2.bus.event_bus import EventBus
from v2.core.config import V2Config, invalidate_config
from v2.core.types import (
    BotName,
    BotMode,
    Position,
    PositionStatus,
    Trade,
    ExitReason,
)
from v2.repository.db import Database
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.services.portfolio_service.aggregator import PortfolioAggregator
from v2.services.dashboard_service.bot_pipeline import BotPipelineTracker
from v2.services.dashboard_service.aggregator import DashboardAggregator
from v2.services.dashboard_service.service import DashboardService
from v2.trading.subaccount_manager import CoinDCXSubAccountManager, SubAccountConfig
from v2.services.trading_service.auto_trader import AutoTradeRouter
from v2.trading.precision_rules import (
    validate_order_notional,
    round_price,
    round_qty,
    round_qty_up,
    PRECISION_TABLE,
)
from v2.backtest.friction import CoinDCXFrictionModel
from v2.api.router import router as main_router, init_router
from v2.api.dashboard_routes import router as dashboard_router, init_dashboard_routes
from v2.api.production_routes import router as production_router, init_production_routes


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_db_env(tmp_path):
    """Isolated SQLite database and repository environment."""
    db_file = str(tmp_path / f"challenger_rep2_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_file)
    await db.open()

    conn = db.connection
    pos_repo = PositionRepository(conn)
    trade_repo = TradeRepository(conn)
    bus = EventBus()
    cfg = V2Config(v2_trading_enabled=True)

    yield {
        "db": db,
        "conn": conn,
        "pos_repo": pos_repo,
        "trade_repo": trade_repo,
        "bus": bus,
        "cfg": cfg,
    }

    await db.close()


# =============================================================================
# 1. Dynamic Equity & Mark-to-Market Stress Testing
# =============================================================================

class TestDynamicEquityAndMTMValuationsRep2:

    def test_dynamic_equity_zero_cash_and_99pct_drawdown(self):
        """
        Stress test: 100% of cash deployed, followed by catastrophic 99% collapse of the coin.
        Total cash is 0, MTM is 1% of entry. Total AUM must equal Cash + MTM without negative crash.
        """
        now = datetime.now(timezone.utc)
        # Entry notional = 100,000 INR
        pos = Position(
            id="pos-crash",
            bot=BotName.STE,
            coin="LUNA",
            pair="LUNA/INR",
            qty=1000.0,
            entry_price=100.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=1.0,  # 99% crash: MTM = 1,000 INR
            unrealised_pnl=-99000.0,
        )

        base_cash = 100000.0
        snapshot = PortfolioAggregator.aggregate(
            positions=[pos],
            closed_trades=[],
            base_cash=base_cash,
        )

        # Deployed = 100,000
        # Cash = 100,000 - 100,000 = 0.0
        # Total AUM = 0.0 + 100,000 + (-99,000) = 1,000.0
        assert snapshot.total_deployed == 100000.0
        assert snapshot.total_cash == 0.0
        assert snapshot.total_unrealised_pnl == -99000.0
        assert snapshot.total_aum == 1000.0

    def test_dynamic_equity_1000pct_gain_on_micro_penny_coin(self):
        """
        Stress test: 10x gain on a micro-penny coin (e.g. PEPE) with millions of units.
        Verifies precision and dynamic total AUM calculation.
        """
        now = datetime.now(timezone.utc)
        pos = Position(
            id="pos-pepe-moon",
            bot=BotName.BBS,
            coin="PEPE",
            pair="PEPE/INR",
            qty=10000000.0,  # 10M PEPE
            entry_price=0.00020,  # Deployed: 2,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=0.00200,  # 10x price: MTM = 20,000 INR
            unrealised_pnl=18000.0,
        )

        base_cash = 10000.0
        snapshot = PortfolioAggregator.aggregate(
            positions=[pos],
            closed_trades=[],
            base_cash=base_cash,
        )

        # Cash = 10,000 - 2,000 = 8,000
        # MTM = 20,000
        # Total AUM = 8,000 + 20,000 = 28,000
        assert snapshot.total_deployed == 2000.0
        assert snapshot.total_cash == 8000.0
        assert snapshot.total_unrealised_pnl == 18000.0
        assert snapshot.total_aum == 28000.0

    def test_dynamic_equity_deep_realized_loss_over_deployment_clamping(self):
        """
        Stress test: Historical closed trades incurred deep losses exceeding base cash.
        Formula Cash = max(0.0, base_cash + total_realised - total_deployed) must clamp cash strictly to 0.0.
        """
        now = datetime.now(timezone.utc)
        closed_loss_trade = Trade(
            id="tr-loss",
            position_id="pos-loss",
            bot=BotName.STE,
            coin="ETH",
            pair="ETH/INR",
            entry_price=300000.0,
            exit_price=100000.0,
            qty=0.5,
            pnl=-100000.0,  # -100k realized loss
            pnl_pct=-66.67,
            entry_time=now,
            exit_time=now,
            exit_reason=ExitReason.STOP_LOSS,
            mode=BotMode.PAPER,
        )

        open_pos = Position(
            id="pos-still-open",
            bot=BotName.HDA,
            coin="SOL",
            pair="SOL/INR",
            qty=1.0,
            entry_price=10000.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=10000.0,
            unrealised_pnl=0.0,
        )

        # Base cash = 50,000. Total realized = -100,000. Deployed = 10,000.
        # Raw Cash = 50,000 - 100,000 - 10,000 = -60,000.
        snapshot = PortfolioAggregator.aggregate(
            positions=[open_pos],
            closed_trades=[closed_loss_trade],
            base_cash=50000.0,
        )

        # Must clamp cash to 0.0, never negative
        assert snapshot.total_cash == 0.0
        assert snapshot.total_realised_pnl == -100000.0
        assert snapshot.total_deployed == 10000.0
        # Total AUM = 0.0 + 10,000 + 0.0 = 10,000
        assert snapshot.total_aum == 10000.0

    def test_dynamic_equity_invalid_prices_fallback_safety(self):
        """
        Verify that negative, zero, or None current_price safely defaults to entry_price.
        """
        now = datetime.now(timezone.utc)
        pos_neg = Position(
            id="pos-neg-price",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.01,
            entry_price=5000000.0,  # 50,000
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=-500.0,  # Malformed negative price
            unrealised_pnl=None,
        )

        snapshot = PortfolioAggregator.aggregate(
            positions=[pos_neg],
            closed_trades=[],
            base_cash=100000.0,
        )

        # When current_price <= 0, mark_price defaults to entry_price (5,000,000.0)
        assert snapshot.total_deployed == 50000.0
        assert snapshot.total_cash == 50000.0
        assert snapshot.total_unrealised_pnl == 0.0
        assert snapshot.total_aum == 100000.0


# =============================================================================
# 2. Shared Capital Pool Concurrency & Constraints
# =============================================================================

class TestSharedCapitalPoolConcurrencyRep2:

    def test_concurrent_multi_threaded_order_race_condition(self):
        """
        Adversarial Concurrency Test:
        20 concurrent threads across 4 bots all attempt to place a ₹200 order simultaneously.
        The shared capital pool starts with exactly ₹500.00.
        Invariant: Exactly 2 orders must succeed (2 * 200 = 400 INR deployed, 100 INR remaining).
        18 orders must fail with INSUFFICIENT_SUBACCOUNT_BALANCE.
        The available balance must be exactly 100.00 INR (NEVER negative).
        """
        sub_mgr = CoinDCXSubAccountManager()
        sub_mgr._shared_pool_state["wallet_balance_inr"] = 500.0
        sub_mgr._shared_pool_state["deployed_capital_inr"] = 0.0

        bots = [BotName.STE, BotName.HDA, BotName.VCP, BotName.BBS]
        results = []
        lock = threading.Lock()

        def worker(thread_idx: int):
            bot = bots[thread_idx % len(bots)]
            client = sub_mgr.get_client(bot)
            res = client.place_order(
                pair="ETH/INR",
                side="BUY",
                price=200000.0,
                qty=0.001,  # Notional: ₹200.00
                client_order_id=f"concurrent-{thread_idx}",
            )
            with lock:
                results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r.get("success") is True]
        failures = [r for r in results if r.get("success") is False]

        assert len(successes) == 2, f"Expected exactly 2 successes, got {len(successes)}"
        assert len(failures) == 18, f"Expected 18 failures, got {len(failures)}"

        for f in failures:
            assert f["error"] == "INSUFFICIENT_SUBACCOUNT_BALANCE"

        client_check = sub_mgr.get_client(BotName.STE)
        assert client_check.available_balance_inr == 100.0
        assert client_check.available_balance_inr >= 0.0

    def test_dynamic_order_size_update_strictly_clamps_to_200(self):
        """
        Verify update_order_size() enforces minimum ₹200 ceiling even when requested lower.
        """
        sub_mgr = CoinDCXSubAccountManager()

        # Attempt to set order size to ₹50
        sub_mgr.update_order_size(50.0)
        for bot in [BotName.STE, BotName.HDA, BotName.VCP, BotName.BBS]:
            client = sub_mgr.get_client(bot)
            assert client.config.default_trade_amount_inr == 200.0

        # Attempt to set order size to negative
        sub_mgr.update_order_size(-500.0)
        for bot in [BotName.STE, BotName.HDA, BotName.VCP, BotName.BBS]:
            client = sub_mgr.get_client(bot)
            assert client.config.default_trade_amount_inr == 200.0

    def test_sequential_capital_depletion_and_recovery(self):
        """
        Simulate draining the capital pool order-by-order and recovering funds on position exit.
        """
        sub_mgr = CoinDCXSubAccountManager()
        sub_mgr._shared_pool_state["wallet_balance_inr"] = 1000.0
        sub_mgr._shared_pool_state["deployed_capital_inr"] = 0.0
        client = sub_mgr.get_client(BotName.VCP)

        # Place 4 orders of ₹200 = ₹800 deployed
        for i in range(4):
            res = client.place_order(pair="SOL/INR", side="BUY", price=10000.0, qty=0.02)  # ₹200
            assert res["success"] is True

        assert client.available_balance_inr == 200.0

        # 5th order of ₹200 = ₹1000 deployed (pool fully exhausted)
        res5 = client.place_order(pair="SOL/INR", side="BUY", price=10000.0, qty=0.02)
        assert res5["success"] is True
        assert client.available_balance_inr == 0.0

        # 6th order must be rejected
        res6 = client.place_order(pair="SOL/INR", side="BUY", price=10000.0, qty=0.02)
        assert res6["success"] is False
        assert res6["error"] == "INSUFFICIENT_SUBACCOUNT_BALANCE"

        # Now simulate closing one position with a profit of +50 INR
        client.close_position_fill(notional_returned=200.0, realized_pnl=50.0)

        # Deployed = 1000 - 200 = 800. Wallet = 1000 + 50 = 1050. Available = 250.
        assert client.available_balance_inr == 250.0

        # Now an order of ₹200 can succeed again
        res7 = client.place_order(pair="SOL/INR", side="BUY", price=10000.0, qty=0.02)
        assert res7["success"] is True
        assert client.available_balance_inr == 50.0


# =============================================================================
# 3. Startup Hydration Idempotency & Lifecycle Stress
# =============================================================================

class TestStartupHydrationIdempotencyRep2:

    @pytest.mark.anyio
    async def test_five_successive_hydrations_zero_drift(self, test_db_env):
        """
        Stress test: Execute sync_from_repository() 5 times in a loop.
        Verify that counts, deployed capital, and bot states never drift or accumulate.
        """
        env = test_db_env
        pos_repo: PositionRepository = env["pos_repo"]
        now = datetime.now(timezone.utc)

        # 2 STE positions (500 + 500 = 1000), 1 BBS position (2000)
        await pos_repo.insert(Position(
            id="p-ste-1", bot=BotName.STE, coin="BTC", pair="BTC/INR", qty=0.0001, entry_price=5000000.0,
            entry_time=now, mode=BotMode.PAPER, status=PositionStatus.OPEN,
        ))
        await pos_repo.insert(Position(
            id="p-ste-2", bot=BotName.STE, coin="ETH", pair="ETH/INR", qty=0.002, entry_price=250000.0,
            entry_time=now, mode=BotMode.PAPER, status=PositionStatus.OPEN,
        ))
        await pos_repo.insert(Position(
            id="p-bbs-1", bot=BotName.BBS, coin="SOL", pair="SOL/INR", qty=0.2, entry_price=10000.0,
            entry_time=now, mode=BotMode.PAPER, status=PositionStatus.OPEN,
        ))

        tracker = BotPipelineTracker()

        for cycle in range(5):
            await tracker.sync_from_repository(pos_repo)
            ste = tracker.get_bot_detail("STE")
            bbs = tracker.get_bot_detail("BBS")
            hda = tracker.get_bot_detail("HDA")
            vcp = tracker.get_bot_detail("VCP")

            assert ste["open_positions"] == 2, f"Failed on cycle {cycle}"
            assert ste["capital_deployed"] == 1000.0, f"Failed on cycle {cycle}"
            assert ste["current_stage"] == "position_manager"

            assert bbs["open_positions"] == 1, f"Failed on cycle {cycle}"
            assert bbs["capital_deployed"] == 2000.0, f"Failed on cycle {cycle}"
            assert bbs["current_stage"] == "position_manager"

            assert hda["open_positions"] == 0, f"Failed on cycle {cycle}"
            assert hda["capital_deployed"] == 0.0, f"Failed on cycle {cycle}"
            assert hda["current_stage"] == "scanner"

            assert vcp["open_positions"] == 0, f"Failed on cycle {cycle}"
            assert vcp["capital_deployed"] == 0.0, f"Failed on cycle {cycle}"

    @pytest.mark.anyio
    async def test_dynamic_add_and_delete_between_hydrations(self, test_db_env):
        """
        Verify that hydration responds accurately when positions are added or removed in SQLite.
        """
        env = test_db_env
        pos_repo: PositionRepository = env["pos_repo"]
        now = datetime.now(timezone.utc)

        tracker = BotPipelineTracker()

        # Step 1: 1 position
        p1 = Position(
            id="pos-step-1", bot=BotName.HDA, coin="SOL", pair="SOL/INR",
            qty=0.1, entry_price=10000.0, entry_time=now, mode=BotMode.PAPER, status=PositionStatus.OPEN,
        )
        await pos_repo.insert(p1)
        await tracker.sync_from_repository(pos_repo)

        hda = tracker.get_bot_detail("HDA")
        assert hda["open_positions"] == 1
        assert hda["capital_deployed"] == 1000.0

        # Step 2: Position is closed in SQLite
        await pos_repo.close_position("pos-step-1", exit_price=11000.0, exit_reason=ExitReason.TAKE_PROFIT)

        # Re-hydrate
        await tracker.sync_from_repository(pos_repo)
        hda_closed = tracker.get_bot_detail("HDA")
        assert hda_closed["open_positions"] == 0
        assert hda_closed["capital_deployed"] == 0.0
        assert hda_closed["current_stage"] == "scanner"
        assert hda_closed["stage_status"] == "IDLE"

    @pytest.mark.anyio
    async def test_e2e_dashboard_overview_positions_sync_and_restart(self, test_db_env, monkeypatch):
        """
        E2E API test for /dashboard/overview:
        Verifies open_positions and open_positions_count match SQLite active positions,
        and remain accurate across consecutive server restarts.
        """
        env = test_db_env
        pos_repo: PositionRepository = env["pos_repo"]
        now = datetime.now(timezone.utc)

        monkeypatch.setenv("DASHBOARD_API_KEY", "challenger-key-rep2")
        invalidate_config()

        # Insert 2 active positions
        await pos_repo.insert(Position(
            id="dash-pos-1", bot=BotName.STE, coin="BTC", pair="BTC/INR",
            qty=0.001, entry_price=5000000.0, entry_time=now, mode=BotMode.PAPER, status=PositionStatus.OPEN,
        ))
        await pos_repo.insert(Position(
            id="dash-pos-2", bot=BotName.VCP, coin="SOL", pair="SOL/INR",
            qty=0.5, entry_price=10000.0, entry_time=now, mode=BotMode.PAPER, status=PositionStatus.CLOSING,
        ))

        bus = env["bus"]
        cfg = env["cfg"]
        dash_service = DashboardService(bus=bus, config=cfg, position_repo=pos_repo)
        bot_tracker = dash_service.bot_tracker
        dash_agg = dash_service.aggregator

        init_dashboard_routes(aggregator=dash_agg, dashboard_service=dash_service, bot_tracker=bot_tracker)
        init_production_routes(controller=None, watchdog=None, config=None, position_repo=pos_repo)
        init_router(position_repo=pos_repo, dashboard_service=dash_service)

        test_app = FastAPI()
        test_app.include_router(main_router, prefix="/api/v2")

        # 1st Startup Hydration
        await bot_tracker.sync_from_repository(pos_repo)

        headers = {"X-API-Key": "challenger-key-rep2"}
        with TestClient(test_app) as client:
            res_overview = client.get("/api/v2/dashboard/overview", headers=headers)
            assert res_overview.status_code == 200
            ov_data = res_overview.json()

            assert ov_data["open_positions_count"] == 2
            assert len(ov_data["open_positions"]) == 2
            ret_ids = {p["id"] for p in ov_data["open_positions"]}
            assert ret_ids == {"dash-pos-1", "dash-pos-2"}

            # 2nd Startup Hydration
            await bot_tracker.sync_from_repository(pos_repo)

            res_overview2 = client.get("/api/v2/dashboard/overview", headers=headers)
            assert res_overview2.status_code == 200
            ov_data2 = res_overview2.json()

            assert ov_data2["open_positions_count"] == 2
            assert len(ov_data2["open_positions"]) == 2
