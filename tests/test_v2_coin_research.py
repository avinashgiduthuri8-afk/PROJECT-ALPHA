"""
Unit and Integration Tests for V2 On-Demand Coin Research & Intelligence Engine.

Covers:
  - Technical indicator computation (pure NumPy math: EMA, RSI, MACD, BB, ATR, RVOL)
  - Minervini VCP contraction stage detection
  - 100-Point 4-Pillar Quality Index scorecard
  - Single-coin on-demand backtesting with 1.572% statutory friction
  - Multi-horizon AI trend forecasting (rule-based)
  - REST API routes under /api/v2/research/*
  - Edge cases (invalid pairs, error handling, auth protection)
"""

from __future__ import annotations

import uuid
import numpy as np
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from v2.app_v2 import app
from v2.core.config import get_config, invalidate_config
from v2.services.research_service.symbol_normalizer import (
    normalize_symbol, is_supported_pair, get_supported_pairs_info
)
from v2.services.research_service.indicators import (
    compute_ema, compute_rsi, compute_macd, compute_bollinger,
    compute_atr, compute_rvol, last_valid
)
from v2.services.research_service.service import CoinResearchService


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    test_db = str(tmp_path / f"test_research_{uuid.uuid4().hex[:6]}.db")
    monkeypatch.setenv("V2_DB_PATH", test_db)
    monkeypatch.setenv("DASHBOARD_API_KEY", "test-research-key")
    invalidate_config()
    yield
    invalidate_config()


# ── 1. Symbol Normalizer Tests ────────────────────────────────────────────────

def test_symbol_normalization():
    assert normalize_symbol("BTC") == "BTC/INR"
    assert normalize_symbol("btc/inr") == "BTC/INR"
    assert normalize_symbol("BTCINR") == "BTC/INR"
    assert normalize_symbol("B-BTC_INR") == "BTC/INR"
    assert normalize_symbol("BTC-INR") == "BTC/INR"
    assert normalize_symbol("SOL/USDT") == "SOL/USDT"
    assert normalize_symbol("ZEC") == "ZEC/USDT"
    assert normalize_symbol("B-ETH_USDT") == "ETH/USDT"


def test_is_supported_pair():
    assert is_supported_pair("BTC/INR") is True
    assert is_supported_pair("ETH") is True
    assert is_supported_pair("SOL/USDT") is True
    assert is_supported_pair("FAKECOIN99/INR") is False

    info = get_supported_pairs_info()
    assert len(info) >= 30
    assert any(p["pair"] == "BTC/INR" for p in info)


# ── 2. Pure NumPy Indicator Math Tests ────────────────────────────────────────

def test_ema_computation():
    # 30 bars of constant price 100 -> EMA should converge to 100
    prices = np.full(30, 100.0)
    ema9 = compute_ema(prices, 9)
    assert not np.isnan(ema9[-1])
    assert pytest.approx(ema9[-1], abs=1e-3) == 100.0


def test_rsi_computation():
    # Strictly increasing prices -> RSI should be near 100
    prices = np.linspace(100, 200, 30)
    rsi = compute_rsi(prices, 14)
    assert last_valid(rsi) > 85.0

    # Strictly decreasing prices -> RSI should be near 0
    prices_down = np.linspace(200, 100, 30)
    rsi_down = compute_rsi(prices_down, 14)
    assert last_valid(rsi_down) < 15.0


def test_macd_computation():
    prices = np.linspace(100, 200, 50)
    macd, signal, hist = compute_macd(prices)
    assert not np.isnan(macd[-1])
    assert not np.isnan(signal[-1])
    # For upward trending, MACD line is above 0
    assert macd[-1] > 0


def test_bollinger_bands():
    prices = np.random.normal(100, 5, 50)
    upper, mid, lower = compute_bollinger(prices, 20, 2.0)
    assert not np.isnan(upper[-1])
    assert not np.isnan(mid[-1])
    assert not np.isnan(lower[-1])
    assert upper[-1] > mid[-1] > lower[-1]


def test_atr_and_rvol():
    n = 30
    highs = np.full(n, 105.0)
    lows = np.full(n, 95.0)
    closes = np.full(n, 100.0)
    volumes = np.full(n, 1000.0)
    volumes[-1] = 2500.0

    atr = compute_atr(highs, lows, closes, 14)
    assert pytest.approx(last_valid(atr), abs=0.5) == 10.0

    rvol = compute_rvol(volumes, 20)
    assert rvol == 2.5


# ── 3. CoinResearchService Core Methods ───────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_full_coin_profile():
    candle_repo = AsyncMock()
    # Generate 60 synthetic daily candles
    candles_1d = []
    base = 50000.0
    for i in range(60):
        candles_1d.append({
            "pair": "BTC/INR",
            "timeframe": "1d",
            "timestamp": 1700000000 + i * 86400,
            "open": base + i * 100,
            "high": base + i * 100 + 500,
            "low": base + i * 100 - 300,
            "close": base + i * 100 + 200,
            "volume": 1000.0,
        })
    candle_repo.get_recent_candles.return_value = candles_1d

    cfg = get_config()
    service = CoinResearchService(candle_repo, cfg)

    # Mock public client ticker
    with patch.object(service._public_client, "get_tickers", new_callable=AsyncMock) as mock_tick:
        mock_tick.return_value = [{
            "market": "BTCINR",
            "last_price": 55000.0,
            "change_24_hour": 3.5,
            "high": 56000.0,
            "low": 54000.0,
            "volume": 25000.0,
            "bid": 54990.0,
            "ask": 55010.0,
        }]

        profile = await service.fetch_full_coin_profile("BTC/INR")

    assert profile["pair"] == "BTC/INR"
    assert profile["ticker"]["ltp"] == 55000.0
    assert profile["ticker"]["change_24h_pct"] == 3.5
    assert "15m" in profile["indicators"]
    assert "1h" in profile["indicators"]
    assert "1d" in profile["indicators"]
    assert profile["vcp_setup"] is not None
    assert "total_score" in profile["scorecard"]
    assert 0 <= profile["scorecard"]["total_score"] <= 100


@pytest.mark.asyncio
async def test_run_on_demand_backtest():
    candle_repo = AsyncMock()
    cfg = get_config()
    service = CoinResearchService(candle_repo, cfg)

    result = await service.run_on_demand_backtest(
        symbol="BTC/INR",
        strategy="STE",
        days=30,
    )

    assert result["pair"] == "BTC/INR"
    assert result["strategy"] == "STE"
    assert result["days"] == 30
    assert "win_rate_pct" in result
    assert "net_pnl_pct" in result
    assert "profit_factor" in result or "net_profit_factor" in result
    assert "max_drawdown_pct" in result
    assert result["statutory_drag_pct"] == 1.572


@pytest.mark.asyncio
async def test_predict_trend_and_catalysts():
    candle_repo = AsyncMock()
    cfg = get_config()
    service = CoinResearchService(candle_repo, cfg)

    # Supply pre-computed indicators
    dummy_indicators = {
        "1h": {
            "status": "OK",
            "close": 55000.0,
            "ema21": 54000.0,
            "ema50": 53000.0,
            "rsi14": 62.0,
            "macd_hist": 25.0,
            "rvol": 1.6,
            "bb_lower": 52000.0,
            "bb_upper": 56000.0,
            "bb_mid": 54000.0,
            "bb_width_pct": 7.4,
        },
        "1d": {
            "status": "OK",
            "close": 55000.0,
            "ema21": 53500.0,
            "ema50": 52000.0,
            "rsi14": 65.0,
            "macd_hist": 45.0,
            "rvol": 1.4,
            "bb_lower": 51000.0,
            "bb_upper": 57000.0,
            "bb_mid": 54000.0,
            "bb_width_pct": 11.1,
        }
    }

    pred = await service.predict_trend_and_catalysts("BTC/INR", indicators=dummy_indicators)

    assert pred["pair"] == "BTC/INR"
    assert pred["method"] == "RULE_BASED"
    assert pred["horizons"]["1h"]["direction"] in ("BULLISH", "BEARISH", "CONSOLIDATION")
    assert pred["horizons"]["4h"]["direction"] in ("BULLISH", "BEARISH", "CONSOLIDATION")
    assert pred["horizons"]["24h"]["direction"] in ("BULLISH", "BEARISH", "CONSOLIDATION")
    assert len(pred["bullish_catalysts"]) > 0
    assert len(pred["key_support_levels"]) > 0


# ── 4. REST API Endpoint Tests via TestClient ─────────────────────────────────

def test_api_list_research_coins():
    with TestClient(app) as client:
        # Unauthorized without header
        resp_unauth = client.get("/api/v2/research/coins")
        assert resp_unauth.status_code == 401

        # Authorized
        resp = client.get("/api/v2/research/coins", headers={"X-API-Key": "test-research-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 30
        assert any(d["pair"] == "BTC/INR" for d in data)


def test_api_get_coin_profile_edge_case_404():
    with TestClient(app) as client:
        resp = client.get(
            "/api/v2/research/coin/NONEXISTENTCOIN999",
            headers={"X-API-Key": "test-research-key"}
        )
        assert resp.status_code == 404
        assert "Unsupported pair" in resp.json()["detail"]


def test_api_backtest_endpoint():
    with TestClient(app) as client:
        payload = {
            "symbol": "BTC/INR",
            "strategy": "STE",
            "days": 30
        }
        resp = client.post(
            "/api/v2/research/backtest",
            json=payload,
            headers={"X-API-Key": "test-research-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pair"] == "BTC/INR"
        assert data["strategy"] == "STE"
        assert data["days"] == 30
        assert "win_rate_pct" in data
        assert "net_pnl_pct" in data
        assert data["statutory_drag_pct"] == 1.572


def test_api_predict_endpoint():
    with TestClient(app) as client:
        payload = {"symbol": "BTC/INR"}
        resp = client.post(
            "/api/v2/research/predict",
            json=payload,
            headers={"X-API-Key": "test-research-key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pair"] == "BTC/INR"
        assert "horizons" in data
        assert "1h" in data["horizons"]
        assert "4h" in data["horizons"]
        assert "24h" in data["horizons"]
