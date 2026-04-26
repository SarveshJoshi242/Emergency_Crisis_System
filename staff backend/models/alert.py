# ============================================================
#  Emergency Backend · models/alert.py
# ============================================================

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class AlertCreate(BaseModel):
    type: Literal["fire", "help"]
    room_id: str
    floor: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    confidence: float
    source: str


class AlertResponse(BaseModel):
    id: str
    floor_id: str
    type: str
    status: str          # ACTIVE | RESOLVED
    message: Optional[str] = None
    risk_level: Optional[str] = None
    fire_event_id: Optional[str] = None
    source_room: Optional[str] = None   # first zone (backward compat)
    danger_zones: List[str] = Field(default_factory=list)  # all active zones
    scope: str = "floor"
    created_at: str


class AlertResolve(BaseModel):
    alert_id: str

