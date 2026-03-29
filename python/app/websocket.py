"""
WebSocket manager for real-time fleet updates.

Broadcasts these event types:
  - robot_position
  - robot_state_change
  - task_update
  - collision_alert
  - iogita_zone_update
  - deadlock_event
  - fleet_metrics
  - wcs_event
  - sg_prediction

Usage:
  ws_manager = ConnectionManager()
  await ws_manager.broadcast({"type": "robot_position", "data": {...}})
"""

import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


MAX_WS_CONNECTIONS = 100  # Prevent DoS via connection flooding


class ConnectionManager:
    """Manages WebSocket connections for /ws/fleet."""

    def __init__(self, max_connections: int = MAX_WS_CONNECTIONS):
        self.active_connections: list[WebSocket] = []
        self._message_count: int = 0
        self._max_connections = max_connections

    async def connect(self, websocket: WebSocket) -> bool:
        """Accept a new WebSocket connection. Returns False if limit reached."""
        if len(self.active_connections) >= self._max_connections:
            await websocket.close(code=1013, reason="Max connections reached")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]):
        """Broadcast a message to all connected clients."""
        self._message_count += 1
        message["_seq"] = self._message_count
        message["_ts"] = time.time()

        payload = json.dumps(message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]):
        """Send a message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    @property
    def message_count(self) -> int:
        return self._message_count


# Global instance — used by routes and background tasks
ws_manager = ConnectionManager()


def _check_ws_origin(websocket: WebSocket) -> bool:
    """Validate WebSocket origin against CORS_ORIGINS config."""
    from app.config import get_settings
    settings = get_settings()
    if settings.cors_origins == "*":
        return True
    allowed = {o.strip() for o in settings.cors_origins.split(",")}
    origin = websocket.headers.get("origin", "")
    return origin in allowed or not origin  # no origin = same-origin


@router.websocket("/ws/fleet")
async def websocket_fleet(websocket: WebSocket):
    """
    WebSocket endpoint for real-time fleet updates.
    Clients connect here to receive streaming updates.
    """
    if not _check_ws_origin(websocket):
        await websocket.close(code=4003, reason="Origin not allowed")
        return
    connected = await ws_manager.connect(websocket)
    if not connected:
        return
    try:
        # Send initial connection confirmation
        await ws_manager.send_personal(websocket, {
            "type": "connected",
            "message": "Connected to fleet WebSocket",
            "active_connections": ws_manager.connection_count,
        })

        # Keep connection alive, process any incoming messages
        while True:
            data = await websocket.receive_text()
            # Clients can send subscription filters or heartbeats
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_personal(websocket, {"type": "pong", "ts": time.time()})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
