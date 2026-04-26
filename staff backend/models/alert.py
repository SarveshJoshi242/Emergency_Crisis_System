# ============================================================
#  Emergency Backend · models/alert.py
# ============================================================

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class AlertCreate(BaseModel):
    floor_id: str
    type: Literal["AUTO", "MANUAL"] = "MANUAL"
    message: Optional[str] = None
    risk_level: Optional[str] = None
    # Room-level fields (optional — backward compatible)
    source_room: Optional[str] = None
    danger_zones: List[str] = Field(default_factory=list)
    scope: Literal["floor", "room"] = "floor"


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

