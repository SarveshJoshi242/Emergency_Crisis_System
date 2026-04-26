# ============================================================
#  Emergency Backend · models/yolo_alert.py
#  Purpose: Pydantic models for YOLO-based fire detection alerts.
#           Used by the YOLO Room Service → Backend API pipeline.
# ============================================================

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Request payloads ──────────────────────────────────────────────────────────

class FireDetectionPayload(BaseModel):
    """
    POST /alerts/fire-detection — medium risk, requires staff review.

    Sent by the YOLO Room Service when the sliding window buffer
    confirms ≥70% MEDIUM frames over a 5-second window.
    """
    room_id: str = Field(..., min_length=1, description="Node ID of the room")
    risk: Literal["medium"] = Field(
        ..., description="Risk level — must be 'medium' for this endpoint"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Average confidence from the sliding window (0–1)",
    )
    source: str = Field(
        "yolo", description="Detection source identifier"
    )
    floor_id: Optional[str] = Field(
        None,
        description="Floor ID — auto-resolved from room→floor mapping if absent",
    )


class AutoTriggerPayload(BaseModel):
    """
    POST /emergency/auto-trigger — high/critical, automatic evacuation.

    Sent by the YOLO Room Service when the sliding window buffer
    confirms ≥70% HIGH or CRITICAL frames over a 5-second window.
    """
    room_id: str = Field(..., min_length=1, description="Node ID of the room")
    risk: Literal["high", "critical"] = Field(
        ..., description="Risk level — 'high' or 'critical'"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Average confidence from the sliding window (0–1)",
    )
    triggered_by: str = Field(
        "model", description="Who/what triggered this — typically 'model'"
    )
    floor_id: Optional[str] = Field(
        None,
        description="Floor ID — auto-resolved from room→floor mapping if absent",
    )


# ── Response schemas ──────────────────────────────────────────────────────────

class AIFireAlertResponse(BaseModel):
    """Response for a stored AI fire alert."""
    id: str
    room_id: str
    floor_id: str
    risk: str
    confidence: float
    source: str
    state: Literal["pending", "confirmed", "dismissed"]
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
