"""
Unit & Integration Tests for Multi-Quote Pair Resolution, USDT Fallback,
Dual-Currency Order Sizing & High-Frequency Price Ticker.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from fastapi.testclient import TestClient

from v2.services.research_service.symbol_normalizer import (
    resolve_tradeable_pairs,
    normalize_symbol,
    is_supported_symbol,
    get_preferred_pair_for_base,
    get_base_asset,
    get_quote_currency,
)
from v2.trading.precision_rules import (
    get_pair_spec,
    round_qty_up,
    round_qty_down,
    validate_order_notional,
)
from v2.services.trading_service.auto_trader import AutoTradeRouter
from v2.bus.event_bus import EventBus
from v2.core.config import invalidate_config
from v2.app_v2 import app



@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-key")
    invalidate_config()
    yield
    invalidate_config()



def test_symbol_normalizer_inr_priority():
    """Verify INR priority when both INR and USDT pairs are available."""
    res_sol = resolve_tradeable_pairs("SOL")
    assert res_sol["base_asset"] == "SOL"
    assert res_sol["primary_pair"] == "SOL/INR"
    assert res_sol["preferred_quote"] == "INR"
    assert res_sol["has_inr"] is True
    assert res_sol["has_usdt"] is True
    assert len(res_sol["available_pairs"]) >= 2

    # Direct check for normalize_symbol
    assert normalize_symbol("SOL") == "SOL/INR"
    assert normalize_symbol("SOL/USDT") == "SOL/USDT"
    assert normalize_symbol("SOLUSDT") == "SOL/USDT"
    assert normalize_symbol("B-SOL_INR") == "SOL/INR"
    assert normalize_symbol("B-SOL_USDT") == "SOL/USDT"


def test_symbol_normalizer_usdt_fallback():
    """Verify automatic fallback to USDT when INR pair is not active."""
    res_render = resolve_tradeable_pairs("RENDER")
    assert res_render["base_asset"] == "RENDER"
    assert res_render["primary_pair"] == "RENDER/USDT"
    assert res_render["preferred_quote"] == "USDT"
    assert res_render["has_inr"] is False
    assert res_render["has_usdt"] is True

    assert normalize_symbol("RENDER") == "RENDER/USDT"
    assert normalize_symbol("RENDER/USDT") == "RENDER/USDT"
    assert normalize_symbol("B-RENDER_USDT") == "RENDER/USDT"

    # Pepe test
    res_pepe = resolve_tradeable_pairs("PEPE")
    assert res_pepe["primary_pair"] == "PEPE/USDT"
    assert res_pepe["preferred_quote"] == "USDT"


def test_precision_rules_usdt_specs():
    """Verify USDT pair specs and precision rounding."""
    sol_usdt = get_pair_spec("SOL/USDT")
    assert sol_usdt["quote_currency"] == "USDT"
    assert sol_usdt["min_notional_usdt"] == 1.0

    render_usdt = get_pair_spec("RENDER/USDT")
    assert render_usdt["quote_currency"] == "USDT"
    assert render_usdt["min_quantity"] > 0

    # Test round_qty_up
    raw_qty = 0.0123456
    rounded = round_qty_up("SOL/USDT", raw_qty)
    assert rounded >= raw_qty

    # Test validate_order_notional
    # ₹200 equivalent in USDT is ~2.18 USDT at 91.50 rate
    assert validate_order_notional("SOL/USDT", 0.02, 130.0) is True
    assert validate_order_notional("SOL/USDT", 0.001, 130.0) is False  # 0.13 USDT < 1.0 USDT


@pytest.mark.asyncio
async def test_cross_currency_single_coin_asset_lock():
    """Verify that having an open SOL/INR position blocks opening a new SOL/USDT position."""
    mock_bus = MagicMock(spec=EventBus)
    mock_pos_repo = MagicMock()
    
    # Mock active position on SOL/INR
    mock_pos = MagicMock()
    mock_pos.coin = "SOL"
    mock_pos.pair = "SOL/INR"
    mock_pos.bot = "STE"
    mock_pos_repo.get_open.return_value = [mock_pos]

    router = AutoTradeRouter(bus=mock_bus, position_repo=mock_pos_repo, dry_run=True)

    # Attempt to route signal for SOL/USDT
    signal_usdt = {
        "bot": "STE",
        "symbol": "SOL/USDT",
        "pair": "SOL/USDT",
        "coin": "SOL",
        "opportunity_type": "momentum_breakout",
        "price": 135.0,
        "stop_loss": 130.0,
        "target_1": 145.0,
        "target_2": 150.0,
        "confidence": 0.88,
    }

    result = await router.handle_signal(signal_usdt)
    assert result["success"] is False
    assert result["error"] == "OPPORTUNITY_LOCKED_ACTIVE_PAIR"
    assert "SOL" in result["message"]


def test_api_research_pairs_discovery():
    """Test GET /api/v2/research/pairs/{symbol} API endpoint."""
    headers = {"X-API-Key": "test-key"}
    with TestClient(app) as client:
        # Test SOL
        resp = client.get("/api/v2/research/pairs/SOL", headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"STATUS {resp.status_code} BODY {resp.text}")
        data = resp.json()
        assert data["base_asset"] == "SOL"
        assert data["preferred_quote"] == "INR"
        assert data["has_inr"] is True
        assert data["has_usdt"] is True
        assert data["usdt_inr_rate"] > 0
        assert any("INR" in p for p in data["available_pairs"])
        assert any("USDT" in p for p in data["available_pairs"])

        # Test RENDER
        resp_render = client.get("/api/v2/research/pairs/RENDER", headers=headers)
        assert resp_render.status_code == 200
        data_render = resp_render.json()
        assert data_render["base_asset"] == "RENDER"
        assert data_render["preferred_quote"] == "USDT"
        assert data_render["has_usdt"] is True


def test_api_research_ticker_endpoint():
    """Test GET /api/v2/research/ticker/{symbol} API endpoint."""
    headers = {"X-API-Key": "test-key"}
    with TestClient(app) as client:
        # Test SOL/INR ticker
        resp = client.get("/api/v2/research/ticker/SOL/INR", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "symbol" in data
        assert "ltp" in data
        assert "quote_currency" in data
        assert data["quote_currency"] == "INR"
        assert "usdt_inr_rate" in data
        assert data["usdt_inr_rate"] > 0
        assert "usdt_equivalent_ltp" in data

        # Test USDT pair ticker
        resp_usdt = client.get("/api/v2/research/ticker/SOL/USDT", headers=headers)
        assert resp_usdt.status_code == 200
        data_usdt = resp_usdt.json()
        assert data_usdt["quote_currency"] == "USDT"
        assert "inr_equivalent_ltp" in data_usdt


