"""
V2 WebSocket API Endpoint.

Mounted at /ws/v2/feed — provides continuous real-time event streaming for connected dashboards.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from v2.core.config import get_config
from v2.core.logging import get_logger
from v2.services.dashboard_service.websocket import WebSocketManager

logger = get_logger("v2.api.websocket")

router = APIRouter()
_ws_manager: Optional[WebSocketManager] = None


def init_websocket(ws_manager: WebSocketManager) -> None:
    """Inject the WebSocket manager instance from application lifespan."""
    global _ws_manager
    _ws_manager = ws_manager


@router.websocket("/ws/v2/feed")
async def websocket_feed(
    websocket: WebSocket,
    api_key: Optional[str] = Query(default=None, alias="api_key"),
) -> None:
    """
    Real-time push feed for V2 events.

    Authentication:
        Pass API key as query parameter `?api_key=...` or header `X-API-Key`.
    """
    cfg = get_config()
    expected_key = cfg.dashboard_api_key

    # Extract API key from query parameter or headers
    provided_key = api_key or websocket.headers.get("X-API-Key")

    if not expected_key:
        logger.warning("WebSocket rejected: DASHBOARD_API_KEY is not configured on server")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        logger.warning("WebSocket rejected: Invalid API key")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if _ws_manager is None:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await _ws_manager.connect(websocket)

    try:
        while True:
            # Keep connection alive, listen for client pings or heartbeats
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WebSocket client connection error", extra={"error": str(exc)})
        _ws_manager.disconnect(websocket)
