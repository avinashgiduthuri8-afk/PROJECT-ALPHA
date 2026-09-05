"""
Phase 3 Post-Trade Intelligence, Journaling, Analytics & Tax Ledger Test Suite for PROJECT-ALPHA V2.

Verifies:
  1. Journal Ingestion (POSITION_CLOSED event mapping, SQLite persistence, MFE/MAE recording).
  2. Statutory Tax & Friction Breakdown (0.20% fee + 18% GST + 1% Sec 194S TDS + 0.10% slippage = 1.572% drag).
  3. Quantitative Metrics & Ratios (Win Rate %, Profit Factor, Max Drawdown %, Sharpe, Sortino, Calmar).
  4. Strategy Attribution Matrix (STE, HDA, VCP, BBS segmentation).
  5. Tax Ledger Summary (TDS & GST quarterly reconciliation).
  6. API Router Endpoints (/api/v2/journal/trades, /api/v2/analytics/performance, /api/v2/analytics/tax-ledger).
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
from v2.services.journal_service.service import JournalService
from v2.services.analytics_service.engine import AnalyticsEngine
from v2.services.analytics_service.tax_ledger import TaxLedgerService
from v2.services.analytics_service.service import AnalyticsService
from v2.app_v2 import app


async def _create_test_journal_db(tmp_path):
    db_path = str(tmp_path / f"test_journal_{uuid.uuid4().hex[:6]}.db")
    db = Database(db_path)
    await db.open()
    conn = db.connection
    repo = JournalRepository(conn)
    return db, repo


# =============================================================================
# 1. Journal Ingestion & Statutory Friction Tests
# =============================================================================

class TestJournalIngestionAndFriction:

    @pytest.mark.anyio
    async def test_statutory_friction_breakdown_formula(self):
        """Assert exact statutory friction decomposition: 0.20% fee + 18% GST + 1% TDS + 0.10% slippage."""
        bus = EventBus()
        repo = MagicMock()
        service = JournalService(bus=bus, journal_repo=repo)

        # Entry = ₹100,000, Exit = ₹110,000, Qty = 1.0
        # Buy Notional = 100,000 | Sell Notional = 110,000
        # Buy Fee = 200.0 | Buy GST = 36.0
        # Sell Fee = 220.0 | Sell GST = 39.6
        # Total Exchange Fee = 420.0
        # Total GST = 75.60
        # Sec 194S TDS = 1,100.00 (1% of sell 110,000)
        # Slippage = (100,000 + 110,000) * 0.0005 = 105.00
        # Total Statutory Drag = 420 + 75.60 + 1100 + 105 = 1,700.60

        friction = service.compute_statutory_friction(entry_price=100000.0, exit_price=110000.0, quantity=1.0)

        assert friction["exchange_fee"] == 420.0
        assert friction["gst_tax"] == 75.60
        assert friction["tds_194s"] == 1100.0
        assert friction["slippage_cost"] == 105.0
        assert friction["total_statutory_drag"] == 1700.60

    @pytest.mark.anyio
    async def test_position_closed_event_ingestion(self, tmp_path):
        """Verify POSITION_CLOSED event writes a complete record into trade_journal."""
        db, repo = await _create_test_journal_db(tmp_path)
        try:
            bus = EventBus()
            service = JournalService(bus=bus, journal_repo=repo)
            await service.start()

            payload = {
                "position_id": "POS_JOURNAL_01",
                "bot": "STE",
                "coin": "SOL",
                "pair": "SOL/INR",
                "side": "BUY",
                "entry_price": 10000.0,
                "exit_price": 11000.0,
                "qty": 2.0,
                "opened_at": "2026-08-30T10:00:00+00:00",
                "closed_at": "2026-08-30T12:00:00+00:00",
                "exit_reason": "TAKE_PROFIT",
                "peak_price": 11200.0,
                "trough_price": 9900.0,
            }

            await bus.publish(EventType.POSITION_CLOSED, payload)
            await asyncio.sleep(0.05)  # Allow async bus handler to finish

            entries = await repo.get_entries(limit=10)
            assert len(entries) == 1
            e = entries[0]

            assert e["position_id"] == "POS_JOURNAL_01"
            assert e["bot_name"] == "STE"
            assert e["pair"] == "SOL/INR"
            assert e["duration_seconds"] == 7200  # 2 hours
            assert e["exit_reason"] == "TAKE_PROFIT"
            assert e["gross_pnl"] == 2000.0  # (11000 - 10000) * 2

            # Statutory drag verification
            assert e["exchange_fee"] == 84.0  # (20000*0.002) + (22000*0.002) = 40 + 44
            assert e["gst_tax"] == 15.12       # 84 * 0.18
            assert e["tds_194s"] == 220.0      # 22000 * 0.01
            assert e["slippage_cost"] == 21.0  # 42000 * 0.0005
            assert e["total_statutory_drag"] == 340.12
            assert e["net_pnl"] == 1659.88     # 2000 - 340.12

            # MFE & MAE
            assert e["mfe"] == 2400.0  # (11200 - 10000) * 2
            assert e["mae"] == 200.0   # (10000 - 9900) * 2
        finally:
            await db.close()


# =============================================================================
# 2. Quantitative Analytics Engine & Ratios Tests
# =============================================================================

class TestQuantitativeAnalyticsEngine:

    @pytest.mark.anyio
    async def test_quant_metrics_calculation(self, tmp_path):
        """Verify Win Rate %, Profit Factor, Max Drawdown, Sharpe, Sortino, Calmar calculations."""
        db, repo = await _create_test_journal_db(tmp_path)
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            # Insert 4 trades: 3 wins (+1000, +500, +800), 1 loss (-400)
            trades = [
                {
                    "id": "J1", "position_id": "P1", "bot_name": "STE", "pair": "BTC/INR", "side": "BUY",
                    "entry_price": 50000.0, "exit_price": 51000.0, "quantity": 1.0,
                    "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 1800,
                    "exit_reason": "TP_HIT", "gross_pnl": 1000.0, "exchange_fee": 20.0, "gst_tax": 3.6,
                    "tds_194s": 510.0, "slippage_cost": 50.0, "total_statutory_drag": 583.6,
                    "net_pnl": 1000.0, "net_pnl_pct": 2.0, "mfe": 1200.0, "mae": 100.0, "tags": []
                },
                {
                    "id": "J2", "position_id": "P2", "bot_name": "HDA", "pair": "ETH/INR", "side": "BUY",
                    "entry_price": 2000.0, "exit_price": 2050.0, "quantity": 10.0,
                    "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 3600,
                    "exit_reason": "TP_HIT", "gross_pnl": 500.0, "exchange_fee": 10.0, "gst_tax": 1.8,
                    "tds_194s": 205.0, "slippage_cost": 20.0, "total_statutory_drag": 236.8,
                    "net_pnl": 500.0, "net_pnl_pct": 2.5, "mfe": 600.0, "mae": 50.0, "tags": []
                },
                {
                    "id": "J3", "position_id": "P3", "bot_name": "VCP", "pair": "SOL/INR", "side": "BUY",
                    "entry_price": 100.0, "exit_price": 96.0, "quantity": 100.0,
                    "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 900,
                    "exit_reason": "SL_HIT", "gross_pnl": -400.0, "exchange_fee": 4.0, "gst_tax": 0.72,
                    "tds_194s": 96.0, "slippage_cost": 10.0, "total_statutory_drag": 110.72,
                    "net_pnl": -400.0, "net_pnl_pct": -4.0, "mfe": 50.0, "mae": 500.0, "tags": []
                },
                {
                    "id": "J4", "position_id": "P4", "bot_name": "BBS", "pair": "BNB/INR", "side": "BUY",
                    "entry_price": 500.0, "exit_price": 516.0, "quantity": 5.0,
                    "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 2700,
                    "exit_reason": "TP_HIT", "gross_pnl": 80.0, "exchange_fee": 2.0, "gst_tax": 0.36,
                    "tds_194s": 25.8, "slippage_cost": 2.5, "total_statutory_drag": 30.66,
                    "net_pnl": 800.0, "net_pnl_pct": 3.2, "mfe": 900.0, "mae": 20.0, "tags": []
                },
            ]

            for t in trades:
                await repo.insert_entry(t)

            engine = AnalyticsEngine(journal_repo=repo)
            metrics = await engine.compute_performance_metrics()

            assert metrics["total_trades"] == 4
            assert metrics["winning_trades"] == 3
            assert metrics["losing_trades"] == 1
            assert metrics["win_rate_pct"] == 75.0

            # Profit factor = gross_gains (2300) / gross_losses (400) = 5.75
            assert metrics["profit_factor"] == 5.75
            assert metrics["net_pnl"] == 1900.0

            # Strategy attribution
            strat = metrics["strategy_attribution"]
            assert strat["STE"]["trades"] == 1
            assert strat["STE"]["net_pnl"] == 1000.0
            assert strat["VCP"]["net_pnl"] == -400.0

            # Sharpe & Sortino ratios are computed non-zero
            assert metrics["sharpe_ratio"] != 0.0
            assert metrics["sortino_ratio"] != 0.0
        finally:
            await db.close()

    def test_analytics_handles_zero_trades_gracefully(self):
        """AnalyticsEngine handles empty trade entries without divide-by-zero errors."""
        engine = AnalyticsEngine(journal_repo=MagicMock())
        metrics = engine.calculate_metrics_from_entries([])

        assert metrics["total_trades"] == 0
        assert metrics["win_rate_pct"] == 0.0
        assert metrics["profit_factor"] == 0.0
        assert metrics["sharpe_ratio"] == 0.0
        assert metrics["sortino_ratio"] == 0.0
        assert metrics["calmar_ratio"] == 0.0


# =============================================================================
# 3. Statutory Tax Ledger Tests
# =============================================================================

class TestStatutoryTaxLedger:

    @pytest.mark.anyio
    async def test_tax_ledger_aggregates_tds_and_gst(self, tmp_path):
        """TaxLedgerService correctly aggregates Sec 194S TDS and brokerage GST."""
        db, repo = await _create_test_journal_db(tmp_path)
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            t1 = {
                "id": "T1", "position_id": "P1", "bot_name": "STE", "pair": "BTC/INR", "side": "BUY",
                "entry_price": 100000.0, "exit_price": 110000.0, "quantity": 1.0,
                "entry_timestamp": now_iso, "exit_timestamp": now_iso, "duration_seconds": 3600,
                "exit_reason": "TP_HIT", "gross_pnl": 10000.0, "exchange_fee": 420.0, "gst_tax": 75.60,
                "tds_194s": 1100.0, "slippage_cost": 105.0, "total_statutory_drag": 1700.60,
                "net_pnl": 8299.40, "net_pnl_pct": 8.30, "mfe": 10000.0, "mae": 0.0, "tags": []
            }
            await repo.insert_entry(t1)

            tax_service = TaxLedgerService(journal_repo=repo)
            summary = await tax_service.get_tax_summary()

            assert summary["total_trades"] == 1
            assert summary["total_exchange_fees_inr"] == 420.0
            assert summary["total_gst_inr"] == 75.60
            assert summary["total_tds_194s_inr"] == 1100.0
            assert summary["total_statutory_drag_inr"] == 1700.60
            assert summary["net_pnl_inr"] == 8299.40
            assert "quarterly_breakdown" in summary
        finally:
            await db.close()


# =============================================================================
# 4. API Endpoints Tests
# =============================================================================

class TestJournalAnalyticsAPIEndpoints:

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path, monkeypatch):
        test_db = str(tmp_path / f"test_api_{uuid.uuid4().hex[:6]}.db")
        monkeypatch.setenv("V2_DB_PATH", test_db)
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-api-key")
        invalidate_config()
        yield
        invalidate_config()

    def test_journal_and_analytics_endpoints(self):
        """Verify GET /api/v2/journal/trades, /api/v2/analytics/performance, /api/v2/analytics/tax-ledger."""
        with TestClient(app) as client:
            headers = {"X-API-Key": "test-api-key"}

            # 1. Journal trades
            res_journal = client.get("/api/v2/journal/trades?limit=10", headers=headers)
            assert res_journal.status_code == 200
            assert isinstance(res_journal.json(), list)

            # 2. Analytics performance
            res_perf = client.get("/api/v2/analytics/performance", headers=headers)
            assert res_perf.status_code == 200
            data_perf = res_perf.json()
            assert "win_rate_pct" in data_perf
            assert "profit_factor" in data_perf
            assert "strategy_attribution" in data_perf

            # 3. Tax ledger
            res_tax = client.get("/api/v2/analytics/tax-ledger", headers=headers)
            assert res_tax.status_code == 200
            data_tax = res_tax.json()
            assert "total_tds_194s_inr" in data_tax
            assert "total_gst_inr" in data_tax
            assert "quarterly_breakdown" in data_tax
