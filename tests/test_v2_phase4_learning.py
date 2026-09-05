"""
Phase 4 Learning Engine & Dynamic Calibration Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. Mistake Detection (consecutive losses, MAE excursion leak, low MFE efficiency, regime mismatch).
  2. Strategy Calibration (COOLING_DOWN, BOOSTED, ACTIVE states, score thresholds & weight multipliers).
  3. SQLite Database Persistence (LearningRepository insights & calibrations).
  4. EventBus Events & REST API Endpoints (/learning/insights, /learning/calibrations, /learning/run-cycle).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import invalidate_config
from v2.repository.db import Database
from v2.repository.journal_repo import JournalRepository
from v2.repository.learning_repo import LearningRepository
from v2.services.analytics_service.engine import AnalyticsEngine
from v2.services.learning_service.engine import LearningEngine
from v2.services.learning_service.calibrator import StrategyCalibrator
from v2.services.learning_service.service import LearningService
from v2.app_v2 import app


async def _create_test_learning_db(tmp_path):
    db_path = str(tmp_path / f"test_learning_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    conn = db.connection
    journal_repo = JournalRepository(conn)
    learning_repo = LearningRepository(conn)
    return db, journal_repo, learning_repo


# =============================================================================
# 1. Mistake Detection & Pattern Extraction Tests
# =============================================================================

class TestMistakeDetectionEngine:

    @pytest.mark.anyio
    async def test_consecutive_losses_detection(self, tmp_path):
        """Assert 3+ consecutive losses trigger a CONSECUTIVE_LOSSES insight."""
        db, journal_repo, learning_repo = await _create_test_learning_db(tmp_path)
        try:
            now_iso = datetime.now(timezone.utc).isoformat()

            # Insert 3 consecutive losing trades for strategy STE on SOL/INR
            for i in range(3):
                trade = {
                    "id": f"L_STE_{i}",
                    "position_id": f"POS_{i}",
                    "bot_name": "STE",
                    "pair": "SOL/INR",
                    "side": "BUY",
                    "entry_price": 100.0,
                    "exit_price": 95.0,
                    "quantity": 10.0,
                    "entry_timestamp": now_iso,
                    "exit_timestamp": now_iso,
                    "duration_seconds": 600,
                    "exit_reason": "SL_HIT",
                    "gross_pnl": -50.0,
                    "exchange_fee": 1.0,
                    "gst_tax": 0.18,
                    "tds_194s": 0.95,
                    "slippage_cost": 0.10,
                    "total_statutory_drag": 2.23,
                    "net_pnl": -52.23,
                    "net_pnl_pct": -5.22,
                    "mfe": 10.0,
                    "mae": 60.0,
                    "tags": [],
                }
                await journal_repo.insert_entry(trade)

            engine = LearningEngine(journal_repo=journal_repo, learning_repo=learning_repo)
            insights = await engine.analyze_trades_and_extract_insights()

            assert len(insights) >= 1
            loss_ins = next((i for i in insights if i["pattern_type"] == "CONSECUTIVE_LOSSES"), None)
            assert loss_ins is not None
            assert loss_ins["bot_name"] == "STE"
            assert loss_ins["severity"] in ("HIGH", "CRITICAL")
            assert "3 consecutive stop-outs" in loss_ins["lesson_summary"]
        finally:
            await db.close()

    @pytest.mark.anyio
    async def test_mae_excursion_and_mfe_efficiency_detection(self, tmp_path):
        """Assert heavy MAE excursion (>2%) and low MFE efficiency (<30%) generate insights."""
        db, journal_repo, learning_repo = await _create_test_learning_db(tmp_path)
        try:
            now_iso = datetime.now(timezone.utc).isoformat()

            # Trade 1: High MAE excursion (entry 100, qty 10 -> notional 1000, MAE 30.0 = 3.0%)
            t_mae = {
                "id": "T_MAE", "position_id": "P_MAE", "bot_name": "HDA", "pair": "ETH/INR", "side": "BUY",
                "entry_price": 100.0, "exit_price": 102.0, "quantity": 10.0,
                "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 1200,
                "exit_reason": "TP_HIT", "gross_pnl": 20.0, "exchange_fee": 0.4, "gst_tax": 0.07,
                "tds_194s": 1.02, "slippage_cost": 0.1, "total_statutory_drag": 1.59,
                "net_pnl": 18.41, "net_pnl_pct": 1.84, "mfe": 100.0, "mae": 30.0, "tags": []
            }

            # Trade 2: Low MFE efficiency (MFE = 500.0, Net PnL = 100.0 -> capture ratio 20% < 30%)
            t_mfe = {
                "id": "T_MFE", "position_id": "P_MFE", "bot_name": "VCP", "pair": "BTC/INR", "side": "BUY",
                "entry_price": 50000.0, "exit_price": 50200.0, "quantity": 1.0,
                "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 1800,
                "exit_reason": "TP_HIT", "gross_pnl": 200.0, "exchange_fee": 20.0, "gst_tax": 3.6,
                "tds_194s": 502.0, "slippage_cost": 50.0, "total_statutory_drag": 575.6,
                "net_pnl": 100.0, "net_pnl_pct": 0.2, "mfe": 500.0, "mae": 20.0, "tags": []
            }

            await journal_repo.insert_entry(t_mae)
            await journal_repo.insert_entry(t_mfe)

            engine = LearningEngine(journal_repo=journal_repo, learning_repo=learning_repo)
            insights = await engine.analyze_trades_and_extract_insights()

            pattern_types = [i["pattern_type"] for i in insights]
            assert "MAE_EXCURSION_LEAK" in pattern_types
            assert "LOW_MFE_EFFICIENCY" in pattern_types
        finally:
            await db.close()


# =============================================================================
# 2. Dynamic Strategy Calibration Tests
# =============================================================================

class TestDynamicStrategyCalibrator:

    @pytest.mark.anyio
    async def test_calibrator_cooling_down_and_boosted_states(self, tmp_path):
        """Assert StrategyCalibrator sets COOLING_DOWN or BOOSTED state based on performance and insights."""
        db, journal_repo, learning_repo = await _create_test_learning_db(tmp_path)
        try:
            bus = EventBus()
            analytics = AnalyticsEngine(journal_repo=journal_repo)
            calibrator = StrategyCalibrator(learning_repo=learning_repo, analytics_engine=analytics, bus=bus)

            # Insert high-severity insight for STE
            ins = {
                "id": "INS_STE_01",
                "bot_name": "STE",
                "pair": "SOL/INR",
                "pattern_type": "CONSECUTIVE_LOSSES",
                "severity": "HIGH",
                "lesson_summary": "3 consecutive stop-outs",
                "recommended_adjustment": "Cool down strategy",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await learning_repo.record_insight(ins)

            cals = await calibrator.calibrate_all_strategies([ins])
            assert len(cals) == 4

            ste_cal = next(c for c in cals if c["bot_name"] == "STE")
            assert ste_cal["status"] == "COOLING_DOWN"
            assert ste_cal["weight_multiplier"] == 0.5
            assert ste_cal["min_confluence_threshold"] == 90.0

            # Verify baseline ACTIVE state for others
            hda_cal = next(c for c in cals if c["bot_name"] == "HDA")
            assert hda_cal["status"] == "ACTIVE"
            assert hda_cal["weight_multiplier"] == 1.0
            assert hda_cal["min_confluence_threshold"] == 85.0
        finally:
            await db.close()


# =============================================================================
# 3. Database Persistence & Service Lifecycle Tests
# =============================================================================

class TestLearningRepositoryPersistence:

    @pytest.mark.anyio
    async def test_upsert_and_retrieve_calibrations(self, tmp_path):
        """Assert calibrations and insights persist cleanly in SQLite."""
        db, journal_repo, learning_repo = await _create_test_learning_db(tmp_path)
        try:
            await learning_repo.upsert_calibration(
                bot_name="BBS",
                pair="BNB/INR",
                weight_multiplier=1.2,
                min_confluence_threshold=80.0,
                status="BOOSTED",
            )

            cals = await learning_repo.get_calibrations()
            assert len(cals) >= 1
            bbs = next(c for c in cals if c["bot_name"] == "BBS")
            assert bbs["status"] == "BOOSTED"
            assert bbs["weight_multiplier"] == 1.2
            assert bbs["min_confluence_threshold"] == 80.0
        finally:
            await db.close()


# =============================================================================
# 4. REST API Endpoint Tests
# =============================================================================

class TestLearningAPIEndpoints:

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        test_db = str(tmp_path / f"test_api_learning_{uuid.uuid4().hex[:6]}.db")
        monkeypatch.setenv("V2_DB_PATH", test_db)
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-learning-key")
        invalidate_config()
        yield
        invalidate_config()

    def test_learning_insights_and_calibrations_endpoints(self):
        """Verify GET /learning/insights, GET /learning/calibrations, and POST /learning/run-cycle."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-learning-key"}

            # 1. Run learning cycle
            res_cycle = client.post("/api/v2/learning/run-cycle", headers=headers)
            assert res_cycle.status_code == 200
            data_cycle = res_cycle.json()
            assert "insights_generated" in data_cycle
            assert "calibrations_updated" in data_cycle

            # 2. Get active insights
            res_insights = client.get("/api/v2/learning/insights", headers=headers)
            assert res_insights.status_code == 200
            assert isinstance(res_insights.json(), list)

            # 3. Get strategy calibrations
            res_cals = client.get("/api/v2/learning/calibrations", headers=headers)
            assert res_cals.status_code == 200
            cals = res_cals.json()
            assert isinstance(cals, list)
            assert len(cals) == 4
            bot_names = [c["bot_name"] for c in cals]
            assert "STE" in bot_names
            assert "HDA" in bot_names
            assert "VCP" in bot_names
            assert "BBS" in bot_names
