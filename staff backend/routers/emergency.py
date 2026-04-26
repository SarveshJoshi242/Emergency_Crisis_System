from fastapi import APIRouter
from pydantic import BaseModel
from services.websocket_manager import manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency", tags=["Emergency"])

class EmergencyStart(BaseModel):
    room_id: str
    floor: str
    type: str

class NotifyResponders(BaseModel):
    type: str
    location: str
    severity: str

@router.post("/start", summary="Start emergency evacuation")
async def start_emergency(body: EmergencyStart):
    # 1. Update system state
    # (In a real system, this updates DB state. We simulate by broadcasting)
    logger.info(f"🚨 EMERGENCY STARTED: {body.type.upper()} in Room {body.room_id}")

    # 2. Trigger Responders
    notify_payload = {
        "type": body.type,
        "location": f"Room {body.room_id}, Floor {body.floor}",
        "severity": "medium"
    }
    # Here we would actually call the endpoint, but we can just call the logic
    await notify_responders(NotifyResponders(**notify_payload))

    # 3. Broadcast to guests
    await manager.broadcast("evacuation_started", {
        "room_id": body.room_id,
        "floor": body.floor,
        "type": body.type
    })
    
    # 4. Generate Staff Tasks
    # We broadcast tasks to staff UI
    tasks = [
        f"Go to Room {body.room_id} and check the situation",
        "Guide guests towards nearest exit",
        "Ensure corridors are clear",
        "Assist anyone needing help"
    ]
    await manager.broadcast("task_assigned", {"tasks": tasks})

    return {"status": "EVACUATION ACTIVE"}

@router.post("/notify-responders", summary="Trigger responders (n8n ready)")
async def notify_responders(body: NotifyResponders):
    # Just log for now. n8n webhook can be plugged here later.
    logger.info(f"🚨 Responders notified: {body.type.upper()} at {body.location} (Severity: {body.severity})")
    return {"status": "Responders notified"}
