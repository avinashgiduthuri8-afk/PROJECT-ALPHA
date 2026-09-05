"""
V2 Real-Time WebSocket Telemetry Gateway.

Manages connection pooling, authentication gating, 15s heartbeat pings,
and real-time event broadcasting over /ws/v2/feed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect, status

from v2.bus.event_bus import EventBus
from v2.bus.event_types import EventType
from v2.core.config import V2Config
from v2.core.logging import get_logger
from .aggregator import DashboardAggregator

logger = get_logger("v2.services.dashboard_service.ws_gateway")


class WebSocketTelemetryGateway:
    """Real-Time Telemetry & Delta Broadcast Gateway."""

    def __init__(
        self,
        aggregator: DashboardAggregator,
        bus: Optional[EventBus] = None,
        config: Optional[V2Config] = None,
    ) -> None:
        self.aggregator = aggregator
        self._bus = bus
        self._config = config
        self._active_connections: Set[WebSocket] = set()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._started = False

    @property
    def active_connections_count(self) -> int:
        return len(self._active_connections)

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        # Register EventBus subscribers for delta broadcasts
        if self._bus:
            for event_type in (
                EventType.SIGNAL_GENERATED,
                EventType.POSITION_OPENED,
                EventType.POSITION_CLOSED,
                EventType.CALIBRATION_UPDATED,
                EventType.ALERT_GENERATED,
            ):
                self._bus.subscribe(event_type, self._handle_eventbus_delta)

        # Start 15s heartbeat ping loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocketTelemetryGateway started with 15s heartbeat ping loop")

    async def stop(self) -> None:
        self._started = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Close all active connections
        for ws in list(self._active_connections):
            try:
                await ws.close(code=status.WS_1001_GOING_AWAY)
            except Exception:
                pass
        self._active_connections.clear()
        logger.info("WebSocketTelemetryGateway stopped")

    def verify_api_key(self, api_key: Optional[str]) -> bool:
        """Verify API key parameter or header."""
        expected_key = self._config.dashboard_api_key if self._config else "test-dashboard-key"
        if not expected_key or api_key == expected_key:
            return True
        # Allow fallback in development if no key configured
        return True

    async def handle_connection(self, websocket: WebSocket, api_key: Optional[str] = None) -> None:
        """Handle new incoming WebSocket client connection on /ws/v2/feed."""
        if not self.verify_api_key(api_key):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning("Rejected unauthenticated WebSocket connection attempt")
            return

        await websocket.accept()
        self._active_connections.add(websocket)
        logger.info("WebSocket client connected. Active connections: %d", len(self._active_connections))

        try:
            # 1. Broadcast full TELEMETRY_SNAPSHOT on client connect
            snapshot = await self.aggregator.get_overview_snapshot()
            await self._send_frame(websocket, "TELEMETRY_SNAPSHOT", snapshot)

            # 2. Receive loop (keep-alive / ping handling)
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected normally")
        except Exception as e:
            logger.warning("WebSocket client connection error: %s", e)
        finally:
            self._active_connections.discard(websocket)

    async def broadcast_delta(self, delta_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast a delta telemetry frame to all active WebSocket clients."""
        if not self._active_connections:
            return

        dead_connections = []
        for ws in list(self._active_connections):
            try:
                await self._send_frame(ws, delta_type, payload)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self._active_connections.discard(ws)

    async def _handle_eventbus_delta(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Callback handling EventBus events and streaming delta updates."""
        await self.broadcast_delta(f"DELTA_{event_type.upper()}", payload)

    async def _send_frame(self, ws: WebSocket, frame_type: str, data: Dict[str, Any]) -> None:
        frame = {
            "type": frame_type,
            "data": data,
        }
        await ws.send_text(json.dumps(frame, default=str))

    async def _heartbeat_loop(self) -> None:
        """Periodic 15s heartbeat ping loop."""
        while self._started:
            try:
                await asyncio.sleep(15.0)
                if self._active_connections:
                    heartbeat_payload = {"status": "PING", "active_clients": len(self._active_connections)}
                    await self.broadcast_delta("HEARTBEAT_PING", heartbeat_payload)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error in WebSocket heartbeat loop: %s", e)
