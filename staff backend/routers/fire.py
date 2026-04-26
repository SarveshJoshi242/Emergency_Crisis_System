# ============================================================
#  Emergency Backend · routers/fire.py
# ============================================================

from fastapi import APIRouter
from models.fire import FireInput, FireEventResponse
from services.fire_service import handle_fire_input

router = APIRouter(prefix="/fire", tags=["Fire"])


@router.post("/input", summary="Receive InfernoGuard fire event")
async def fire_input(payload: FireInput):
    """
    Accepts the InfernoGuard PredictResponse payload (plus floor_id).
    - Stores the fire event
    - AUTO-creates an alert if risk is HIGH or CRITICAL
    - Generates tasks and broadcasts via WebSocket
    """
    result = await handle_fire_input(payload.model_dump())
    return result
