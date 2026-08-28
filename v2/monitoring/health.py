"""
V2 HealthChecker — aggregate liveness, readiness, and subsystem diagnostic probes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


class HealthChecker:
    """Probes status across all active V2 subsystems and evaluates platform health."""

    def __init__(
        self,
        db: Optional[Any] = None,
        scanner_service: Optional[Any] = None,
        ai_service: Optional[Any] = None,
        risk_service: Optional[Any] = None,
        portfolio_service: Optional[Any] = None,
        trading_service: Optional[Any] = None,
        shadow_service: Optional[Any] = None,
        notification_service: Optional[Any] = None,
        scheduler: Optional[Any] = None,
    ) -> None:
        self._db = db
        self._scanner_service = scanner_service
        self._ai_service = ai_service
        self._risk_service = risk_service
        self._portfolio_service = portfolio_service
        self._trading_service = trading_service
        self._shadow_service = shadow_service
        self._notification_service = notification_service
        self._scheduler = scheduler

    def check_health(self) -> dict[str, Any]:
        """Query all registered subsystems and determine aggregate health status."""
        services: dict[str, dict[str, Any]] = {}

        # 1. Database
        db_healthy = self._db is not None and self._db.is_open
        services["database"] = {"healthy": db_healthy}

        # 2. Scanner
        if self._scanner_service:
            services["scanner"] = self._scanner_service.get_health()
        else:
            services["scanner"] = {"healthy": True, "registered": False}

        # 3. AI Intelligence
        if self._ai_service:
            services["ai"] = self._ai_service.get_health()
        else:
            services["ai"] = {"healthy": True, "registered": False}

        # 4. Risk Engine
        if self._risk_service:
            services["risk"] = self._risk_service.get_health()
        else:
            services["risk"] = {"healthy": True, "registered": False}

        # 5. Portfolio
        if self._portfolio_service:
            services["portfolio"] = self._portfolio_service.get_health()
        else:
            services["portfolio"] = {"healthy": True, "registered": False}

        # 6. Trading
        if self._trading_service:
            services["trading"] = self._trading_service.get_health()
        else:
            services["trading"] = {"healthy": True, "registered": False}

        # 7. Shadow Engine
        if self._shadow_service:
            services["shadow"] = self._shadow_service.get_health()
        else:
            services["shadow"] = {"healthy": True, "registered": False}

        # 8. Notification
        if self._notification_service:
            services["notification"] = self._notification_service.get_health()
        else:
            services["notification"] = {"healthy": True, "registered": False}

        # 9. Scheduler
        if self._scheduler:
            services["scheduler"] = self._scheduler.get_health()
        else:
            services["scheduler"] = {"healthy": True, "registered": False}

        unhealthy = [
            k for k, v in services.items()
            if v.get("registered", True) is not False and not v.get("healthy", False)
        ]

        if not unhealthy:
            overall_status = "healthy"
        elif len(unhealthy) <= 2 and "database" not in unhealthy:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return {
            "status": overall_status,
            "unhealthy_services": unhealthy,
            "services": services,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
