"""
V2 Production Service Facade.

Coordinates ProductionController, ProductionWatchdog, ShadowDivergenceTracker,
and ProductionRepository into a unified production management layer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from v2.bus.event_bus import EventBus
from v2.core.logging import get_logger
from v2.repository.production_repo import ProductionRepository
from v2.services.shadow_service.tracker import ShadowDivergenceTracker
from .controller import DeploymentMode, ProductionController
from .watchdog import ProductionWatchdog

logger = get_logger("v2.services.production_service")


class ProductionService:
    """Production Deployment & Watchdog Supervisor Service."""

    def __init__(
        self,
        production_repo: ProductionRepository,
        bus: Optional[EventBus] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.repo = production_repo
        self._bus = bus
        self.controller = ProductionController(production_repo=production_repo, bus=bus)
        self.tracker = ShadowDivergenceTracker(production_repo=production_repo, bus=bus)
        self.watchdog = ProductionWatchdog(services=services, bus=bus)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self.controller.initialize_state()
        await self.watchdog.start()
        logger.info("ProductionService started with mode: %s", self.controller.mode.value)

    async def stop(self) -> None:
        self._started = False
        await self.watchdog.stop()
        logger.info("ProductionService stopped")

    async def get_status(self) -> Dict[str, Any]:
        """Return unified production status snapshot."""
        health = await self.watchdog.inspect_system_health()
        return {
            "deployment_mode": self.controller.mode.value,
            "is_kill_switch_tripped": self.controller.is_kill_switch_tripped,
            "system_health": health,
            "wallet_limits_inr": {
                "STE": 35000.0,
                "HDA": 30000.0,
                "VCP": 15000.0,
                "BBS": 20000.0,
            },
            "micro_order_caps_inr": {
                "STE": 500.0,
                "HDA": 600.0,
                "VCP": 400.0,
                "BBS": 400.0,
            },
            "minimum_notional_inr": 100.0,
        }
