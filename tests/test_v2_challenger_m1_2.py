"""
tests/test_v2_challenger_m1_2.py
Adversarial test suite for Challenger 2 (Milestone 1).

Covers:
  1. Dynamic Equity Formula (Cash + MTM - Friction), unrealized PnL, varying tick/lot sizes, zero-cash states.
  2. Shared Capital Pool constraints (non-negative pool, available balance clamp, ₹200 min notional across all 4 bots).
  3. Startup Hydration Idempotency (successive restarts, transitional active positions, zero-state resets).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient

from v2.bus.event_bus import EventBus
from v2.core.config import V2Config
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
from v2.services.portfolio_service.service import PortfolioService
from v2.services.dashboard_service.bot_pipeline import BotPipelineTracker
from v2.services.dashboard_service.service import DashboardService
from v2.trading.subaccount_manager import CoinDCXSubAccountManager, SubAccountConfig
from v2.services.trading_service.auto_trader import AutoTradeRouter
from v2.trading.precision_rules import (
    validate_order_notional,
    round_price,
    round_qty,
    round_qty_up,
)
from v2.backtest.friction import CoinDCXFrictionModel


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def sqlite_env(tmp_path):
    """Isolated SQLite database and repository environment."""
    db_file = str(tmp_path / f"challenger_m1_2_{uuid.uuid4().hex[:6]}.db")
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
# 1. Dynamic Equity Formula & Mark-to-Market Valuations
# =============================================================================

class TestDynamicEquityAndMTMValuations:

    def test_dynamic_equity_positive_unrealized_pnl(self):
        """Verify dynamic equity accurately computes Cash + MTM under +10% unrealized PnL."""
        now = datetime.now(timezone.utc)
        pos = Position(
            id="pos-btc-bull",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.01,
            entry_price=5000000.0,  # Deployed: 50,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=5500000.0,  # MTM: 55,000 INR (+5,000)
            unrealised_pnl=5000.0,
        )

        base_cash = 100000.0
        snapshot = PortfolioAggregator.aggregate(
            positions=[pos],
            closed_trades=[],
            base_cash=base_cash,
        )

        # Expected:
        # Deployed = 50,000
        # Cash = base_cash - deployed = 100,000 - 50,000 = 50,000
        # MTM = 55,000
        # Total AUM = Cash + MTM = 50,000 + 55,000 = 105,000
        assert snapshot.total_deployed == 50000.0
        assert snapshot.total_cash == 50000.0
        assert snapshot.total_unrealised_pnl == 5000.0
        assert snapshot.total_aum == 105000.0

    def test_dynamic_equity_negative_unrealized_pnl(self):
        """Verify dynamic equity accurately computes Cash + MTM under -15% unrealized drawdown."""
        now = datetime.now(timezone.utc)
        pos = Position(
            id="pos-eth-bear",
            bot=BotName.HDA,
            coin="ETH",
            pair="ETH/INR",
            qty=0.1,
            entry_price=300000.0,  # Deployed: 30,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=255000.0,  # MTM: 25,500 INR (-4,500)
            unrealised_pnl=-4500.0,
        )

        base_cash = 100000.0
        snapshot = PortfolioAggregator.aggregate(
            positions=[pos],
            closed_trades=[],
            base_cash=base_cash,
        )

        # Expected:
        # Deployed = 30,000
        # Cash = 100,000 - 30,000 = 70,000
        # MTM = 25,500
        # Total AUM = Cash + MTM = 70,000 + 25,500 = 95,500
        assert snapshot.total_deployed == 30000.0
        assert snapshot.total_cash == 70000.0
        assert snapshot.total_unrealised_pnl == -4500.0
        assert snapshot.total_aum == 95500.0

    def test_dynamic_equity_zero_cash_state(self):
        """Verify dynamic equity handles 100% capital deployment (zero cash state)."""
        now = datetime.now(timezone.utc)
        pos = Position(
            id="pos-sol-max",
            bot=BotName.VCP,
            coin="SOL",
            pair="SOL/INR",
            qty=10.0,
            entry_price=10000.0,  # Deployed: 100,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=10500.0,  # MTM: 105,000 INR (+5,000)
            unrealised_pnl=5000.0,
        )

        base_cash = 100000.0
        snapshot = PortfolioAggregator.aggregate(
            positions=[pos],
            closed_trades=[],
            base_cash=base_cash,
        )

        # Expected:
        # Deployed = 100,000
        # Cash = max(0.0, 100,000 - 100,000) = 0.0
        # Total AUM = 0.0 + 105,000 = 105,000
        assert snapshot.total_cash == 0.0
        assert snapshot.total_deployed == 100000.0
        assert snapshot.total_aum == 105000.0
        assert snapshot.capital_utilisation == 95.24  # 100000 / 105000 * 100

    def test_dynamic_equity_negative_cash_clamping(self):
        """Verify total_cash never becomes negative when deployed capital exceeds cash."""
        now = datetime.now(timezone.utc)
        pos = Position(
            id="pos-over-deployed",
            bot=BotName.BBS,
            coin="BTC",
            pair="BTC/INR",
            qty=0.03,
            entry_price=5000000.0,  # Deployed: 150,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=5000000.0,
            unrealised_pnl=0.0,
        )

        base_cash = 100000.0  # Less than deployed
        snapshot = PortfolioAggregator.aggregate(
            positions=[pos],
            closed_trades=[],
            base_cash=base_cash,
        )

        # Cash is strictly clamped to >= 0.0
        assert snapshot.total_cash == 0.0
        assert snapshot.total_deployed == 150000.0
        assert snapshot.total_aum == 150000.0

    def test_dynamic_equity_multi_coin_varying_tick_sizes(self):
        """Stress-test MTM valuation across multi-coin portfolio with extreme tick/step sizes."""
        now = datetime.now(timezone.utc)
        positions = [
            # 1. High price, fine lot (BTC)
            Position(
                id="pos-btc",
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                qty=0.00045,
                entry_price=5555555.0,  # Deployed = 2499.99975
                entry_time=now,
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
                current_price=5600000.0,  # MTM = 2520.0
                unrealised_pnl=round((5600000.0 - 5555555.0) * 0.00045, 4),
            ),
            # 2. Medium price, standard lot (SOL)
            Position(
                id="pos-sol",
                bot=BotName.HDA,
                coin="SOL",
                pair="SOL/INR",
                qty=0.25,
                entry_price=12345.67,  # Deployed = 3086.4175
                entry_time=now,
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
                current_price=12500.00,  # MTM = 3125.0
                unrealised_pnl=round((12500.00 - 12345.67) * 0.25, 4),
            ),
            # 3. Unit lot coin (DOGE)
            Position(
                id="pos-doge",
                bot=BotName.VCP,
                coin="DOGE",
                pair="DOGE/INR",
                qty=150.0,
                entry_price=14.50,  # Deployed = 2175.0
                entry_time=now,
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
                current_price=16.20,  # MTM = 2430.0
                unrealised_pnl=round((16.20 - 14.50) * 150.0, 4),
            ),
            # 4. Micro-penny coin with step 1000 (SHIB)
            Position(
                id="pos-shib",
                bot=BotName.BBS,
                coin="SHIB",
                pair="SHIB/INR",
                qty=2000000.0,
                entry_price=0.001850,  # Deployed = 3700.0
                entry_time=now,
                mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
                current_price=0.001720,  # MTM = 3440.0
                unrealised_pnl=round((0.001720 - 0.001850) * 2000000.0, 4),
            ),
        ]

        snapshot = PortfolioAggregator.aggregate(
            positions=positions,
            closed_trades=[],
            base_cash=100000.0,
        )

        expected_deployed = sum(p.qty * p.entry_price for p in positions)
        expected_mtm = sum(p.qty * p.current_price for p in positions)
        expected_unrealised = sum(p.unrealised_pnl for p in positions)
        expected_cash = 100000.0 - expected_deployed
        expected_aum = expected_cash + expected_mtm

        assert snapshot.total_deployed == round(expected_deployed, 2)
        assert snapshot.total_cash == round(expected_cash, 2)
        assert snapshot.total_unrealised_pnl == round(expected_unrealised, 2)
        assert snapshot.total_aum == round(expected_aum, 2)
        assert len(snapshot.positions_by_bot["STE"]) == 1
        assert len(snapshot.positions_by_bot["HDA"]) == 1
        assert len(snapshot.positions_by_bot["VCP"]) == 1
        assert len(snapshot.positions_by_bot["BBS"]) == 1

    def test_dynamic_equity_missing_or_zero_current_price_fallback(self):
        """Verify PortfolioAggregator falls back safely to entry_price when current_price is None or 0."""
        now = datetime.now(timezone.utc)
        pos_none = Position(
            id="pos-none-px",
            bot=BotName.STE,
            coin="ADA",
            pair="ADA/INR",
            qty=100.0,
            entry_price=50.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=None,
            unrealised_pnl=None,
        )
        pos_zero = Position(
            id="pos-zero-px",
            bot=BotName.STE,
            coin="DOT",
            pair="DOT/INR",
            qty=10.0,
            entry_price=600.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=0.0,
            unrealised_pnl=None,
        )

        snapshot = PortfolioAggregator.aggregate(
            positions=[pos_none, pos_zero],
            closed_trades=[],
            base_cash=100000.0,
        )

        # When current_price is None or 0.0, mark price falls back to entry price:
        # unrealised_pnl falls back to 0.0
        assert snapshot.total_unrealised_pnl == 0.0
        assert snapshot.total_deployed == 11000.0  # (100*50) + (10*600) = 5000 + 6000
        assert snapshot.total_cash == 89000.0
        assert snapshot.total_aum == 100000.0

    def test_dynamic_equity_friction_deduction_audit(self):
        """
        Adversarial audit of statutory friction deduction in portfolio equity:
        - Closed trades have statutory friction deducted from realised PnL.
        - Open positions in PortfolioAggregator aggregate gross MTM (Cash + Deployed + Unrealised).
        """
        now = datetime.now(timezone.utc)
        # Closed trade with friction
        friction_model = CoinDCXFrictionModel()
        pnl_data = friction_model.calculate_trade_net_pnl(
            entry_price=100.0,
            exit_price=110.0,
            position_size_qty=10.0,
        )
        closed_trade = Trade(
            id="tr-01",
            position_id="pos-old-01",
            bot=BotName.STE,
            coin="SOL",
            pair="SOL/INR",
            entry_price=100.0,
            exit_price=110.0,
            qty=10.0,
            pnl=pnl_data["net_pnl"],  # Net of 1.572% friction
            pnl_pct=pnl_data["net_pnl_pct"],
            entry_time=now,
            exit_time=now,
            exit_reason=ExitReason.TAKE_PROFIT,
            mode=BotMode.PAPER,
        )

        open_pos = Position(
            id="pos-active-01",
            bot=BotName.STE,
            coin="SOL",
            pair="SOL/INR",
            qty=5.0,
            entry_price=100.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=110.0,
            unrealised_pnl=50.0,  # Gross unrealized PnL: (110 - 100) * 5
        )

        snapshot = PortfolioAggregator.aggregate(
            positions=[open_pos],
            closed_trades=[closed_trade],
            base_cash=10000.0,
        )

        # Deployed = 500.0
        # Realised = pnl_data["net_pnl"] (post-friction, approx +67.07 INR rather than gross +100 INR)
        assert snapshot.total_realised_pnl < 100.0  # Verifies friction is deducted from realised PnL
        assert snapshot.total_cash == round(10000.0 + pnl_data["net_pnl"] - 500.0, 2)
        # Unrealised PnL on open position is gross MTM (+50.0)
        assert snapshot.total_unrealised_pnl == 50.0


# =============================================================================
# 2. Shared Capital Pool Constraints & Minimum ₹200 Notional
# =============================================================================

class TestSharedCapitalPoolAndMinNotional:

    def test_shared_capital_pool_never_negative(self):
        """Verify available balance never drops below 0.0 even under excessive simulated deployment."""
        sub_mgr = CoinDCXSubAccountManager()
        client = sub_mgr.get_client(BotName.STE)

        # Set shared state wallet to 500.0
        sub_mgr._shared_pool_state["wallet_balance_inr"] = 500.0
        sub_mgr._shared_pool_state["deployed_capital_inr"] = 0.0

        assert client.available_balance_inr == 500.0

        # Simulate deploying 600.0 (exceeding balance)
        sub_mgr._shared_pool_state["deployed_capital_inr"] = 600.0

        # Must clamp strictly to 0.0, NEVER negative
        assert client.available_balance_inr == 0.0

    def test_shared_capital_rejects_orders_exceeding_available_pool(self):
        """Verify order is rejected when required notional exceeds available pool."""
        sub_mgr = CoinDCXSubAccountManager()
        client = sub_mgr.get_client(BotName.HDA)

        sub_mgr._shared_pool_state["wallet_balance_inr"] = 300.0
        sub_mgr._shared_pool_state["deployed_capital_inr"] = 150.0
        # Available = 150.0

        # Attempt placing order of ₹200.00 (exceeds available ₹150.00)
        res = client.place_order(
            pair="SOL/INR",
            side="BUY",
            price=10000.0,
            qty=0.02,  # Notional: ₹200.00
        )

        assert res["success"] is False
        assert res["error"] == "INSUFFICIENT_SUBACCOUNT_BALANCE"
        assert "exceeds available capital pool balance" in res["message"]

    @pytest.mark.anyio
    async def test_min_notional_200_enforcement_all_bots(self):
        """Verify ₹200 minimum notional enforcement across all 4 production bots (STE, HDA, VCP, BBS)."""
        sub_mgr = CoinDCXSubAccountManager()

        for bot in [BotName.STE, BotName.HDA, BotName.VCP, BotName.BBS]:
            client = sub_mgr.get_client(bot)

            # Test 1: Direct order with notional = ₹100.00 (below ₹200.00) -> MUST FAIL
            res_below = client.place_order(
                pair="ETH/INR",
                side="BUY",
                price=200000.0,
                qty=0.0005,  # ₹100.00
            )
            assert res_below["success"] is False
            assert res_below["error"] == "ORDER_NOTIONAL_BELOW_MINIMUM"

            # Test 2: Direct order with notional = ₹199.99 (below ₹200.00) -> MUST FAIL
            res_199 = client.place_order(
                pair="ETH/INR",
                side="BUY",
                price=199990.0,
                qty=0.001,  # ₹199.99
            )
            assert res_199["success"] is False
            assert res_199["error"] == "ORDER_NOTIONAL_BELOW_MINIMUM"

            # Test 3: Direct order with notional = ₹200.00 -> MUST SUCCEED
            res_exact = client.place_order(
                pair="ETH/INR",
                side="BUY",
                price=200000.0,
                qty=0.001,  # ₹200.00
            )
            assert res_exact["success"] is True
            assert res_exact["order"]["notional_inr"] >= 200.0

    @pytest.mark.anyio
    async def test_auto_trader_rounds_up_sub_200_notional(self):
        """Verify AutoTradeRouter rounds quantity UP to meet ₹200 notional invariant."""
        bus = EventBus()
        sub_mgr = CoinDCXSubAccountManager()
        sub_mgr._shared_pool_state["wallet_balance_inr"] = 100000.0
        sub_mgr._shared_pool_state["deployed_capital_inr"] = 0.0

        router = AutoTradeRouter(bus=bus, subaccount_manager=sub_mgr, dry_run=True)

        for bot_name in ["STE", "HDA", "VCP", "BBS"]:
            signal = {
                "id": f"sig-{bot_name.lower()}-roundup",
                "coin": "DOGE",
                "pair": "DOGE/INR",
                "price": 10.0,
                "trade_amount": 195.0,  # ₹195 < ₹200
                "target_bot": bot_name,
            }
            res = await router.handle_signal(signal)
            assert res is not None
            assert res["success"] is True
            # DOGE lot step is 1.0; 195 / 10 = 19.5 -> rounded UP to 20 DOGE = ₹200.00
            assert res["qty"] == 20.0
            assert res["notional"] >= 200.0

    def test_precision_rules_min_notional_boundary_cases(self):
        """Stress test validate_order_notional on boundary numbers."""
        # BTC/INR
        assert validate_order_notional("BTC/INR", 5000000.0, 0.000039, min_notional=200.0) is False  # 195.0
        assert validate_order_notional("BTC/INR", 5000000.0, 0.000040, min_notional=200.0) is True   # 200.0

        # PEPE/INR
        assert validate_order_notional("PEPE/INR", 0.0008, 200000.0, min_notional=200.0) is False   # 160.0
        assert validate_order_notional("PEPE/INR", 0.0008, 250000.0, min_notional=200.0) is True    # 200.0


# =============================================================================
# 3. Startup Hydration Idempotency
# =============================================================================

class TestStartupHydrationIdempotency:

    @pytest.mark.anyio
    async def test_successive_hydration_preserves_idempotency(self, sqlite_env):
        """
        Verify that running sync_from_repository multiple times in succession
        preserves exact position counts and capital without multiplying or duplicating.
        """
        env = sqlite_env
        pos_repo: PositionRepository = env["pos_repo"]

        now = datetime.now(timezone.utc)
        # Populate SQLite with known positions across 4 bots
        p1 = Position(
            id="hyd-pos-01",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.001,
            entry_price=5000000.0,  # 5,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=5000000.0,
        )
        p2 = Position(
            id="hyd-pos-02",
            bot=BotName.STE,
            coin="ETH",
            pair="ETH/INR",
            qty=0.02,
            entry_price=300000.0,  # 6,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=300000.0,
        )
        p3 = Position(
            id="hyd-pos-03",
            bot=BotName.HDA,
            coin="SOL",
            pair="SOL/INR",
            qty=0.5,
            entry_price=10000.0,  # 5,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=10000.0,
        )
        p4 = Position(
            id="hyd-pos-04",
            bot=BotName.VCP,
            coin="ADA",
            pair="ADA/INR",
            qty=100.0,
            entry_price=40.0,  # 4,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=40.0,
        )
        # Closed position (MUST be ignored)
        p_closed = Position(
            id="hyd-pos-closed",
            bot=BotName.BBS,
            coin="DOGE",
            pair="DOGE/INR",
            qty=500.0,
            entry_price=15.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.CLOSED,
            current_price=15.0,
        )

        await pos_repo.insert(p1)
        await pos_repo.insert(p2)
        await pos_repo.insert(p3)
        await pos_repo.insert(p4)
        await pos_repo.insert(p_closed)

        tracker = BotPipelineTracker()

        # ── First Hydration ──
        await tracker.sync_from_repository(pos_repo)

        ste_bot = tracker.get_bot_detail("STE")
        hda_bot = tracker.get_bot_detail("HDA")
        vcp_bot = tracker.get_bot_detail("VCP")
        bbs_bot = tracker.get_bot_detail("BBS")

        assert ste_bot["open_positions"] == 2
        assert ste_bot["capital_deployed"] == 11000.0
        assert ste_bot["current_stage"] == "position_manager"
        assert ste_bot["stage_status"] == "IN_POSITION"

        assert hda_bot["open_positions"] == 1
        assert hda_bot["capital_deployed"] == 5000.0
        assert hda_bot["current_stage"] == "position_manager"

        assert vcp_bot["open_positions"] == 1
        assert vcp_bot["capital_deployed"] == 4000.0
        assert vcp_bot["current_stage"] == "position_manager"

        assert bbs_bot["open_positions"] == 0
        assert bbs_bot["capital_deployed"] == 0.0
        assert bbs_bot["current_stage"] == "scanner"
        assert bbs_bot["stage_status"] == "IDLE"

        # ── Second Hydration (Simulating immediate server restart) ──
        await tracker.sync_from_repository(pos_repo)

        ste_bot2 = tracker.get_bot_detail("STE")
        hda_bot2 = tracker.get_bot_detail("HDA")
        vcp_bot2 = tracker.get_bot_detail("VCP")
        bbs_bot2 = tracker.get_bot_detail("BBS")

        # Counts and capital MUST be 100% identical, NOT doubled
        assert ste_bot2["open_positions"] == 2
        assert ste_bot2["capital_deployed"] == 11000.0

        assert hda_bot2["open_positions"] == 1
        assert hda_bot2["capital_deployed"] == 5000.0

        assert vcp_bot2["open_positions"] == 1
        assert vcp_bot2["capital_deployed"] == 4000.0

        assert bbs_bot2["open_positions"] == 0
        assert bbs_bot2["capital_deployed"] == 0.0

        # ── Third Hydration (Triple restart stress) ──
        await tracker.sync_from_repository(pos_repo)
        ste_bot3 = tracker.get_bot_detail("STE")
        assert ste_bot3["open_positions"] == 2
        assert ste_bot3["capital_deployed"] == 11000.0

    @pytest.mark.anyio
    async def test_startup_hydration_handles_all_transitional_statuses(self, sqlite_env):
        """Verify all valid non-CLOSED enum statuses (OPEN, CLOSING) are hydrated."""
        env = sqlite_env
        pos_repo: PositionRepository = env["pos_repo"]

        now = datetime.now(timezone.utc)
        statuses = [
            (PositionStatus.OPEN, "pos-trans-open-1"),
            (PositionStatus.CLOSING, "pos-trans-closing-2"),
        ]

        for st, pid in statuses:
            p = Position(
                id=pid,
                bot=BotName.STE,
                coin="BTC",
                pair="BTC/INR",
                qty=0.0001,
                entry_price=5000000.0,
                entry_time=now,
                mode=BotMode.PAPER,
                status=st,
                current_price=5000000.0,
            )
            await pos_repo.insert(p)

        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(pos_repo)

        ste = tracker.get_bot_detail("STE")
        assert ste["open_positions"] == 2
        assert ste["capital_deployed"] == 1000.0  # 2 * 500

    @pytest.mark.anyio
    async def test_sqlite_unsupported_transitional_status_adversarial_finding(self, sqlite_env):
        """
        Adversarial finding:
        PROJECT.md and worker_m1 claim lifecycle includes PENDING_ENTRY and PENDING_EXIT.
        However, PositionStatus enum only defines OPEN, CLOSING, CLOSED.
        If SQLite contains raw 'PENDING_ENTRY' status, PositionRepository._row_to_position
        raises ValueError: 'PENDING_ENTRY' is not a valid PositionStatus.
        """
        env = sqlite_env
        conn = env["conn"]
        pos_repo: PositionRepository = env["pos_repo"]

        now = datetime.now(timezone.utc).isoformat()
        # Insert a raw row directly via SQL with 'PENDING_ENTRY'
        await conn.execute(
            """
            INSERT INTO positions (id, bot, coin, pair, qty, entry_price, entry_time, mode, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("pos-raw-pending-entry", "STE", "BTC", "BTC/INR", 0.001, 5000000.0, now, "PAPER", "PENDING_ENTRY"),
        )
        await conn.commit()

        # Calling get_active_positions() attempts PositionStatus('PENDING_ENTRY')
        # which raises ValueError because PENDING_ENTRY is not in PositionStatus enum!
        with pytest.raises(ValueError, match="is not a valid PositionStatus"):
            await pos_repo.get_active_positions()

    @pytest.mark.anyio
    async def test_startup_hydration_resets_stale_in_memory_state(self, sqlite_env):
        """Verify hydration correctly clears prior in-memory state when DB has fewer/zero positions."""
        env = sqlite_env
        pos_repo: PositionRepository = env["pos_repo"]

        tracker = BotPipelineTracker()
        # Artificially set stale in-memory state
        tracker._bots["STE"].open_positions = 5
        tracker._bots["STE"].capital_deployed = 50000.0
        tracker._bots["STE"].stage_status = "IN_POSITION"
        tracker._bots["STE"].current_stage = "position_manager"

        # Database is completely empty
        await tracker.sync_from_repository(pos_repo)

        ste = tracker.get_bot_detail("STE")
        assert ste["open_positions"] == 0
        assert ste["capital_deployed"] == 0.0
        assert ste["current_stage"] == "scanner"
        assert ste["stage_status"] == "IDLE"

    @pytest.mark.anyio
    async def test_startup_hydration_resilience_to_string_and_enum_bot_names(self, sqlite_env):
        """Verify sync_from_repository handles string 'ste', 'STE', and BotName.STE seamlessly."""
        env = sqlite_env
        pos_repo: PositionRepository = env["pos_repo"]
        now = datetime.now(timezone.utc)

        # Mock position-like objects with various bot representation types
        class RawPos:
            def __init__(self, bot, deployed):
                self.bot = bot
                self.deployed_capital = deployed
                self.qty = 1.0
                self.entry_price = deployed
                self.coin = "BTC"
                self.entry_time = now

        raw_positions = [
            RawPos("ste", 1000.0),
            RawPos("STE", 1500.0),
            RawPos(BotName.STE, 2000.0),
        ]

        tracker = BotPipelineTracker()
        await tracker.sync_from_repository(raw_positions)

        ste = tracker.get_bot_detail("STE")
        assert ste["open_positions"] == 3
        assert ste["capital_deployed"] == 4500.0

    @pytest.mark.anyio
    async def test_e2e_api_endpoints_hydration_and_restarts(self, sqlite_env, monkeypatch):
        """
        Full End-to-End API test verifying that:
        1. /positions/open returns all non-closed active positions.
        2. /production/status reflects active position count and deployed capital.
        3. Successive server restart / hydration preserves exact metrics without multiplication.
        """
        from fastapi import FastAPI
        from v2.api.router import router as main_router, init_router
        from v2.api.dashboard_routes import router as dashboard_router, init_dashboard_routes
        from v2.api.production_routes import router as production_router, init_production_routes
        from v2.services.dashboard_service.aggregator import DashboardAggregator

        env = sqlite_env
        pos_repo = env["pos_repo"]
        now = datetime.now(timezone.utc)

        monkeypatch.setenv("DASHBOARD_API_KEY", "test-challenger-key")
        from v2.core.config import invalidate_config
        invalidate_config()

        # Insert 3 active positions across STE and HDA
        p1 = Position(
            id="e2e-pos-01",
            bot=BotName.STE,
            coin="BTC",
            pair="BTC/INR",
            qty=0.001,
            entry_price=5000000.0,  # 5,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=5000000.0,
        )
        p2 = Position(
            id="e2e-pos-02",
            bot=BotName.STE,
            coin="ETH",
            pair="ETH/INR",
            qty=0.01,
            entry_price=300000.0,  # 3,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
            current_price=300000.0,
        )
        p3 = Position(
            id="e2e-pos-03",
            bot=BotName.HDA,
            coin="SOL",
            pair="SOL/INR",
            qty=0.2,
            entry_price=10000.0,  # 2,000 INR
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.CLOSING,  # Non-closed transitional
            current_price=10000.0,
        )
        p_closed = Position(
            id="e2e-pos-closed",
            bot=BotName.VCP,
            coin="ADA",
            pair="ADA/INR",
            qty=100.0,
            entry_price=50.0,
            entry_time=now,
            mode=BotMode.PAPER,
            status=PositionStatus.CLOSED,
            current_price=50.0,
        )
        await pos_repo.insert(p1)
        await pos_repo.insert(p2)
        await pos_repo.insert(p3)
        await pos_repo.insert(p_closed)

        bot_tracker = BotPipelineTracker()
        dash_agg = DashboardAggregator()
        init_dashboard_routes(aggregator=dash_agg, bot_tracker=bot_tracker)
        init_production_routes(controller=None, watchdog=None, config=None, position_repo=pos_repo)
        init_router(position_repo=pos_repo)

        test_app = FastAPI()
        test_app.include_router(main_router, prefix="/api/v2")

        # 1st Startup Hydration
        await bot_tracker.sync_from_repository(pos_repo)

        headers = {"X-API-Key": "test-challenger-key"}
        with TestClient(test_app) as client:
            # Check 1: /positions/open returns exactly 3 non-closed positions
            res_open = client.get("/api/v2/positions/open", headers=headers)
            assert res_open.status_code == 200
            open_pos = res_open.json()
            assert len(open_pos) == 3
            ids = {p["id"] for p in open_pos}
            assert ids == {"e2e-pos-01", "e2e-pos-02", "e2e-pos-03"}
            assert "e2e-pos-closed" not in ids

            # Check 2: /production/status reflects 3 active positions and 10,000 INR deployed
            res_prod = client.get("/api/v2/production/status", headers=headers)
            assert res_prod.status_code == 200
            prod_status = res_prod.json()
            assert prod_status["open_positions_count"] == 3
            assert prod_status["capital_pool_deployed"] == 10000.0

            # 2nd Startup Hydration (Simulating consecutive server restart)
            await bot_tracker.sync_from_repository(pos_repo)

            # Re-verify endpoints after restart
            res_open2 = client.get("/api/v2/positions/open", headers=headers)
            assert len(res_open2.json()) == 3

            res_prod2 = client.get("/api/v2/production/status", headers=headers)
            assert res_prod2.json()["open_positions_count"] == 3
            assert res_prod2.json()["capital_pool_deployed"] == 10000.0
