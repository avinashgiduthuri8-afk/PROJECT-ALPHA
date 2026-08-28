"""
V2 WebSocket Manager — manages live client subscriptions and real-time event broadcasting.
"""

from __future__ import annotations

import json
from typing import Any, Set

from fastapi import WebSocket

from v2.core.logging import get_logger

logger = get_logger("v2.services.dashboard_service.websocket")


class WebSocketManager:
    """Tracks active frontend WebSocket client connections and broadcasts live event frames."""

    def __init__(self) -> None:
        self._active_connections: Set[WebSocket] = set()

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active_connections.add(websocket)
        logger.info("WebSocket client connected", extra={"active_connections": len(self._active_connections)})

    def disconnect(self, websocket: WebSocket) -> None:
        self._active_connections.discard(websocket)
        logger.info("WebSocket client disconnected", extra={"active_connections": len(self._active_connections)})

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        """Broadcast JSON message to all connected clients."""
        if not self._active_connections:
            return

        frame = {
            "type": event_type,
            "data": payload,
        }
        text = json.dumps(frame, default=str)

        dead_connections = []
        for ws in list(self._active_connections):
            try:
                await ws.send_text(text)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self._active_connections.discard(ws)
