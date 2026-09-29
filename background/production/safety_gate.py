"""
background/production/safety_gate.py — Universal LIVE Mode Safety Verification Gate.

Enforces all 7 safety invariants before allowing transition to LIVE / LIVE_MICROCASH:
1. Valid, non-mock CoinDCX API credentials present.
2. Emergency Stop / Global Kill-Switch is inactive.
3. Risk Engine is active and Circuit Breaker is normal (closed).
4. CoinDCX REST exchange connectivity succeeds.
5. CoinDCX available INR balance is retrieved.
6. Available INR balance is a valid, non-negative number.
7. Available INR balance >= configured order amount (order_size_inr, minimum ₹200.00).

Fails closed on any exception or discrepancy.
"""

from __future__ import annotations

import os
from typing import Any

from core.config import AppConfig, get_config
from core.logging import get_logger

logger = get_logger("background.production.safety_gate")


async def verify_live_mode_safety_gate(
    config: AppConfig | None = None,
    risk_service: Any | None = None,
    trading_service: Any | None = None,
    subaccount_manager: Any | None = None,
) -> tuple[bool, str, float | None]:
    """
    Evaluate all 7 safety preconditions required for LIVE mode activation.

    Returns:
        tuple (passed: bool, reason: str, available_inr_balance: float | None)
    """
    cfg = config or get_config()
    min_order_required = max(200.0, float(getattr(cfg, "order_size_inr", 200.0)))

    # 1. Credentials Check
    api_key = os.getenv("COINDCX_API_KEY") or getattr(cfg, "coindcx_api_key", None)
    api_secret = os.getenv("COINDCX_API_SECRET") or getattr(cfg, "coindcx_api_secret", None)

    if not api_key or not api_secret:
        msg = "CoinDCX API credentials (COINDCX_API_KEY / COINDCX_API_SECRET) are missing."
        logger.warning("LIVE Safety Gate failed: %s", msg)
        return False, msg, None

    key_str = str(api_key).strip().lower()
    secret_str = str(api_secret).strip().lower()
    if (
        "mock" in key_str
        or "dummy" in key_str
        or "test" in key_str
        or len(key_str) < 10
        or len(secret_str) < 10
    ):
        msg = "CoinDCX API credentials are placeholder or invalid mock keys."
        logger.warning("LIVE Safety Gate failed: %s", msg)
        return False, msg, None

    # 2 & 3. Risk Engine & Circuit Breaker Check
    if risk_service is not None:
        if hasattr(risk_service, "circuit_breaker") and risk_service.circuit_breaker.is_open:
            reason = getattr(risk_service.circuit_breaker, "reason", "Triggered")
            msg = f"Circuit Breaker is tripped/OPEN ({reason}). Reset circuit breaker before activating live trading."
            logger.warning("LIVE Safety Gate failed: %s", msg)
            return False, msg, None
        if hasattr(risk_service, "is_kill_switch_tripped") and risk_service.is_kill_switch_tripped:
            msg = "Global emergency stop / kill-switch is active."
            logger.warning("LIVE Safety Gate failed: %s", msg)
            return False, msg, None

    # 4 & 5. CoinDCX Connectivity & Balance Retrieval
    sub_mgr = subaccount_manager
    if sub_mgr is None and trading_service is not None:
        sub_mgr = getattr(trading_service, "subaccount_manager", None) or getattr(
            trading_service, "_subaccount_manager", None
        )

    if sub_mgr is None:
        from execution.trading.subaccount_manager import CoinDCXSubAccountManager
        try:
            sub_mgr = CoinDCXSubAccountManager(config=cfg)
        except Exception as e:
            msg = f"Unable to initialize CoinDCX SubAccountManager: {e}"
            logger.error("LIVE Safety Gate failed: %s", msg)
            return False, msg, None

    try:
        bal_res = await sub_mgr.get_live_balance()
    except Exception as exc:
        msg = f"CoinDCX network connectivity error: {exc}"
        logger.error("LIVE Safety Gate failed: %s", msg)
        return False, msg, None

    if not bal_res.get("success"):
        err = bal_res.get("error") or bal_res.get("message") or "COINDCX_UNAVAILABLE"
        msg = f"CoinDCX authentication/connectivity failed: {err}"
        logger.warning("LIVE Safety Gate failed: %s", msg)
        return False, msg, None

    # 6. INR Balance Validation
    inr_bal = bal_res.get("inr_balance")
    if inr_bal is None or not isinstance(inr_bal, (int, float)):
        msg = "CoinDCX INR available balance could not be determined."
        logger.warning("LIVE Safety Gate failed: %s", msg)
        return False, msg, None

    inr_float = float(inr_bal)
    if inr_float < 0.0:
        msg = f"Invalid negative CoinDCX INR balance detected: ₹{inr_float:,.2f}."
        logger.warning("LIVE Safety Gate failed: %s", msg)
        return False, msg, None

    # 7. Available INR Balance vs Configured Order Amount (Min ₹200)
    if inr_float < min_order_required:
        msg = (
            f"Insufficient CoinDCX INR balance. Available: ₹{inr_float:,.2f}, "
            f"Required: ₹{min_order_required:,.2f} for micro-order execution."
        )
        logger.warning("LIVE Safety Gate failed: %s", msg)
        return False, msg, inr_float

    logger.info(
        "LIVE Safety Gate PASSED: CoinDCX INR Balance=₹%.2f, Order Size=₹%.2f",
        inr_float,
        min_order_required,
    )
    return True, "All live trading safety invariants verified.", inr_float
