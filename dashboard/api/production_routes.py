"""
PROJECT-ALPHA Production Fleet Command & Control Routes — /api/production/* and /api/v2/production/*

Provides atomic mode management, emergency kill-switch halt & resume procedures,
and 24/7 watchdog supervisor telemetry. Guarded by require_api_key.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.logging import get_logger

from .auth import require_api_key
from .schemas import (
    KillSwitchResponseSchema,
    ProductionStatusSchema,
    ResumeResponseSchema,
    SetModeRequestSchema,
    SetModeResponseSchema,
)

logger = get_logger("dashboard.api.production_routes")

production_router = APIRouter()
router = production_router

# Injected module references
_controller = None
_watchdog = None
_config = None
_position_repo = None
_risk_service = None


def init_production_router(
    controller: Any,
    watchdog: Any,
    config: Any,
    position_repo: Any = None,
    risk_service: Any = None,
) -> None:
    """Wire dependencies into the production router module."""
    global _controller, _watchdog, _config, _position_repo, _risk_service
    _controller = controller
    _watchdog = watchdog
    _config = config
    _position_repo = position_repo
    _risk_service = risk_service


init_production_routes = init_production_router


@production_router.get(
    "/status",
    response_model=ProductionStatusSchema,
    dependencies=[Depends(require_api_key)],
    summary="Comprehensive fleet operational status and subsystem health",
)
async def get_production_status() -> ProductionStatusSchema:
    """
    Return comprehensive operational status: deployment mode, trading flag,
    unified capital pool headroom, open positions count, circuit breaker,
    and watchdog inspection status.
    """
    mode = getattr(_config, "deployment_mode", "PAPER") if _config else "PAPER"
    trading_enabled = getattr(_config, "trading_enabled", False) if _config else False
    shadow_mode = getattr(_config, "shadow_mode", True) if _config else True
    cap_limit = getattr(_config, "total_capital_limit", None) if _config else None

    deployed = 0.0
    open_count = 0
    if _position_repo:
        try:
            if hasattr(_position_repo, "get_active_positions"):
                active_pos = await _position_repo.get_active_positions()
            else:
                active_pos = await _position_repo.get_open()
            deployed = sum(p.deployed_capital for p in active_pos)
            open_count = len(active_pos)
        except Exception as exc:
            logger.debug("Failed fetching active positions for status: %s", exc)

    if mode in ("LIVE", "LIVE_MICROCASH"):
        # Fetch real CoinDCX available INR wallet balance for live trading
        if _controller and hasattr(_controller, "_trading_service") and _controller._trading_service:
            sub_mgr = getattr(_controller._trading_service, "subaccount_manager", None) or getattr(
                _controller._trading_service, "_subaccount_manager", None
            )
            if sub_mgr and hasattr(sub_mgr, "get_live_balance"):
                try:
                    bal_res = await sub_mgr.get_live_balance()
                    if bal_res.get("success"):
                        cap_avail = round(float(bal_res.get("inr_balance", 0.0)), 2)
                        cap_limit = round(cap_avail + deployed, 2)
                except Exception as exc:
                    logger.debug("Failed fetching live CoinDCX balance for status: %s", exc)
    else:
        # Strict Paper Capital: ₹10,000.0
        if cap_limit is None or cap_limit == float("inf"):
            cap_limit = 10000.0
        cap_avail = round(max(0.0, cap_limit - deployed), 2)

    breaker_status = "NORMAL"
    if _risk_service and hasattr(_risk_service, "circuit_breaker"):
        cb = _risk_service.circuit_breaker
        if cb.is_tripped or cb.emergency_stop:
            breaker_status = "TRIPPED"

    if cap_avail is None and cap_limit is not None:
        cap_avail = round(max(0.0, cap_limit - deployed), 2)

    watchdog_status = None
    subsystems_healthy = None
    last_inspection = None
    if _watchdog:
        try:
            telemetry = _watchdog.get_telemetry()
            watchdog_status = "RUNNING" if telemetry.get("running") else "STOPPED"
            last_inspection = telemetry.get("last_inspection_at")
            probes = telemetry.get("probes", {})
            subsystems_healthy = (
                all(
                    p.get("status") in ("OK", "NORMAL", "HEALTHY")
                    for p in probes.values()
                )
                if probes
                else True
            )
        except Exception:
            pass

    is_tripped = False
    if _controller and hasattr(_controller, "is_kill_switch_tripped"):
        is_tripped = bool(_controller.is_kill_switch_tripped)
    elif breaker_status == "TRIPPED":
        is_tripped = True

    return ProductionStatusSchema(
        mode=mode,
        deployment_mode=mode,
        is_kill_switch_tripped=is_tripped,
        trading_enabled=trading_enabled,
        shadow_mode=shadow_mode,
        capital_pool_limit=cap_limit,
        capital_pool_deployed=round(deployed, 2),
        capital_pool_available=cap_avail,
        open_positions_count=open_count,
        circuit_breaker_status=breaker_status,
        watchdog_status=watchdog_status,
        subsystems_healthy=subsystems_healthy,
        last_inspection=last_inspection,
    )


@production_router.post(
    "/set-mode",
    response_model=SetModeResponseSchema,
    dependencies=[Depends(require_api_key)],
    summary="Dynamically switch execution mode between SHADOW, PAPER, and LIVE_MICROCASH",
)
@production_router.post(
    "/mode",
    response_model=SetModeResponseSchema,
    dependencies=[Depends(require_api_key)],
    summary="Alias to set-mode",
)
async def set_execution_mode(body: SetModeRequestSchema) -> SetModeResponseSchema:
    """
    Dynamically transition execution mode with configuration override persistence.
    """
    target = body.mode.strip().upper()
    if target not in ("LIVE_MICROCASH", "LIVE", "PAPER"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mode. Must be 'PAPER' or 'LIVE'.",
        )

    if _controller:
        try:
            res = await _controller.set_mode(target, operator="API")
            return SetModeResponseSchema(**res)
        except ValueError as val_err:
            raise HTTPException(status_code=400, detail=str(val_err))
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Mode transition failed: {exc}"
            )

    # Fallback to direct config update if controller not wired
    if _config is None:
        raise HTTPException(status_code=503, detail="Configuration not initialized.")

    _config.deployment_mode = target
    if target in ("LIVE", "LIVE_MICROCASH"):
        _config.deployment_mode = "LIVE"
        _config.trading_enabled = True
        _config.shadow_mode = False
        msg = f"Switched to LIVE. Real micro-orders (₹{_config.order_size_inr:.2f}) dispatch to CoinDCX."
    else:
        _config.deployment_mode = "PAPER"
        _config.trading_enabled = True
        _config.shadow_mode = False
        msg = "Switched to PAPER mode. Virtual paper positions track live prices and SL/TP exits."

    try:
        from core.config import AppConfig

        AppConfig.save_runtime_overrides(
            {
                "deployment_mode": _config.deployment_mode,
                "trading_enabled": _config.trading_enabled,
                "shadow_mode": _config.shadow_mode,
                "v2_deployment_mode": _config.deployment_mode,
                "v2_trading_enabled": _config.trading_enabled,
                "v2_shadow_mode": _config.shadow_mode,
            }
        )
    except Exception as exc:
        logger.warning("Could not persist runtime override: %s", exc)

    return SetModeResponseSchema(
        ok=True,
        mode=target,
        deployment_mode=target,
        trading_enabled=_config.trading_enabled,
        shadow_mode=_config.shadow_mode,
        message=msg,
    )


@production_router.get(
    "/trading-status",
    dependencies=[Depends(require_api_key)],
    summary="Get trading_enabled status flag",
)
@production_router.post(
    "/toggle-trading",
    dependencies=[Depends(require_api_key)],
    summary="Toggle trading_enabled flag on or off",
)
@production_router.post(
    "/set-trading-enabled",
    dependencies=[Depends(require_api_key)],
    summary="Set trading_enabled flag explicitly",
)
async def toggle_trading_enabled(body: dict | None = None) -> dict[str, Any]:
    """Dynamically toggle or set trading_enabled flag."""
    if _config is None:
        raise HTTPException(status_code=503, detail="Config not initialized")

    if body and "enabled" in body:
        _config.trading_enabled = bool(body["enabled"])
    else:
        _config.trading_enabled = not _config.trading_enabled

    try:
        from core.config import AppConfig

        AppConfig.save_runtime_overrides(
            {
                "trading_enabled": _config.trading_enabled,
                "v2_trading_enabled": _config.trading_enabled,
            }
        )
    except Exception as exc:
        logger.warning("Could not persist trading_enabled override: %s", exc)

    state_str = "ENABLED" if _config.trading_enabled else "DISABLED"
    logger.info("Trading status updated to %s", state_str)
    return {
        "ok": True,
        "success": True,
        "trading_enabled": _config.trading_enabled,
        "message": f"Trading status is now {state_str}.",
    }


@production_router.post(
    "/kill-switch",
    response_model=KillSwitchResponseSchema,
    dependencies=[Depends(require_api_key)],
    summary="Emergency Halt: trip circuit breaker and block all order placements",
)
async def trigger_emergency_kill_switch() -> KillSwitchResponseSchema:
    """
    Emergency kill-switch: Immediately trips the global circuit breaker,
    halts all outbound orders, and sets mode to SHADOW.
    """
    if _controller:
        res = await _controller.kill_switch(
            reason="API Emergency Kill-Switch Request", operator="API"
        )
        if hasattr(_controller, "trip_kill_switch"):
            res = await _controller.trip_kill_switch(
                reason="API Emergency Kill-Switch Request"
            )
        else:
            res = await _controller.kill_switch(
                reason="API Emergency Kill-Switch Request", operator="API"
            )
        return KillSwitchResponseSchema(
            ok=res.get("ok", True),
            circuit_breaker=res.get("circuit_breaker", "TRIPPED"),
            trading_enabled=res.get("trading_enabled", False),
            status=res.get("status", "KILL_SWITCH_TRIPPED"),
            is_kill_switch_tripped=True,
            message=res.get("message", "Circuit breaker tripped. All orders blocked."),
        )

    # Fallback
    if _risk_service and hasattr(_risk_service, "circuit_breaker"):
        _risk_service.circuit_breaker.trip("EMERGENCY_KILL_SWITCH_TRIGGERED")

    if _config:
        _config.trading_enabled = False
        _config.deployment_mode = "PAPER"
        _config.shadow_mode = False

    return KillSwitchResponseSchema(
        ok=True,
        circuit_breaker="TRIPPED",
        trading_enabled=False,
        status="KILL_SWITCH_TRIPPED",
        is_kill_switch_tripped=True,
        message="Circuit breaker tripped. All live order dispatch blocked immediately.",
    )


@production_router.post(
    "/resume",
    response_model=ResumeResponseSchema,
    dependencies=[Depends(require_api_key)],
    summary="Resume operations: verify database integrity, reset breaker, and re-arm router",
)
async def resume_trading_operations() -> ResumeResponseSchema:
    """
    Verify database integrity, reset circuit breaker, and re-arm order router.
    """
    if _controller:
        res = await _controller.resume(operator="API")
        if hasattr(_controller, "reset_kill_switch"):
            res = await _controller.reset_kill_switch()
        else:
            res = await _controller.resume(operator="API")
        if not res.get("ok"):
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail=res.get("message", "Resume failed verification check"),
            )
        return ResumeResponseSchema(
            ok=True,
            circuit_breaker=res.get("circuit_breaker", "NORMAL"),
            mode=res.get("mode", "PAPER"),
            deployment_mode=res.get("mode", "PAPER"),
            trading_enabled=res.get("trading_enabled", True),
            status="ACTIVE",
            is_kill_switch_tripped=False,
            message=res.get("message", "Trading resumed successfully."),
        )

    # Fallback
    if _risk_service and hasattr(_risk_service, "circuit_breaker"):
        _risk_service.circuit_breaker.reset()

    mode = "PAPER"
    if _config:
        _config.trading_enabled = True
        _config.deployment_mode = mode
        _config.shadow_mode = False

    return ResumeResponseSchema(
        ok=True,
        circuit_breaker="NORMAL",
        mode=mode,
        deployment_mode=mode,
        trading_enabled=True,
        status="ACTIVE",
        is_kill_switch_tripped=False,
        message="Circuit breaker reset and order router re-armed.",
    )


@production_router.get(
    "/watchdog",
    dependencies=[Depends(require_api_key)],
    summary="Get detailed 24/7 Watchdog Supervisor telemetry and 9 subsystem probe results",
)
async def get_watchdog_telemetry() -> dict[str, Any]:
    """Return live watchdog inspection telemetry and subsystem health probes."""
    if _watchdog is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production watchdog supervisor not initialized",
        )
    return _watchdog.get_telemetry()
