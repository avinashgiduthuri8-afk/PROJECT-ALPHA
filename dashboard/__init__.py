"""
PROJECT-ALPHA — Dashboard Module.

Provides web UI templates, static assets, dashboard API routing,
WebSocket state broadcasts, and telemetry aggregation.
"""

from .aggregator import DashboardAggregator
from .bot_pipeline import BotPipelineTracker
from .pipeline import PipelineStageCollector
from .service import DashboardService
from .websocket import WebSocketManager
from .ws_gateway import WebSocketTelemetryGateway

__all__ = [
    "BotPipelineTracker",
    "DashboardAggregator",
    "DashboardService",
    "PipelineStageCollector",
    "WebSocketManager",
    "WebSocketTelemetryGateway",
]
