"""
PROJECT-ALPHA — Dashboard API Layer.
"""

from .dashboard_routes import router as dashboard_router
from .production_routes import router as production_router
from .research_routes import research_router
from .router import router

__all__ = ["dashboard_router", "production_router", "research_router", "router"]
