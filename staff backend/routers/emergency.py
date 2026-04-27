from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.websocket_manager import manager
from services.fire_service import handle_fire_input
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency", tags=["Emergency"])


class EmergencyStart(BaseModel):
    room_id: str
    floor: str
    type: str = "fire"


@router.post("/start", summary="Manually start emergency evacuation")
async def start_emergency(body: EmergencyStart):
    """
    Manually trigger a full emergency for a specific room and floor.
    Goes through the same pipeline as YOLO fire detection:
      - Creates DB alert (deduplication-aware)
      - Syncs emergency_state (guest backend reads this)
      - Generates Gemini AI tasks
      - Broadcasts via WebSocket to all clients
      - Sends SMS to all active guests with phone numbers
    """
    logger.warning(
        "🚨 MANUAL EMERGENCY TRIGGERED | room=%s floor=%s type=%s",
        body.room_id, body.floor, body.type
    )

    # Build a fire_event payload that matches what the YOLO pipeline sends
    payload = {
        "floor_id":       body.floor,
        "risk_level":     "HIGH",
        "risk_score":     0.95,
        "action":         "EVACUATE",
        "density_label":  "high",
        "density_value":  0.9,
        "people_count":   10,
        "fire_conf":      0.95,
        "movement_score": 0.8,
        "source_room":    body.room_id,
        "scope":          "room",
        "danger_zones":   [body.room_id],
        "override_message": (
            f"MANUAL ALERT: {body.type.upper()} emergency declared in "
            f"Room {body.room_id} on Floor {body.floor}. "
            "Immediate evacuation required."
        ),
    }

    try:
        result = await handle_fire_input(payload)
    except Exception as e:
        logger.error("Manual emergency pipeline failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Emergency pipeline error: {e}")

    return {
        "status": "EVACUATION ACTIVE",
        "room_id": body.room_id,
        "floor": body.floor,
        "alert_created": result.get("alert_created", False),
        "fire_event_id": result.get("id"),
    }


@router.post("/notify-responders", summary="Trigger responders (n8n ready)")
async def notify_responders(body: dict):
    logger.info("Responders notified: %s", body)
    return {"status": "Responders notified"}
