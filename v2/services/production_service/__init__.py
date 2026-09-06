"""
v2.services.production_service — 24/7 Watchdog Supervisor, Emergency Kill-Switch, and Fleet Controller.
"""

from .controller import ProductionController
from .watchdog import ProductionWatchdog

__all__ = [
    "ProductionController",
    "ProductionWatchdog",
]

