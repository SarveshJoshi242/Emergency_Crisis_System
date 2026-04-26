# ============================================================
#  Emergency Backend · routers/staff.py
# ============================================================

import logging
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models.staff import StaffCreate
from services.staff_service import create_staff, list_staff
from auth.dependencies import require_staff  # JWT guard — staff only

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/staff", tags=["Staff"])


# ── Existing endpoints (unchanged) ────────────────────────────────────────────

@router.post("", summary="Register a staff member")
async def add_staff(
    body: StaffCreate,
    _auth: dict = Depends(require_staff),   # 🔒 staff only
):
    return await create_staff(name=body.name, role=body.role)


@router.get("", summary="List all staff")
async def get_staff(
    _auth: dict = Depends(require_staff),   # 🔒 staff only
):
    return await list_staff()


# ── New: room-level manual emergency trigger ──────────────────────────────────

class RoomEmergencyRequest(BaseModel):
    """
    Staff-initiated room-level emergency.
    severity = medium  → notify staff only (no evacuation)
    severity = high | critical → trigger full evacuation with room context
    """
    floor_id: str
    room_id: str
    severity: Literal["medium", "high", "critical"]
    message: Optional[str] = None


@router.post(
    "/emergency/trigger-room",
    status_code=200,
    summary="Staff-triggered room-level emergency",
    description="""
Allows staff to manually declare an emergency at room granularity.

- **medium**: Notifies staff dashboard with room context. No evacuation.
- **high / critical**: Triggers full evacuation pipeline including Gemini task
  generation and WebSocket broadcast to all clients with the source room included.

This endpoint is an extension of the existing manual alert system with room context.
""",
)
async def trigger_room_emergency(
    body: RoomEmergencyRequest,
    _auth: dict = Depends(require_staff),   # 🔒 staff only — most sensitive endpoint
):
    """
    Manual room-level emergency trigger for staff.

    Routes:
    - medium  → staff-only notification (alert + WebSocket, no tasks)
    - high / critical → full evacuation via existing fire_service pipeline
    """
    from services.alert_service import create_auto_alert
    from services.websocket_manager import manager
    from services.fire_service import handle_fire_input
    import time

    floor_id = body.floor_id
    room_id = body.room_id
    severity = body.severity

    location = f"Room {room_id} on Floor {floor_id}"
    avoidance = f"Guests must avoid {location} immediately."

    if body.message:
        base_message = body.message
    else:
        base_message = (
            f"Staff-triggered {severity.upper()} emergency in {location}. "
            f"{avoidance}"
        )

    logger.warning(
        f"Manual room emergency | floor={floor_id} room={room_id} "
        f"severity={severity}"
    )

    if severity == "medium":
        # Notify staff — no evacuation
        fire_event_id = f"manual_medium_{floor_id}_{room_id}_{int(time.time())}"
        alert = await create_auto_alert(
            floor_id=floor_id,
            fire_event_id=fire_event_id,
            risk_level="MEDIUM",
            message=base_message,
            source_room=room_id,
            scope="floor",
        )
        if not alert:
            raise HTTPException(
                status_code=409,
                detail="A medium alert for this room is already active.",
            )
        ws_payload = {
            **alert,
            "type":        "ai_medium_alert",
            "floor_id":    floor_id,
            "source_room": room_id,
            "severity":    "medium",
            "message":     base_message,
        }
        await manager.broadcast("ai_medium_alert", ws_payload)
        return {
            "status":      "notified",
            "floor_id":    floor_id,
            "source_room": room_id,
            "severity":    "medium",
            "alert_id":    alert["id"],
            "message":     base_message,
        }

    else:
        # high / critical → full evacuation pipeline
        synthetic_payload = {
            "floor_id":         floor_id,
            "risk_level":       severity.upper(),
            "risk_score":       0.95 if severity == "critical" else 0.85,
            "action":           "EVACUATE",
            "density_label":    "HIGH",
            "density_value":    0.9,
            "people_count":     0,
            "fire_conf":        0.9,
            "movement_score":   0.7,
            "source_room":      room_id,
            "scope":            "floor",
            "override_message": base_message,
        }
        result = await handle_fire_input(synthetic_payload)
        return {
            "status":        "evacuation_triggered",
            "floor_id":      floor_id,
            "source_room":   room_id,
            "severity":      severity,
            "alert_created": result.get("alert_created", False),
            "message":       base_message,
        }

