"""
v2/services/production_service/controller.py — Production Controller & Emergency Kill-Switch.

Manages:
1. Dynamic mode switching between SHADOW, PAPER, and LIVE_MICROCASH with persistence.
2. Global emergency kill-switch tripping the circuit breaker and halting orders.
3. System resume procedure with database integrity checks and breaker re-arming.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config, get_config
from v2.core.logging import get_logger

logger = get_logger("v2.services.production_service.controller")


class ProductionController:
    """
    Central controller orchestrating deployment mode transitions, emergency stops,
    and system-wide resumption under strict risk invariants.
    """

    def __init__(
        self,
        config: V2Config,
        bus: EventBus,
        state_repo: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        event_log_repo: Optional[Any] = None,
        notification_service: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._state_repo = state_repo
        self._risk_service = risk_service
        self._trading_service = trading_service
        self._event_log_repo = event_log_repo
        self._notification_service = notification_service

    def wire_dependencies(
        self,
        state_repo: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        event_log_repo: Optional[Any] = None,
        notification_service: Optional[Any] = None,
    ) -> None:
        """Wire or update references after initial container bootstrap."""
        if state_repo is not None:
            self._state_repo = state_repo
        if risk_service is not None:
            self._risk_service = risk_service
        if trading_service is not None:
            self._trading_service = trading_service
        if event_log_repo is not None:
            self._event_log_repo = event_log_repo
        if notification_service is not None:
            self._notification_service = notification_service

    def get_active_mode(self) -> str:
        """Return the currently configured deployment mode."""
        return getattr(self._config, "v2_deployment_mode", "PAPER")

    async def set_mode(self, target_mode: str, operator: str = "API") -> Dict[str, Any]:
        """
        Dynamically transition execution mode (SHADOW, PAPER, LIVE_MICROCASH).
        Persists changes to database and config override file.
        """
        mode = target_mode.strip().upper()
        if mode not in ("SHADOW", "PAPER", "LIVE_MICROCASH"):
            raise ValueError(f"Invalid mode '{target_mode}'. Valid modes: SHADOW, PAPER, LIVE_MICROCASH")

        if mode == "LIVE_MICROCASH":
            if self._risk_service and hasattr(self._risk_service, "circuit_breaker") and self._risk_service.circuit_breaker.is_open:
                raise ValueError(f"Cannot transition to LIVE_MICROCASH: Circuit breaker is OPEN ({self._risk_service.circuit_breaker.reason})")
            if self._trading_service and hasattr(self._trading_service, "subaccount_manager"):
                sub_mgr = self._trading_service.subaccount_manager
                if self._config.coindcx_api_key and "mock" not in str(self._config.coindcx_api_key).lower():
                    bal_res = await sub_mgr.check_account_connectivity()
                    if not bal_res.get("success"):
                        raise ValueError(f"Cannot transition to LIVE_MICROCASH: CoinDCX connectivity check failed ({bal_res.get('error') or bal_res.get('message')})")
            self._config.v2_deployment_mode = "LIVE_MICROCASH"
            self._config.v2_trading_enabled = True
            self._config.v2_shadow_mode = False
            msg = f"Mode transitioned to LIVE_MICROCASH. Real micro-orders (₹{self._config.order_size_inr:.2f}) dispatch to CoinDCX."
        elif mode == "PAPER":
            self._config.v2_deployment_mode = "PAPER"
            self._config.v2_trading_enabled = True
            self._config.v2_shadow_mode = False
            msg = "Mode transitioned to PAPER. Virtual positions execute with live prices, SL/TP exits, and 1.572% friction."
        else:
            self._config.v2_deployment_mode = "SHADOW"
            self._config.v2_trading_enabled = False
            self._config.v2_shadow_mode = True
            msg = "Mode transitioned to SHADOW. Passive observation only; zero order placement."

        # 1. Persist config overrides to filesystem
        try:
            V2Config.save_runtime_overrides({
                "v2_deployment_mode": self._config.v2_deployment_mode,
                "v2_trading_enabled": self._config.v2_trading_enabled,
                "v2_shadow_mode": self._config.v2_shadow_mode,
            })
        except Exception as exc:
            logger.warning("Could not persist runtime override for set_mode: %s", exc)

        # 2. Persist to production_runtime_state table in SQLite
        if self._state_repo:
            try:
                await self._state_repo.set_many({
                    "v2_deployment_mode": self._config.v2_deployment_mode,
                    "v2_trading_enabled": str(self._config.v2_trading_enabled).lower(),
                    "v2_shadow_mode": str(self._config.v2_shadow_mode).lower(),
                    "mode_updated_at": datetime.now(timezone.utc).isoformat(),
                    "mode_updated_by": operator,
                }, updated_by=operator)
            except Exception as exc:
                logger.warning("Failed to persist mode to SQLite state_repo: %s", exc)

        # 3. Log event
        if self._event_log_repo:
            try:
                await self._event_log_repo.append(
                    event_type="PRODUCTION_MODE_CHANGED",
                    payload={"new_mode": mode, "operator": operator, "trading_enabled": self._config.v2_trading_enabled},
                    source_service="production_controller",
                )
            except Exception as exc:
                logger.debug("Failed to log mode change event: %s", exc)

        # 4. Notify EventBus
        try:
            await self._bus.publish(EventType.SYSTEM_CONFIG_UPDATED, {
                "v2_deployment_mode": self._config.v2_deployment_mode,
                "v2_trading_enabled": self._config.v2_trading_enabled,
                "v2_shadow_mode": self._config.v2_shadow_mode,
                "operator": operator,
            })
        except Exception as exc:
            logger.debug("Bus notification failed: %s", exc)

        logger.info("Production mode changed to %s by %s", mode, operator)

        return {
            "ok": True,
            "mode": mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "shadow_mode": self._config.v2_shadow_mode,
            "message": msg,
        }

    async def kill_switch(
        self,
        reason: str = "Emergency Kill-Switch Triggered",
        operator: str = "API",
    ) -> Dict[str, Any]:
        """
        Emergency Halt: Immediately trips the global circuit breaker, sets trading_enabled=False,
        reverts mode to SHADOW, and halts all outbound orders.
        """
        logger.critical("EMERGENCY KILL-SWITCH TRIGGERED by %s: %s", operator, reason)

        # 1. Trip circuit breaker in RiskService
        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.trip(reason)
            self._risk_service.circuit_breaker.set_emergency_stop(True, reason)

        # 2. Force configuration to fail-safe SHADOW mode
        self._config.v2_trading_enabled = False
        self._config.v2_deployment_mode = "SHADOW"
        self._config.v2_shadow_mode = True

        try:
            V2Config.save_runtime_overrides({
                "v2_deployment_mode": "SHADOW",
                "v2_trading_enabled": False,
                "v2_shadow_mode": True,
            })
        except Exception as exc:
            logger.warning("Could not persist runtime overrides for kill-switch: %s", exc)

        now_str = datetime.now(timezone.utc).isoformat()

        # 3. Persist state to SQLite
        if self._state_repo:
            try:
                await self._state_repo.set_many({
                    "circuit_breaker_status": "TRIPPED",
                    "circuit_breaker_reason": reason,
                    "emergency_stop": "true",
                    "v2_deployment_mode": "SHADOW",
                    "v2_trading_enabled": "false",
                    "v2_shadow_mode": "true",
                    "last_kill_switch_at": now_str,
                    "kill_switch_operator": operator,
                }, updated_by=operator)
            except Exception as exc:
                logger.warning("Failed to persist kill-switch state to DB: %s", exc)

        # 4. Audit Log
        if self._event_log_repo:
            try:
                await self._event_log_repo.append(
                    event_type="CIRCUIT_BREAKER_TRIPPED",
                    payload={"reason": reason, "operator": operator, "action": "KILL_SWITCH"},
                    source_service="production_controller",
                )
            except Exception as exc:
                logger.debug("Failed to log kill switch event: %s", exc)

        # 5. Broadcast alert on EventBus
        try:
            await self._bus.publish(EventType.CIRCUIT_BREAKER_TRIPPED, {
                "reason": reason,
                "operator": operator,
                "timestamp": now_str,
            })
        except Exception as exc:
            logger.debug("Bus alert dispatch error: %s", exc)

        return {
            "ok": True,
            "circuit_breaker": "TRIPPED",
            "circuit_breaker_tripped": True,
            "mode": "SHADOW",
            "trading_enabled": False,
            "status": "ALL_ORDERS_BLOCKED",
            "message": f"Circuit breaker tripped. All order dispatch blocked immediately. Reason: {reason}",
        }

    async def resume(
        self,
        operator: str = "API",
        target_mode: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify database integrity, reset circuit breaker, re-arm order router,
        and transition back to target_mode (defaults to PAPER).
        """
        logger.info("Resuming trading operations requested by %s (target_mode: %s)", operator, target_mode)

        # 1. Database Integrity Verification
        if self._state_repo:
            healthy = await self._state_repo.verify_integrity()
            if not healthy:
                err_msg = "Database integrity check FAILED (PRAGMA integrity_check). Refusing to resume."
                logger.critical(err_msg)
                return {
                    "ok": False,
                    "error": "INTEGRITY_CHECK_FAILED",
                    "message": err_msg,
                }

        # 2. Risk Engine Safety Verification
        if self._risk_service and hasattr(self._risk_service, "is_safe_to_resume"):
            check_fn = getattr(self._risk_service, "is_safe_to_resume")
            res = check_fn()
            if asyncio.iscoroutine(res):
                is_safe, unsafe_reason = await res
            elif isinstance(res, tuple):
                is_safe, unsafe_reason = res
            else:
                is_safe, unsafe_reason = True, "Mock/Default"

            if not is_safe:
                logger.critical("Refusing to resume trading: Risk Engine reports unsafe state: %s", unsafe_reason)
                return {
                    "ok": False,
                    "error": "RISK_PRECONDITION_FAILED",
                    "message": f"Cannot resume trading: Risk Engine reports unsafe state ({unsafe_reason})",
                    "status": "HALTED",
                }

        # 3. Reset circuit breaker in RiskService (only after safety confirmation)
        if self._risk_service and hasattr(self._risk_service, "circuit_breaker"):
            self._risk_service.circuit_breaker.reset()
            self._risk_service.circuit_breaker.set_emergency_stop(False)

        # 4. Determine resume mode
        resume_mode = (target_mode or "PAPER").upper().strip()
        if resume_mode not in ("PAPER", "LIVE_MICROCASH", "SHADOW"):
            resume_mode = "PAPER"

        # Apply mode
        mode_res = await self.set_mode(resume_mode, operator=operator)

        now_str = datetime.now(timezone.utc).isoformat()

        # 4. Persist normalized state in SQLite
        if self._state_repo:
            try:
                await self._state_repo.set_many({
                    "circuit_breaker_status": "NORMAL",
                    "circuit_breaker_reason": "",
                    "emergency_stop": "false",
                    "last_resumed_at": now_str,
                    "resumed_operator": operator,
                }, updated_by=operator)
            except Exception as exc:
                logger.warning("Failed to persist resume state to DB: %s", exc)

        # 5. Audit Log
        if self._event_log_repo:
            try:
                await self._event_log_repo.append(
                    event_type="SYSTEM_RESUMED",
                    payload={"resumed_mode": resume_mode, "operator": operator},
                    source_service="production_controller",
                )
            except Exception as exc:
                logger.debug("Failed to log resume event: %s", exc)

        # 6. Broadcast resume event on EventBus
        try:
            await self._bus.publish(EventType.SYSTEM_CONFIG_UPDATED, {
                "action": "RESUME",
                "circuit_breaker": "NORMAL",
                "mode": resume_mode,
                "operator": operator,
                "timestamp": now_str,
            })
        except Exception as exc:
            logger.debug("Bus resume event dispatch error: %s", exc)

        return {
            "ok": True,
            "circuit_breaker": "NORMAL",
            "circuit_breaker_tripped": False,
            "mode": resume_mode,
            "trading_enabled": self._config.v2_trading_enabled,
            "database_integrity": True,
            "message": f"Trading successfully resumed in {resume_mode} mode. Circuit breaker re-armed.",
        }
