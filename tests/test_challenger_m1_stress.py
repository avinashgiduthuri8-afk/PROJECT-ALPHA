"""
Empirical Adversarial Stress Suite for Milestone 1.

Target Components:
1. BotPipelineTracker.sync_from_repository()
2. /positions/open API endpoint
3. /dashboard/overview API endpoint
4. PositionRepository.get_active_positions() with mixed statuses
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from v2.core.config import get_config
from v2.core.types import (
    BotMode, BotName, ExitReason, Position, PositionStatus
)
from v2.repository.db import Database
from v2.repository.position_repo import PositionRepository
from v2.repository.trade_repo import TradeRepository
from v2.services.dashboard_service.bot_pipeline import BotPipelineTracker, BotState
from v2.services.dashboard_service.aggregator import DashboardAggregator
from v2.services.dashboard_service.service import DashboardService
from v2.api.router import router as api_router, init_router
from v2.api.dashboard_routes import router as dashboard_router, init_dashboard_routes


class DummyPosition:
    """Mock position object with configurable attributes for stress-testing."""
    def __init__(
        self,
        bot: Any = "STE",
        coin: str = "BTC",
        qty: Any = 1.0,
        entry_price: Any = 1000.0,
        deployed_capital: Any = None,
        status: Any = "OPEN",
        entry_time: Any = None,
    ):
        self.bot = bot
        self.coin = coin
        self.qty = qty
        self.entry_price = entry_price
        self.deployed_capital = deployed_capital
        self.status = status
        self.entry_time = entry_time or datetime.now(timezone.utc)


# ── SECTION 1: BotPipelineTracker.sync_from_repository() Stress Tests ─────────

class TestBotPipelineTrackerSyncStress:

    def test_sync_empty_list_resets_state(self):
        """Verify syncing with empty list cleanly resets all bots to 0 positions and IDLE scanner."""
        tracker = BotPipelineTracker()
        # Seed state first
        ste_bot = tracker._bots["STE"]
        ste_bot.open_positions = 5
        ste_bot.capital_deployed = 50000.0
        ste_bot.current_stage = "position_manager"
        ste_bot.stage_status = "IN_POSITION"

        asyncio.run(tracker.sync_from_repository([]))

        assert ste_bot.open_positions == 0
        assert ste_bot.capital_deployed == 0.0
        assert ste_bot.current_stage == "scanner"
        assert ste_bot.stage_status == "IDLE"

    def test_sync_unsupported_sources(self):
        """Verify non-iterable, non-repository inputs do not crash and log warning."""
        tracker = BotPipelineTracker()
        for invalid_source in [None, 12345, "invalid", object()]:
            asyncio.run(tracker.sync_from_repository(invalid_source))
            assert all(b["open_positions"] == 0 for b in tracker.get_all_bots())

    def test_sync_unknown_bot_names_ignored(self):
        """Verify positions with invalid/unknown bot names are skipped without error."""
        tracker = BotPipelineTracker()
        positions = [
            DummyPosition(bot="UNKNOWN", coin="BTC", qty=1.0, entry_price=100.0),
            DummyPosition(bot="VGX", coin="ETH", qty=1.0, entry_price=100.0),
            DummyPosition(bot="", coin="SOL", qty=1.0, entry_price=100.0),
            DummyPosition(bot=None, coin="DOGE", qty=1.0, entry_price=100.0),
            DummyPosition(bot=12345, coin="ADA", qty=1.0, entry_price=100.0),
            DummyPosition(bot="STE", coin="BTC", qty=2.0, entry_price=500.0),
        ]
        asyncio.run(tracker.sync_from_repository(positions))

        ste_detail = tracker.get_bot_detail("STE")
        assert ste_detail["open_positions"] == 1
        assert ste_detail["capital_deployed"] == 1000.0
        for other_bot in ["HDA", "VCP", "BBS"]:
            assert tracker.get_bot_detail(other_bot)["open_positions"] == 0

    def test_sync_negative_capital_and_zero_values(self):
        """Stress-test negative capital, zero quantity, and explicit deployed_capital overrides."""
        tracker = BotPipelineTracker()
        positions = [
            DummyPosition(bot="HDA", coin="BTC", qty=-2.0, entry_price=100.0),  # -200
            DummyPosition(bot="VCP", coin="ETH", qty=0.0, entry_price=500.0),   # 0
            DummyPosition(bot="BBS", coin="SOL", qty=1.0, entry_price=100.0, deployed_capital=-500.0), # explicit -500
        ]
        asyncio.run(tracker.sync_from_repository(positions))

        hda = tracker.get_bot_detail("HDA")
        assert hda["open_positions"] == 1
        assert hda["capital_deployed"] == -200.0  # Empirical: negative values are accumulated as-is

        vcp = tracker.get_bot_detail("VCP")
        assert vcp["open_positions"] == 1
        assert vcp["capital_deployed"] == 0.0

        bbs = tracker.get_bot_detail("BBS")
        assert bbs["open_positions"] == 1
        assert bbs["capital_deployed"] == -500.0

    def test_sync_direct_list_with_closed_positions_behavior(self):
        """
        Adversarial test: If a caller passes a raw list containing CLOSED positions to sync_from_repository(),
        does sync_from_repository() check pos.status?
        """
        tracker = BotPipelineTracker()
        positions = [
            DummyPosition(bot="STE", coin="BTC", qty=1.0, entry_price=100.0, status="OPEN"),
            DummyPosition(bot="STE", coin="ETH", qty=1.0, entry_price=200.0, status="CLOSED"),
            DummyPosition(bot="STE", coin="SOL", qty=1.0, entry_price=300.0, status="CLOSING"),
        ]
        asyncio.run(tracker.sync_from_repository(positions))

        ste = tracker.get_bot_detail("STE")
        # Empirical finding: sync_from_repository assumes caller pre-filtered non-closed positions!
        # When passed a list containing CLOSED, it counts all 3 items!
        assert ste["open_positions"] == 3

    def test_sync_dict_items_ignored(self):
        """Verify behavior when dicts are passed instead of objects with attributes."""
        tracker = BotPipelineTracker()
        dicts = [
            {"bot": "STE", "coin": "BTC", "qty": 1.0, "entry_price": 100.0, "status": "OPEN"}
        ]
        asyncio.run(tracker.sync_from_repository(dicts))
        ste = tracker.get_bot_detail("STE")
        # Dicts do not have .bot attribute, getattr(d, 'bot', '') returns ''
        assert ste["open_positions"] == 0

    def test_sync_idempotence_and_rehydration(self):
        """Verify that multiple consecutive sync calls cleanly replace previous state."""
        tracker = BotPipelineTracker()

        # Pass 1: 2 positions for STE
        batch_1 = [
            DummyPosition(bot="STE", coin="BTC", qty=1.0, entry_price=1000.0),
            DummyPosition(bot="STE", coin="ETH", qty=1.0, entry_price=2000.0),
        ]
        asyncio.run(tracker.sync_from_repository(batch_1))
        assert tracker.get_bot_detail("STE")["open_positions"] == 2
        assert tracker.get_bot_detail("STE")["capital_deployed"] == 3000.0

        # Pass 2: 1 position for HDA, 0 for STE
        batch_2 = [
            DummyPosition(bot="HDA", coin="SOL", qty=5.0, entry_price=100.0),
        ]
        asyncio.run(tracker.sync_from_repository(batch_2))
        assert tracker.get_bot_detail("STE")["open_positions"] == 0
        assert tracker.get_bot_detail("STE")["capital_deployed"] == 0.0
        assert tracker.get_bot_detail("HDA")["open_positions"] == 1
        assert tracker.get_bot_detail("HDA")["capital_deployed"] == 500.0


# ── SECTION 2: PositionRepository SQLite Status Edge Cases ───────────────────

class TestSQLitePositionRepositoryEdgeCases:

    @pytest.fixture
    def test_db_file(self, tmp_path):
        db_path = str(tmp_path / f"test_stress_{uuid.uuid4().hex[:8]}.db")
        return db_path

    @pytest.mark.asyncio
    async def test_get_active_positions_open_and_closing_statuses(self, test_db_file):
        """Verify that OPEN and CLOSING positions are returned by get_active_positions()."""
        db = Database(test_db_file)
        await db.open()
        try:
            repo = PositionRepository(db.connection)
            now = datetime.now(timezone.utc)

            pos_open = Position(
                id="pos-open-1", bot=BotName.STE, coin="BTC", pair="BTC/INR",
                qty=0.01, entry_price=5000000.0, entry_time=now, mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            pos_closing = Position(
                id="pos-closing-1", bot=BotName.HDA, coin="ETH", pair="ETH/INR",
                qty=0.1, entry_price=250000.0, entry_time=now, mode=BotMode.PAPER,
                status=PositionStatus.CLOSING,
            )
            pos_closed = Position(
                id="pos-closed-1", bot=BotName.VCP, coin="SOL", pair="SOL/INR",
                qty=1.0, entry_price=12000.0, entry_time=now, mode=BotMode.PAPER,
                status=PositionStatus.CLOSED,
            )

            await repo.insert(pos_open)
            await repo.insert(pos_closing)
            await repo.insert(pos_closed)

            active = await repo.get_active_positions()
            active_ids = {p.id for p in active}

            assert "pos-open-1" in active_ids
            assert "pos-closing-1" in active_ids
            assert "pos-closed-1" not in active_ids
            assert len(active) == 2
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_pending_entry_in_sqlite_causes_value_error(self, test_db_file):
        """
        Adversarial edge-case: If SQLite has status='PENDING_ENTRY', what happens?
        Since PositionStatus enum only defines OPEN, CLOSING, CLOSED,
        _row_to_position raises ValueError('PENDING_ENTRY' is not a valid PositionStatus).
        """
        db = Database(test_db_file)
        await db.open()
        try:
            now = datetime.now(timezone.utc).isoformat()
            # Directly execute INSERT with status='PENDING_ENTRY' into SQLite positions table
            await db.connection.execute(
                """
                INSERT INTO positions (id, bot, coin, pair, qty, entry_price, entry_time, mode, status)
                VALUES ('pos-pending-entry-1', 'STE', 'BTC', 'BTC/INR', 0.01, 5000000.0, ?, 'PAPER', 'PENDING_ENTRY')
                """,
                (now,)
            )
            await db.connection.commit()

            repo = PositionRepository(db.connection)
            with pytest.raises(ValueError, match="PENDING_ENTRY"):
                await repo.get_active_positions()
        finally:
            await db.close()


# ── SECTION 3: API Endpoints /positions/open & /dashboard/overview ───────────

class TestAPIEndpointsStress:

    @pytest.fixture
    def test_env(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / f"api_stress_{uuid.uuid4().hex[:8]}.db")
        test_api_key = "test-secret-key-v2"
        monkeypatch.setenv("DASHBOARD_API_KEY", test_api_key)
        from v2.core.config import invalidate_config
        invalidate_config()
        cfg = get_config()

        async def _setup():
            db = Database(db_path)
            await db.open()
            return db

        db = asyncio.run(_setup())
        pos_repo = PositionRepository(db.connection)
        trade_repo = TradeRepository(db.connection)

        from v2.bus.event_bus import EventBus
        bus = EventBus()
        dash_service = DashboardService(
            bus=bus,
            config=cfg,
            position_repo=pos_repo,
        )

        init_router(
            position_repo=pos_repo,
            trade_repo=trade_repo,
            config=cfg,
            dashboard_service=dash_service,
        )

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v2")

        client = TestClient(app)
        yield {
            "client": client,
            "api_key": test_api_key,
            "db": db,
            "pos_repo": pos_repo,
            "dash_service": dash_service,
            "bot_tracker": dash_service.bot_tracker,
        }

        asyncio.run(db.close())

    def test_empty_database_positions_and_overview(self, test_env):
        """Test API behavior when database has 0 positions."""
        client = test_env["client"]
        headers = {"X-API-Key": test_env["api_key"]}

        # /positions/open
        res_pos = client.get("/api/v2/positions/open", headers=headers)
        assert res_pos.status_code == 200
        assert res_pos.json() == []

        # /dashboard/overview
        res_ov = client.get("/api/v2/dashboard/overview", headers=headers)
        assert res_ov.status_code == 200
        data = res_ov.json()
        assert data["status"] == "ok"
        assert data["open_positions_count"] == 0
        assert data["open_positions"] == []
        assert "execution_fleet" in data

    def test_active_and_closed_positions_filtering(self, test_env):
        """Verify /positions/open and /dashboard/overview strictly include active and exclude CLOSED."""
        client = test_env["client"]
        headers = {"X-API-Key": test_env["api_key"]}
        repo = test_env["pos_repo"]
        now = datetime.now(timezone.utc)

        # Insert 1 OPEN, 1 CLOSING, 1 CLOSED
        p_open = Position(
            id="p-open-101", bot=BotName.STE, coin="BTC", pair="BTC/INR",
            qty=0.01, entry_price=5000000.0, entry_time=now, mode=BotMode.PAPER,
            status=PositionStatus.OPEN,
        )
        p_closing = Position(
            id="p-closing-102", bot=BotName.HDA, coin="ETH", pair="ETH/INR",
            qty=0.1, entry_price=250000.0, entry_time=now, mode=BotMode.PAPER,
            status=PositionStatus.CLOSING,
        )
        p_closed = Position(
            id="p-closed-103", bot=BotName.VCP, coin="SOL", pair="SOL/INR",
            qty=1.0, entry_price=12000.0, entry_time=now, mode=BotMode.PAPER,
            status=PositionStatus.CLOSED,
        )

        asyncio.run(repo.insert(p_open))
        asyncio.run(repo.insert(p_closing))
        asyncio.run(repo.insert(p_closed))

        # Check /positions/open
        res_pos = client.get("/api/v2/positions/open", headers=headers)
        assert res_pos.status_code == 200
        positions = res_pos.json()
        ids = {p["id"] for p in positions}
        assert "p-open-101" in ids
        assert "p-closing-102" in ids
        assert "p-closed-103" not in ids
        assert len(positions) == 2

        # Check /dashboard/overview
        res_ov = client.get("/api/v2/dashboard/overview", headers=headers)
        assert res_ov.status_code == 200
        ov_data = res_ov.json()
        assert ov_data["open_positions_count"] == 2
        ov_ids = {p["id"] for p in ov_data["open_positions"]}
        assert "p-open-101" in ov_ids
        assert "p-closing-102" in ov_ids
        assert "p-closed-103" not in ov_ids

    def test_unauthenticated_requests_rejected(self, test_env):
        """Verify security guard: missing or wrong API key returns 401."""
        client = test_env["client"]

        # No header
        res1 = client.get("/api/v2/positions/open")
        assert res1.status_code == 401

        res2 = client.get("/api/v2/dashboard/overview")
        assert res2.status_code == 401

        # Wrong key
        res3 = client.get("/api/v2/positions/open", headers={"X-API-Key": "wrong-key"})
        assert res3.status_code == 401

    def test_pending_entry_in_sqlite_breaks_positions_endpoint(self, test_env):
        """
        Adversarial test: What happens when an unhandled status ('PENDING_ENTRY') exists in SQLite?
        /positions/open calls repo.get_active_positions(), which fails on _row_to_position.
        This triggers a 500 Internal Server Error!
        """
        client = test_env["client"]
        headers = {"X-API-Key": test_env["api_key"]}
        db = test_env["db"]
        now = datetime.now(timezone.utc).isoformat()

        async def _insert_raw():
            await db.connection.execute(
                """
                INSERT INTO positions (id, bot, coin, pair, qty, entry_price, entry_time, mode, status)
                VALUES ('pos-raw-pending', 'STE', 'BTC', 'BTC/INR', 0.01, 5000000.0, ?, 'PAPER', 'PENDING_ENTRY')
                """,
                (now,)
            )
            await db.connection.commit()

        asyncio.run(_insert_raw())

        # In /positions/open: unhandled ValueError turns into HTTP 500
        with pytest.raises(ValueError, match="PENDING_ENTRY"):
            client.get("/api/v2/positions/open", headers=headers)

    def test_overview_with_pending_entry_logs_and_returns_zero_positions(self, test_env):
        """
        Adversarial test: If SQLite contains PENDING_ENTRY, get_overview() catches
        the exception in try..except, logs a warning, and returns open_positions_count = 0.
        All active positions are silently dropped!
        """
        client = test_env["client"]
        headers = {"X-API-Key": test_env["api_key"]}
        db = test_env["db"]
        now = datetime.now(timezone.utc).isoformat()

        async def _insert_raw():
            await db.connection.execute(
                """
                INSERT INTO positions (id, bot, coin, pair, qty, entry_price, entry_time, mode, status)
                VALUES ('pos-raw-pending-ov', 'STE', 'BTC', 'BTC/INR', 0.01, 5000000.0, ?, 'PAPER', 'PENDING_ENTRY')
                """,
                (now,)
            )
            await db.connection.commit()

        asyncio.run(_insert_raw())

        res = client.get("/api/v2/dashboard/overview", headers=headers)
        assert res.status_code == 200
        data = res.json()
        # Because PositionRepository crashed on PENDING_ENTRY, open_positions falls back to empty!
        assert data["open_positions_count"] == 0
        assert data["open_positions"] == []

    def test_capacity_overload_hydration(self, test_env):
        """
        Adversarial test: What happens when positions in SQLite exceed a bot's configured capacity?
        STE capacity is 3. We insert 5 active positions for STE.
        """
        client = test_env["client"]
        headers = {"X-API-Key": test_env["api_key"]}
        repo = test_env["pos_repo"]
        bot_tracker = test_env["bot_tracker"]
        now = datetime.now(timezone.utc)

        for i in range(5):
            pos = Position(
                id=f"pos-ste-overload-{i}", bot=BotName.STE, coin="BTC", pair="BTC/INR",
                qty=0.01, entry_price=5000000.0, entry_time=now, mode=BotMode.PAPER,
                status=PositionStatus.OPEN,
            )
            asyncio.run(repo.insert(pos))

        asyncio.run(bot_tracker.sync_from_repository(repo))
        ste = bot_tracker.get_bot_detail("STE")
        # Tracker does not clamp to max_positions: tracks actual 5 positions
        assert ste["open_positions"] == 5
        assert ste["capital_deployed"] == 250000.0

        res_pos = client.get("/api/v2/positions/open", headers=headers)
        assert res_pos.status_code == 200
        assert len(res_pos.json()) == 5

    def test_sqlite_lowercase_closed_status_leak(self, test_env):
        """
        Adversarial test: What happens if status is stored in lowercase 'closed' in SQLite?
        Since SQLite query is `WHERE status != 'CLOSED'`, 'closed' != 'CLOSED' is TRUE.
        Therefore, lowercase 'closed' rows are returned by get_active_positions()!
        And then PositionStatus('closed') crashes with ValueError!
        """
        client = test_env["client"]
        headers = {"X-API-Key": test_env["api_key"]}
        db = test_env["db"]
        now = datetime.now(timezone.utc).isoformat()

        async def _insert_lowercase():
            await db.connection.execute(
                """
                INSERT INTO positions (id, bot, coin, pair, qty, entry_price, entry_time, mode, status)
                VALUES ('pos-lowercase-closed', 'STE', 'BTC', 'BTC/INR', 0.01, 5000000.0, ?, 'PAPER', 'closed')
                """,
                (now,)
            )
            await db.connection.commit()

        asyncio.run(_insert_lowercase())

        # Calling get_active_positions() fetches the row because 'closed' != 'CLOSED' in SQLite
        # and crashes on PositionStatus('closed')!
        with pytest.raises(ValueError, match="closed"):
            client.get("/api/v2/positions/open", headers=headers)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
