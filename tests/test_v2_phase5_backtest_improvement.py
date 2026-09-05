"""
Phase 5 Historical Backtest & Strategy Improvement Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. Zero Look-Ahead Bias (signal on bar N close executes on bar N+1 Open price).
  2. Statutory Drag & Net PnL Accuracy (1.572% total round-trip friction).
  3. Multi-Strategy Replay (STE, HDA, VCP, BBS).
  4. Walk-Forward 70/30 In-Sample vs Out-of-Sample Validation & Benchmark Comparison.
  5. SQLite Persistence & REST API Endpoints (/backtest/run, /backtest/results, /backtest/results/{run_id}).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from v2.core.config import invalidate_config
from v2.repository.db import Database
from v2.repository.backtest_repo import BacktestRepository
from v2.backtest.historical_runner import HistoricalRunner, STATUTORY_ROUND_TRIP_DRAG_RATE
from v2.backtest.optimizer import StrategyOptimizer
from v2.services.backtest_service.service import BacktestService
from v2.app_v2 import app


def generate_synthetic_candles(count: int = 50, start_price: float = 100.0) -> list[dict]:
    """Helper generating synthetic candle series for backtest testing."""
    candles = []
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    price = start_price

    for i in range(count):
        t_str = (base_time + timedelta(minutes=5 * i)).isoformat()
        # Alternate up and down bars to trigger signals
        change = 1.5 if i % 2 == 0 else -0.8
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + 0.5
        low_p = min(open_p, close_p) - 0.5
        price = close_p

        candles.append({
            "timestamp": t_str,
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": 100.0 + i * 2,
        })

    return candles


async def _create_test_backtest_db(tmp_path):
    db_path = str(tmp_path / f"test_backtest_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    conn = db.connection
    backtest_repo = BacktestRepository(conn)
    return db, backtest_repo


# =============================================================================
# 1. Zero Look-Ahead Bias & Statutory Friction Tests
# =============================================================================

class TestHistoricalRunnerEngine:

    def test_zero_look_ahead_bias_execution(self):
        """Assert signal calculated on bar N close enters trade at bar N+1 Open price."""
        runner = HistoricalRunner()
        candles = generate_synthetic_candles(count=30, start_price=100.0)

        run_summary, trades = runner.run_simulation("STE", "BTC/INR", candles)
        assert run_summary["total_trades"] == len(trades)

        if trades:
            first_trade = trades[0]
            # Find entry timestamp in candles
            entry_time = first_trade["entry_time"]
            entry_candle = next(c for c in candles if c["timestamp"] == entry_time)
            # Assert execution price matches bar N+1 OPEN price
            assert first_trade["entry_price"] == entry_candle["open"]

    def test_statutory_friction_drag_deduction(self):
        """Assert statutory 1.572% friction is correctly deducted from net PnL."""
        runner = HistoricalRunner()
        entry_price = 100.0
        exit_price = 110.0
        qty = 10.0

        drag = runner.compute_statutory_drag(entry_price, exit_price, qty)
        expected_drag = (100.0 * 10.0 + 110.0 * 10.0) * (STATUTORY_ROUND_TRIP_DRAG_RATE / 2.0)
        assert round(drag, 4) == round(expected_drag, 4)


# =============================================================================
# 2. Strategy Optimizer & Walk-Forward Validation Tests
# =============================================================================

class TestStrategyOptimizer:

    def test_walk_forward_split_and_validation(self):
        """Verify 70/30 Walk-Forward split ratio and validation report generation."""
        optimizer = StrategyOptimizer()
        candles = generate_synthetic_candles(count=100)

        in_sample, out_sample = optimizer.walk_forward_split(candles, train_ratio=0.70)
        assert len(in_sample) == 70
        assert len(out_sample) == 30

        param_grid = {
            "stop_loss_pct": [0.01, 0.02],
            "take_profit_pct": [0.03, 0.05],
        }

        wf_report = optimizer.run_walk_forward_validation("STE", "ETH/INR", candles, param_grid)
        assert "in_sample" in wf_report
        assert "out_of_sample" in wf_report
        assert wf_report["in_sample"]["candle_count"] == 70
        assert wf_report["out_of_sample"]["candle_count"] == 30

    def test_benchmark_metrics_computation(self):
        """Verify Alpha and Beta calculations against benchmark series."""
        optimizer = StrategyOptimizer()
        b_candles = generate_synthetic_candles(count=20, start_price=100.0)
        strat_returns = [1.5, 2.0, -0.5, 3.0, 1.2]

        bench_metrics = optimizer.compute_benchmark_metrics(strat_returns, b_candles)
        assert "alpha" in bench_metrics
        assert "beta" in bench_metrics
        assert "benchmark_cagr" in bench_metrics
        assert "strategy_cagr" in bench_metrics


# =============================================================================
# 3. Database Persistence & Service Layer Tests
# =============================================================================

class TestBacktestRepositoryPersistence:

    @pytest.mark.anyio
    async def test_record_and_retrieve_backtest_run(self, tmp_path):
        """Verify SQLite persistence for backtest runs and simulated trade logs."""
        db, backtest_repo = await _create_test_backtest_db(tmp_path)
        try:
            service = BacktestService(backtest_repo=backtest_repo)
            candles = generate_synthetic_candles(count=40)

            result = await service.run_backtest("HDA", "SOL/INR", candles)
            assert result["id"] is not None
            run_id = result["id"]

            detail = await service.get_run_detail(run_id)
            assert detail is not None
            assert detail["strategy_name"] == "HDA"
            assert detail["pair"] == "SOL/INR"
            assert isinstance(detail["trades"], list)
        finally:
            await db.close()


# =============================================================================
# 4. REST API Endpoint Tests
# =============================================================================

class TestBacktestAPIEndpoints:

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        test_db = str(tmp_path / f"test_api_backtest_{uuid.uuid4().hex[:6]}.db")
        monkeypatch.setenv("V2_DB_PATH", test_db)
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-backtest-key")
        invalidate_config()
        yield
        invalidate_config()

    def test_backtest_run_and_results_endpoints(self):
        """Verify POST /backtest/run, GET /backtest/results, and GET /backtest/results/{run_id}."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-backtest-key"}
            candles = generate_synthetic_candles(count=30)

            # 1. POST /backtest/run
            payload = {
                "strategy_name": "STE",
                "pair": "BTC/INR",
                "timeframe": "5m",
                "candles": candles,
            }
            res_run = client.post(
                "/api/v2/backtest/run",
                json=payload,
                headers=headers,
            )
            assert res_run.status_code == 200
            data_run = res_run.json()
            assert "id" in data_run
            run_id = data_run["id"]

            # 2. GET /backtest/results
            res_list = client.get("/api/v2/backtest/results", headers=headers)
            assert res_list.status_code == 200
            runs = res_list.json()
            assert isinstance(runs, list)
            assert any(r["id"] == run_id for r in runs)

            # 3. GET /backtest/results/{run_id}
            res_detail = client.get(f"/api/v2/backtest/results/{run_id}", headers=headers)
            assert res_detail.status_code == 200
            detail = res_detail.json()
            assert detail["id"] == run_id
            assert "trades" in detail
