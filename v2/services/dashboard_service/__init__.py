"""
V2 Dashboard Service Package.
"""

from .service import DashboardService
from .websocket import WebSocketManager

__all__ = ["DashboardService", "WebSocketManager"]
