# ============================================================
#  Emergency Backend · services/websocket_manager.py
#  Purpose: Single-channel WebSocket connection manager
# ============================================================

import json
import logging
from datetime import datetime, date
from typing import Any, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _serialize_payload(value: Any) -> Any:
    """JSON serialization default handler for non-standard types."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    # bson ObjectId and other objects with __str__
    return str(value)


class ConnectionManager:
    """
    One broadcast list — no channels.
    Send { "type": "alert"|"task", "data": {} } to all connected clients.
    """

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast a typed message to every connected client."""
        payload = json.dumps(
            {"type": event_type, "data": data},
            default=_serialize_payload,
        )
        dead: List[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# Singleton used across routers and services
manager = ConnectionManager()
