"""
Tests for PROJECT-ALPHA V2 14-Stage Autonomous Trading Pipeline & Dashboard Inspection.
"""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from v2.app_v2 import app
from v2.bus.event_types import EventType
from v2.core.config import invalidate_config
from v2.services.dashboard_service.pipeline import PipelineStageCollector


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    test_db = str(tmp_path / f"test_pipe_{uuid.uuid4().hex[:6]}.db")
    monkeypatch.setenv("V2_DB_PATH", test_db)
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-pipe-key")
    invalidate_config()
    yield
    invalidate_config()


def test_pipeline_stage_collector_initialization():
    """Verify collector registers all 14 stages of the autonomous pipeline."""
    collector = PipelineStageCollector()
    stages = collector.get_all_stages()

    assert len(stages) == 14
    stage_ids = [s["id"] for s in stages]
    expected_ids = [
        "market_data",
        "scanner",
        "signal_engine",
        "ai_intelligence",
        "trade_constructor",
        "risk_engine",
        "auto_trade",
        "position_manager",
        "trade_journal",
        "analytics",
        "learning_engine",
        "backtest_test",
        "improved_strategy",
        "autonomous_loop",
    ]
    assert stage_ids == expected_ids

    # Verify numbering and non-empty metadata
    for idx, stage in enumerate(stages, start=1):
        assert stage["number"] == idx
        assert stage["name"]
        assert stage["category"]
        assert stage["icon"]
        assert stage["status"] in ("ONLINE", "ACTIVE", "READY", "STANDBY", "CONTINUOUS")
        assert isinstance(stage["metrics"], dict)


def test_pipeline_stage_detail_contracts():
    """Verify detailed contracts and telemetry for key stages."""
    collector = PipelineStageCollector()

    # 1. Market Data
    md = collector.get_stage_detail("market_data")
    assert md is not None
    assert md["input_contract"]["source"] == "CoinDCX Public WebSockets & REST Tickers"
    assert md["output_contract"]["destination"] == "Scanner & Local Ticker Cache"

    # 2. AI Intelligence
    ai = collector.get_stage_detail("ai_intelligence")
    assert ai is not None
    assert "SIGNAL_AI_CONFIRMED" in ai["output_contract"]["events"]

    # 3. Auto-Trade (Execution Engine)
    at = collector.get_stage_detail("auto_trade")
    assert at is not None
    assert at["input_contract"]["event"] == "TRADE_APPROVED"
    assert at["output_contract"]["event"] == "TRADE_EXECUTED"

    # 4. Recursive Feedback Loop
    loop = collector.get_stage_detail("autonomous_loop")
    assert loop is not None
    assert loop["number"] == 14
    assert loop["status"] == "CONTINUOUS"


def test_pipeline_stage_event_handling():
    """Verify live EventBus events dynamically update stage states and telemetry."""
    collector = PipelineStageCollector()

    # Event 1: SIGNAL_GENERATED
    collector.handle_bus_event(
        EventType.SIGNAL_GENERATED.value,
        {"coin": "SOL", "score": 88, "bot": "MTB"},
    )
    sig_stage = collector.get_stage_detail("signal_engine")
    assert sig_stage["last_event"]["coin"] == "SOL"
    assert sig_stage["last_event"]["score"] == 88

    # Event 2: SIGNAL_AI_CONFIRMED
    collector.handle_bus_event(
        EventType.SIGNAL_AI_CONFIRMED.value,
        {"coin": "SOL", "recommendation": "APPROVE", "confidence_score": 92},
    )
    ai_stage = collector.get_stage_detail("ai_intelligence")
    assert ai_stage["last_event"]["coin"] == "SOL"
    assert ai_stage["last_event"]["recommendation"] == "APPROVE"
    assert ai_stage["last_event"]["confidence"] == 92

    # Event 3: TRADE_APPROVED
    collector.handle_bus_event(
        EventType.TRADE_APPROVED.value,
        {"coin": "SOL", "bot": "MTB", "approved_amount": 250.0},
    )
    risk_stage = collector.get_stage_detail("risk_engine")
    assert risk_stage["last_event"]["status"] == "APPROVED"
    assert risk_stage["last_event"]["amount"] == 250.0

    # Event 4: TRADE_EXECUTED
    collector.handle_bus_event(
        EventType.TRADE_EXECUTED.value,
        {"coin": "SOL", "bot": "MTB", "entry_price": 140.0},
    )
    auto_trade_stage = collector.get_stage_detail("auto_trade")
    assert auto_trade_stage["last_event"]["coin"] == "SOL"
    assert auto_trade_stage["last_event"]["price"] == 140.0


def test_pipeline_api_endpoints():
    """Verify API endpoints for pipeline stages and detail lookup."""
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-pipe-key"}

        # 1. GET /api/v2/pipeline/stages
        res = client.get("/api/v2/pipeline/stages", headers=headers)
        assert res.status_code == 200
        stages = res.json()
        assert len(stages) == 14
        assert stages[0]["id"] == "market_data"
        assert stages[6]["id"] == "auto_trade"
        assert stages[13]["id"] == "autonomous_loop"

        # 2. GET /api/v2/pipeline/stages/auto_trade (Detail)
        res_at = client.get("/api/v2/pipeline/stages/auto_trade", headers=headers)
        assert res_at.status_code == 200
        at_data = res_at.json()
        assert at_data["id"] == "auto_trade"
        assert at_data["name"] == "AUTO TRADE (EXECUTION)"
        assert "input_contract" in at_data
        assert "output_contract" in at_data

        # 3. GET /api/v2/pipeline/stages/unknown (404)
        res_404 = client.get("/api/v2/pipeline/stages/non_existent_stage", headers=headers)
        assert res_404.status_code == 404

        # 4. GET /api/v2/dashboard/overview includes pipeline_stages
        res_ov = client.get("/api/v2/dashboard/overview", headers=headers)
        assert res_ov.status_code == 200
        ov_data = res_ov.json()
        assert "pipeline_stages" in ov_data
        assert len(ov_data["pipeline_stages"]) == 14

        # 5. GET /v2/dashboard HTML includes pipeline UI and modal
        res_html = client.get("/v2/dashboard")
        assert res_html.status_code == 200
        assert "14-Stage Autonomous Trading Pipeline" in res_html.text
        assert "pipeline-stages-grid" in res_html.text
        assert "stage-modal" in res_html.text
