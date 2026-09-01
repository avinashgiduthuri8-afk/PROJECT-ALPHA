"""
Unit and Integration Tests for V2 Scanned Coins Visibility & Latest-Scan Snapshot Engine.
"""

from __future__ import annotations

import asyncio
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from v2.app_v2 import app
from v2.bus.event_bus import EventBus
from v2.core.config import V2Config, get_config, invalidate_config
from v2.core.types import MarketState, OppType, Priority, RiskLevel, Signal
from v2.repository.signal_repo import SignalRepository
from v2.repository.event_log_repo import EventLogRepository
from v2.repository.db import Database
from v2.services.scanner_service.service import ScannerService
from v2.services.scanner_service.confluence_engine import ConfluenceEngine, LayerEvaluation, ConfluenceResult


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    test_db = str(tmp_path / f"test_visibility_{uuid.uuid4().hex[:6]}.db")
    monkeypatch.setenv("V2_DB_PATH", test_db)
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-visibility-key")
    invalidate_config()
    yield
    invalidate_config()


@pytest.mark.anyio
async def test_scanner_snapshot_retention_and_overwrite(tmp_path):
    """Verify ScannerService captures evaluation results and atomically overwrites on subsequent cycles."""
    db_path = str(tmp_path / "scanner_snap.db")
    db = Database(db_path)
    await db.open()
    bus = EventBus()
    sig_repo = SignalRepository(db.connection)
    event_repo = EventLogRepository(db.connection)
    cfg = V2Config(v2_scanner_strict_confluence_threshold=85, v2_scanner_max_signals=2)

    scanner = ScannerService(bus=bus, signal_repo=sig_repo, event_log_repo=event_repo, config=cfg)

    # Initial state
    assert scanner.get_scanned_coins() == []
    assert scanner.get_scanned_coin_detail("BTC") is None

    # Simulate first scan pass with 3 candidates
    now = datetime.now(timezone.utc)
    sig_btc = Signal(id="sig-1", coin="BTC", pair="BTC/INR", market_state=MarketState.BULL_TREND, opportunity_type=OppType.MOMENTUM_TRADE, priority=Priority.HIGH, risk_level=RiskLevel.LOW, score=88, confidence=90, coin_class="A", mtf_alignment=True, generated_at=now, expires_at=now)
    sig_eth = Signal(id="sig-2", coin="ETH", pair="ETH/INR", market_state=MarketState.PULLBACK, opportunity_type=OppType.CONTINUATION, priority=Priority.MEDIUM, risk_level=RiskLevel.MEDIUM, score=78, confidence=80, coin_class="A", mtf_alignment=True, generated_at=now, expires_at=now)
    sig_sol = Signal(id="sig-3", coin="SOL", pair="SOL/INR", market_state=MarketState.DOWNTREND, opportunity_type=OppType.WATCHLIST, priority=Priority.WATCH, risk_level=RiskLevel.HIGH, score=62, confidence=60, coin_class="B", mtf_alignment=False, generated_at=now, expires_at=now)

    res_btc = ConfluenceResult(signal=sig_btc, accepted=True, confluence_score=88, rank=1, layer_evaluations={"chart": LayerEvaluation("Chart", True, 90), "indicator": LayerEvaluation("Indicator", True, 88), "sentiment": LayerEvaluation("Sentiment", True, 85), "news": LayerEvaluation("News", True, 90)}, rejection_reasons=[])
    res_eth = ConfluenceResult(signal=sig_eth, accepted=False, confluence_score=78, rank=0, layer_evaluations={"chart": LayerEvaluation("Chart", True, 80), "indicator": LayerEvaluation("Indicator", True, 78), "sentiment": LayerEvaluation("Sentiment", False, 60, reasons=["Market regime is RISK_OFF"]), "news": LayerEvaluation("News", True, 90)}, rejection_reasons=["Market regime is RISK_OFF", "Confluence score (78) below strict threshold (85)"])
    res_sol = ConfluenceResult(signal=sig_sol, accepted=False, confluence_score=62, rank=0, layer_evaluations={"chart": LayerEvaluation("Chart", False, 50, reasons=["Downtrend chart"]), "indicator": LayerEvaluation("Indicator", False, 60), "sentiment": LayerEvaluation("Sentiment", False, 60), "news": LayerEvaluation("News", True, 80)}, rejection_reasons=["Downtrend chart", "Confluence score (62) below strict threshold (85)"])

    # Directly mock confluence evaluation return
    async def mock_fetch_v1():
        return [{"coin": "BTC", "price": 6500000.0, "rsi": 58.0}, {"coin": "ETH", "price": 280000.0, "rsi": 48.0}, {"coin": "SOL", "price": 14500.0, "rsi": 42.0}]

    scanner._fetch_v1_signals = mock_fetch_v1
    scanner._confluence_engine.evaluate_candidates = lambda raw_candidates, signals: ([sig_btc], [res_btc, res_eth, res_sol])

    summary = await scanner.poll()
    assert summary["new_signals"] == 1

    # Verify snapshot populated for all 3 coins (including rejected ones)
    scanned = scanner.get_scanned_coins()
    assert len(scanned) == 3
    assert scanned[0]["symbol"] == "BTC"
    assert scanned[0]["status"] == "PASSED"
    assert scanned[0]["confluence_score"] == 88

    assert scanned[1]["symbol"] == "ETH"
    assert scanned[1]["status"] == "REJECTED"
    assert scanned[1]["confluence_score"] == 78
    assert "RISK_OFF" in scanned[1]["rejection_reason"]

    assert scanned[2]["symbol"] == "SOL"
    assert scanned[2]["status"] == "REJECTED"
    assert scanned[2]["confluence_score"] == 62

    # Verify symbol flexibility lookup
    detail_btc1 = scanner.get_scanned_coin_detail("BTC")
    detail_btc2 = scanner.get_scanned_coin_detail("BTCINR")
    detail_btc3 = scanner.get_scanned_coin_detail("BTC/INR")
    assert detail_btc1 is not None and detail_btc1["confluence_score"] == 88
    assert detail_btc2 is not None and detail_btc2["price"] == 6500000.0
    assert detail_btc3 is not None

    # Simulate second scan pass with only 1 coin to test atomic overwrite (no memory leak)
    async def mock_fetch_v1_pass2():
        return [{"coin": "ETH", "price": 282000.0, "rsi": 50.0}]

    scanner._fetch_v1_signals = mock_fetch_v1_pass2
    scanner._confluence_engine.evaluate_candidates = lambda raw_candidates, signals: ([], [res_eth])

    await scanner.poll()
    scanned_pass2 = scanner.get_scanned_coins()
    assert len(scanned_pass2) == 1
    assert scanned_pass2[0]["symbol"] == "ETH"
    assert scanner.get_scanned_coin_detail("BTC") is None  # BTC evicted from previous pass


def test_api_scanned_coins_endpoints():
    """Verify GET /api/v2/scanner/coins and /api/v2/scanner/coins/{symbol}."""
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-visibility-key"}

        # 1. Trigger poll to populate snapshot
        poll_resp = client.post("/api/v2/scanner/poll", headers=headers)
        assert poll_resp.status_code == 200

        # 2. Query coins list
        resp = client.get("/api/v2/scanner/coins", headers=headers)
        assert resp.status_code == 200
        coins = resp.json()
        assert isinstance(coins, list)
        assert len(coins) >= 1

        for c in coins:
            assert "symbol" in c
            assert "pair" in c
            assert "price" in c
            assert "confluence_score" in c
            assert "status" in c
            assert "ema_trend" in c
            assert "rsi" in c

        first_sym = coins[0]["symbol"]

        # 3. Query single coin detail
        resp_detail = client.get(f"/api/v2/scanner/coins/{first_sym}", headers=headers)
        assert resp_detail.status_code == 200
        detail = resp_detail.json()
        assert detail["symbol"] == first_sym
        assert "eval_breakdown" in detail
        assert "chart" in detail["eval_breakdown"]
        assert "indicator" in detail["eval_breakdown"]
        assert "sentiment" in detail["eval_breakdown"]
        assert "news" in detail["eval_breakdown"]

        # 4. Query unknown coin returns 404
        resp_404 = client.get("/api/v2/scanner/coins/NON_EXISTENT_COIN_XYZ", headers=headers)
        assert resp_404.status_code == 404
        assert "not found" in resp_404.json()["detail"].lower()


def test_zero_signal_market_regime_retains_scanned_coins():
    """Verify that even when 0 signals pass the 85-point strict gate, all evaluated coins remain visible."""
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-visibility-key"}

        # Get overview
        resp = client.get("/api/v2/dashboard/overview", headers=headers)
        assert resp.status_code == 200
        overview = resp.json()
        assert "watchlist_summary" in overview
        assert "total_evaluated" in overview["watchlist_summary"]
        assert "scanned_coins" in overview
