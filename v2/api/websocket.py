"""
V2 WebSocket API Endpoint.

Mounted at /ws/v2/feed — provides continuous real-time event streaming for connected dashboards.
"""

from __future__ import annotations

import hmac
import json
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from v2.core.config import get_config
from v2.core.logging import get_logger
from v2.services.dashboard_service.websocket import WebSocketManager

logger = get_logger("v2.api.websocket")

router = APIRouter()
_ws_manager: Optional[WebSocketManager] = None
_dashboard_service: Optional[Any] = None


def init_websocket(
    ws_manager: WebSocketManager,
    dashboard_service: Optional[Any] = None,
) -> None:
    """Inject the WebSocket manager and DashboardService instance from application lifespan."""
    global _ws_manager, _dashboard_service
    _ws_manager = ws_manager
    _dashboard_service = dashboard_service


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

    # In dev mode with default alpha-dev-key, permit connection even if api_key query param was omitted
    is_authorized = (
        (expected_key == "alpha-dev-key" and (not provided_key or provided_key == "alpha-dev-key"))
        or (provided_key and hmac.compare_digest(provided_key, expected_key))
    )

    if not is_authorized:
        logger.warning("WebSocket rejected: Invalid API key")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if _ws_manager is None:
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await _ws_manager.connect(websocket)

    # Immediately push telemetry snapshot upon connection
    if _dashboard_service is not None:
        try:
            snap = _dashboard_service.get_telemetry_snapshot()
            await websocket.send_text(json.dumps({"type": "TELEMETRY_SNAPSHOT", "data": snap}, default=str))
        except Exception as exc:
            logger.debug("Failed sending initial telemetry snapshot: %s", exc)

    try:
        while True:
            # Keep connection alive, listen for client pings or heartbeats
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
            elif data in ("close", "exit"):
                break
    except (WebSocketDisconnect, RuntimeError):
        _ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WebSocket client connection error", extra={"error": str(exc)})
        _ws_manager.disconnect(websocket)
    finally:
        _ws_manager.disconnect(websocket)
