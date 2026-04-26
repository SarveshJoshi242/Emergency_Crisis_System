# ============================================================
#  Emergency Backend · routers/websocket.py
#  Purpose: Single /ws/live endpoint — all clients, one channel
# ============================================================

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.websocket_manager import manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    Connect to receive real-time events.

    Message format:
        { "type": "alert" | "task", "data": { ... } }
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; we only push from server side
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
