"""
tests/test_live_safety_gate.py — Comprehensive unit & regression tests for FIX 1, 2, and 3.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from background.production.safety_gate import verify_live_mode_safety_gate
from core.config import AppConfig
from telegram.formatters import (
    format_telegram_capital,
    format_telegram_health,
    format_telegram_status,
)


@pytest.mark.asyncio
async def test_safety_gate_blocks_on_missing_credentials():
    """Verify safety gate blocks transition when API credentials are not set."""
    cfg = AppConfig()
    cfg.coindcx_api_key = ""
    cfg.coindcx_api_secret = ""

    with patch.dict(os.environ, {"COINDCX_API_KEY": "", "COINDCX_API_SECRET": ""}, clear=True):
        passed, reason, bal = await verify_live_mode_safety_gate(config=cfg)
        assert passed is False
        assert "credentials" in reason.lower()
        assert bal is None


@pytest.mark.asyncio
async def test_safety_gate_blocks_on_dummy_credentials():
    """Verify safety gate blocks when placeholder/dummy keys are detected."""
    cfg = AppConfig()
    cfg.coindcx_api_key = "dummy_key_12345"
    cfg.coindcx_api_secret = "dummy_secret_12345"

    with patch.dict(os.environ, {"COINDCX_API_KEY": "mock_api_key_12345", "COINDCX_API_SECRET": "mock_secret_12345"}):
        passed, reason, bal = await verify_live_mode_safety_gate(config=cfg)
        assert passed is False
        assert "placeholder" in reason.lower() or "invalid" in reason.lower()
        assert bal is None


@pytest.mark.asyncio
async def test_safety_gate_blocks_on_tripped_circuit_breaker():
    """Verify safety gate blocks when Risk Engine circuit breaker is open."""
    cfg = AppConfig()
    cfg.coindcx_api_key = "real_coindcx_api_key_valid_1234"
    cfg.coindcx_api_secret = "real_coindcx_api_secret_valid_1234"

    mock_risk = MagicMock()
    mock_risk.circuit_breaker.is_open = True
    mock_risk.circuit_breaker.reason = "Max Drawdown Breached"

    with patch.dict(os.environ, {"COINDCX_API_KEY": "real_coindcx_api_key_valid_1234", "COINDCX_API_SECRET": "real_coindcx_api_secret_valid_1234"}):
        passed, reason, bal = await verify_live_mode_safety_gate(config=cfg, risk_service=mock_risk)
        assert passed is False
        assert "circuit breaker" in reason.lower()


@pytest.mark.asyncio
async def test_safety_gate_blocks_on_insufficient_inr_balance():
    """Verify safety gate blocks when CoinDCX balance is less than required ₹200 order size."""
    cfg = AppConfig()
    cfg.coindcx_api_key = "real_coindcx_api_key_valid_1234"
    cfg.coindcx_api_secret = "real_coindcx_api_secret_valid_1234"
    cfg.order_size_inr = 200.0

    mock_sub_mgr = AsyncMock()
    mock_sub_mgr.get_live_balance.return_value = {
        "success": True,
        "inr_balance": 0.00235,  # Real-world VPS test case
        "inr_locked": 0.0,
    }

    with patch.dict(os.environ, {"COINDCX_API_KEY": "real_coindcx_api_key_valid_1234", "COINDCX_API_SECRET": "real_coindcx_api_secret_valid_1234"}):
        passed, reason, bal = await verify_live_mode_safety_gate(
            config=cfg, subaccount_manager=mock_sub_mgr
        )
        assert passed is False
        assert "insufficient" in reason.lower()
        assert bal == 0.00235


@pytest.mark.asyncio
async def test_safety_gate_blocks_on_coindcx_api_failure():
    """Verify safety gate blocks when CoinDCX returns an authentication error."""
    cfg = AppConfig()
    cfg.coindcx_api_key = "real_coindcx_api_key_valid_1234"
    cfg.coindcx_api_secret = "real_coindcx_api_secret_valid_1234"

    mock_sub_mgr = AsyncMock()
    mock_sub_mgr.get_live_balance.return_value = {
        "success": False,
        "error": "AUTH_FAILED",
        "message": "Invalid API Key or HMAC Signature",
    }

    with patch.dict(os.environ, {"COINDCX_API_KEY": "real_coindcx_api_key_valid_1234", "COINDCX_API_SECRET": "real_coindcx_api_secret_valid_1234"}):
        passed, reason, bal = await verify_live_mode_safety_gate(
            config=cfg, subaccount_manager=mock_sub_mgr
        )
        assert passed is False
        assert "auth" in reason.lower() or "connectivity" in reason.lower()
        assert bal is None


@pytest.mark.asyncio
async def test_safety_gate_passes_when_all_invariants_met():
    """Verify safety gate passes when all 7 safety invariants are valid."""
    cfg = AppConfig()
    cfg.coindcx_api_key = "real_coindcx_api_key_valid_1234"
    cfg.coindcx_api_secret = "real_coindcx_api_secret_valid_1234"
    cfg.order_size_inr = 200.0

    mock_risk = MagicMock()
    mock_risk.circuit_breaker.is_open = False
    mock_risk.is_kill_switch_tripped = False

    mock_sub_mgr = AsyncMock()
    mock_sub_mgr.get_live_balance.return_value = {
        "success": True,
        "inr_balance": 5000.0,
        "inr_locked": 0.0,
    }

    with patch.dict(os.environ, {"COINDCX_API_KEY": "real_coindcx_api_key_valid_1234", "COINDCX_API_SECRET": "real_coindcx_api_secret_valid_1234"}):
        passed, reason, bal = await verify_live_mode_safety_gate(
            config=cfg, risk_service=mock_risk, subaccount_manager=mock_sub_mgr
        )
        assert passed is True
        assert "verified" in reason.lower()
        assert bal == 5000.0


def test_formatters_coindcx_unavailable():
    """Verify formatters correctly display COINDCX_UNAVAILABLE when balance is missing in LIVE mode."""
    # /capital formatter
    cap_data = {
        "mode": "LIVE_MICROCASH",
        "available_capital": None,
        "deployed_capital": 0.0,
        "source": "COINDCX_UNAVAILABLE",
    }
    text = format_telegram_capital(cap_data)
    assert "COINDCX_UNAVAILABLE" in text

    # /status formatter
    status_data = {
        "mode": "LIVE_MICROCASH",
        "available_capital": None,
        "order_amount_inr": 200.0,
    }
    status_text = format_telegram_status(status_data)
    assert "COINDCX_UNAVAILABLE" in status_text

    # /health formatter
    health_data = {
        "mode": "LIVE_MICROCASH",
        "components": {
            "scanner": True,
            "ai": True,
            "risk": True,
            "execution": True,
            "database": True,
            "event_bus": True,
            "coindcx": False,
        },
        "overall": "DEGRADED",
    }
    health_text = format_telegram_health(health_data)
    assert "CoinDCX       🔴" in health_text
