"""
<<<<<<< Updated upstream
v2.services.production_service — 24/7 Watchdog Supervisor, Emergency Kill-Switch, and Fleet Controller.
"""

from .controller import ProductionController
from .watchdog import ProductionWatchdog

__all__ = [
    "ProductionController",
    "ProductionWatchdog",
]

=======
V2 Production Service Module Exports.
"""

from .controller import DeploymentMode, ProductionController
from .service import ProductionService
from .watchdog import ProductionWatchdog

__all__ = [
    "DeploymentMode",
    "ProductionController",
    "ProductionService",
    "ProductionWatchdog",
]
>>>>>>> Stashed changes
