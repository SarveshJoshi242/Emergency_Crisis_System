# ============================================================
#  Emergency Backend · routers/webhook.py
#  Purpose: AI model → backend integration webhook
# ============================================================

import logging
from fastapi import APIRouter, BackgroundTasks
from models.webhook import AIDangerEvent, AIDangerResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post(
    "/ai-danger-detection",
    status_code=202,
    response_model=AIDangerResponse,
    summary="Receive AI danger detection event",
    description="""
Called by the AI model (e.g. InfernoGuard / camera system) when danger is detected.

**Returns immediately** with `202 Accepted` — processing happens asynchronously
in a background task so the AI model is never blocked.

**Time-window logic** (5-second sustained rule):
- Single events are silently ignored (noise filter)
- `medium` sustained ≥ 5s → staff notification only
- `high` or `critical` sustained ≥ 5s → automatic evacuation triggered

**Room-level support**:
- Include `room_id` for localized danger tracking
- Omit `room_id` for floor-level detection (backward compatible)
""",
)
async def ai_danger_detection(
    payload: AIDangerEvent,
    background_tasks: BackgroundTasks,
) -> AIDangerResponse:
    """
    Non-blocking AI webhook endpoint.

    The danger processing is offloaded to a FastAPI BackgroundTask so this
    endpoint always responds in < 5ms regardless of DB or downstream latency.
    The AI model should call this at regular intervals (e.g. every 1–2 seconds).
    """
    from services.danger_tracker import process_danger_event  # local import avoids circular

    background_tasks.add_task(
        process_danger_event,
        floor_id=payload.floor_id,
        danger_level=payload.danger_level,
        timestamp=payload.timestamp,
        room_id=payload.room_id,
    )

    scope = "room" if payload.room_id else "floor"
    logger.info(
        f"Webhook received | floor={payload.floor_id} "
        f"room={payload.room_id or 'N/A'} level={payload.danger_level} "
        f"scope={scope} → queued for processing"
    )

    return AIDangerResponse(
        status="accepted",
        floor_id=payload.floor_id,
        room_id=payload.room_id,
        danger_level=payload.danger_level,
        message=(
            f"Event queued. "
            f"{'Room' if payload.room_id else 'Floor'}-level tracking active. "
            f"Action triggers after {5}s sustained detection."
        ),
    )
