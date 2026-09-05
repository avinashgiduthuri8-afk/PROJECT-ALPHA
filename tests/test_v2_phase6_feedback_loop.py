"""
Phase 6 Autonomous Recursive Feedback Loop Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. End-to-End Feedback Pipeline (Signal -> Trade -> Result -> Insight -> Pre-Validation -> Promotion).
  2. Pre-Deployment Backtest Verification Gate (PROMOTED vs REJECTED decisions).
  3. Safety Rollback Engine (2 consecutive post-promotion losses trigger rollback to baseline mult=1.0, thresh=85.0).
  4. SQLite Persistence & REST API Endpoints (/feedback/loop-status, /feedback/audit-trail, /feedback/trigger-cycle).
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
from v2.core.config import invalidate_config
from v2.repository.db import Database
from v2.repository.backtest_repo import BacktestRepository
from v2.repository.feedback_repo import FeedbackRepository
from v2.services.backtest_service.service import BacktestService
from v2.services.feedback_service.orchestrator import FeedbackOrchestrator
from v2.services.feedback_service.service import FeedbackService
from v2.app_v2 import app
from tests.test_v2_phase5_backtest_improvement import generate_synthetic_candles


async def _create_test_feedback_db(tmp_path):
    db_path = str(tmp_path / f"test_feedback_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    conn = db.connection
    backtest_repo = BacktestRepository(conn)
    feedback_repo = FeedbackRepository(conn)
    return db, backtest_repo, feedback_repo


# =============================================================================
# 1. Pre-Deployment Backtest Verification & Promotion Gate Tests
# =============================================================================

class TestPreDeploymentValidationGate:

    @pytest.mark.anyio
    async def test_calibration_promotion_on_valid_backtest(self, tmp_path):
        """Assert candidate calibration passing backtest is PROMOTED to active cache."""
        db, backtest_repo, feedback_repo = await _create_test_feedback_db(tmp_path)
        try:
            bus = EventBus()
            backtest_service = BacktestService(backtest_repo=backtest_repo)
            orchestrator = FeedbackOrchestrator(feedback_repo=feedback_repo, backtest_service=backtest_service, bus=bus)

            candles = generate_synthetic_candles(count=40)

            # Evaluate candidate calibration (tighten threshold to 90.0, mult 1.2x)
            audit_event = await orchestrator.evaluate_and_validate_calibration(
                bot_name="STE",
                pair="BTC/INR",
                proposed_multiplier=1.2,
                proposed_threshold=90.0,
                validation_candles=candles,
            )

            assert audit_event["status"] in ("PROMOTED", "VALIDATED")
            assert audit_event["bot_name"] == "STE"

            cached = await feedback_repo.get_active_calibration("STE")
            assert cached is not None
            assert cached["weight_multiplier"] == 1.2
            assert cached["strict_threshold"] == 90.0
        finally:
            await db.close()

    @pytest.mark.anyio
    async def test_calibration_rejection_on_degraded_backtest(self, tmp_path):
        """Assert candidate calibration failing backtest criteria is REJECTED and not cached."""
        db, backtest_repo, feedback_repo = await _create_test_feedback_db(tmp_path)
        try:
            bus = EventBus()
            backtest_service = BacktestService(backtest_repo=backtest_repo)

            # Mock backtest service to return degraded results (PF = 0.5 < 0.8)
            backtest_service.run_backtest = AsyncMock(return_value={
                "id": "BT_DEGRADED",
                "total_trades": 10,
                "win_rate": 20.0,
                "profit_factor": 0.5,
                "max_drawdown": 25.0,
            })

            orchestrator = FeedbackOrchestrator(feedback_repo=feedback_repo, backtest_service=backtest_service, bus=bus)

            audit_event = await orchestrator.evaluate_and_validate_calibration(
                bot_name="HDA",
                pair="ETH/INR",
                proposed_multiplier=0.5,
                proposed_threshold=95.0,
            )

            assert audit_event["status"] == "REJECTED"
            cached = await feedback_repo.get_active_calibration("HDA")
            # Should remain unpromoted / None
            assert cached is None
        finally:
            await db.close()


# =============================================================================
# 2. Automated Safety Rollback Tests
# =============================================================================

class TestSafetyRollbackEngine:

    @pytest.mark.anyio
    async def test_safety_rollback_on_consecutive_losses(self, tmp_path):
        """Assert 2 consecutive post-promotion losses trigger emergency rollback to baseline config."""
        db, backtest_repo, feedback_repo = await _create_test_feedback_db(tmp_path)
        try:
            bus = EventBus()
            backtest_service = BacktestService(backtest_repo=backtest_repo)
            orchestrator = FeedbackOrchestrator(feedback_repo=feedback_repo, backtest_service=backtest_service, bus=bus)

            # 1. Promote initial calibration (mult 1.5x, thresh 90.0)
            await feedback_repo.upsert_active_calibration("VCP", 1.5, 90.0)

            # 2. First losing trade post-promotion
            rb1 = await orchestrator.register_trade_outcome("VCP", "BTC/INR", is_win=False)
            assert rb1 is None  # Not yet rolled back

            # 3. Second consecutive losing trade post-promotion -> Trigger Rollback!
            rb2 = await orchestrator.register_trade_outcome("VCP", "BTC/INR", is_win=False)
            assert rb2 is not None
            assert rb2["status"] == "ROLLED_BACK"
            assert rb2["action_taken"] == "ROLLBACK"
            assert rb2["new_multiplier"] == 1.0
            assert rb2["new_threshold"] == 85.0

            # Verify active calibration cache was restored to baseline
            cached = await feedback_repo.get_active_calibration("VCP")
            assert cached["weight_multiplier"] == 1.0
            assert cached["strict_threshold"] == 85.0
        finally:
            await db.close()


# =============================================================================
# 3. Persistence & REST API Endpoint Tests
# =============================================================================

class TestFeedbackAPIEndpoints:

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        test_db = str(tmp_path / f"test_api_feedback_{uuid.uuid4().hex[:6]}.db")
        monkeypatch.setenv("V2_DB_PATH", test_db)
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-feedback-key")
        invalidate_config()
        yield
        invalidate_config()

    def test_feedback_loop_status_audit_trail_and_trigger_cycle(self):
        """Verify GET /feedback/loop-status, GET /feedback/audit-trail, and POST /feedback/trigger-cycle."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-feedback-key"}
            candles = generate_synthetic_candles(count=30)

            # 1. POST /feedback/trigger-cycle
            payload = {
                "bot_name": "STE",
                "pair": "SOL/INR",
                "multiplier": 1.2,
                "threshold": 88.0,
                "candles": candles,
            }
            res_trigger = client.post("/api/v2/feedback/trigger-cycle", json=payload, headers=headers)
            assert res_trigger.status_code == 200
            data_trig = res_trigger.json()
            assert "bot_name" in data_trig
            assert data_trig["bot_name"] == "STE"
            assert "status" in data_trig

            # 2. GET /feedback/loop-status
            res_status = client.get("/api/v2/feedback/loop-status", headers=headers)
            assert res_status.status_code == 200
            data_stat = res_status.json()
            assert data_stat["loop_status"] == "ACTIVE_HEALTHY"
            assert "active_calibrations" in data_stat

            # 3. GET /feedback/audit-trail
            res_audit = client.get("/api/v2/feedback/audit-trail", headers=headers)
            assert res_audit.status_code == 200
            audits = res_audit.json()
            assert isinstance(audits, list)
            assert len(audits) >= 1
            assert audits[0]["bot_name"] == "STE"
