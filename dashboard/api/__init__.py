"""
PROJECT-ALPHA — Dashboard API Layer.
"""

from .router import router
from .dashboard_routes import router as dashboard_router
from .production_routes import router as production_router
from .research_routes import research_router

__all__ = ["router", "dashboard_router", "production_router", "research_router"]
