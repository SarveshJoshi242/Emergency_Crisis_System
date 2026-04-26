# ============================================================
#  Emergency Backend · models/webhook.py
#  Purpose: AI danger detection webhook payload schema
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional, Literal


class AIDangerEvent(BaseModel):
    """
    Payload sent by the external AI model (e.g. InfernoGuard / camera system).

    - floor_id   : required — which floor the camera covers
    - room_id    : optional — if the AI can pinpoint a specific room
    - danger_level: low | medium | high | critical
    - timestamp  : ISO 8601 string from the AI model

    Backward compatible: existing payloads without room_id work unchanged.
    """
    timestamp: str = Field(..., description="ISO 8601 timestamp from the AI system")
    floor_id: str = Field(..., description="Floor identifier (e.g. 'floor_1', 'ground')")
    room_id: Optional[str] = Field(
        None,
        description="Optional room identifier for localized detection (e.g. 'room_101')",
    )
    danger_level: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="AI-assessed danger level"
    )


class AIDangerResponse(BaseModel):
    """Acknowledgement returned immediately to the AI model (no blocking)."""
    status: str = "accepted"
    floor_id: str
    room_id: Optional[str] = None
    danger_level: str
    message: str
