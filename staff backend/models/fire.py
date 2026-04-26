# ============================================================
#  Emergency Backend · models/fire.py
#  Mirrors InfernoGuard PredictResponse schema exactly
# ============================================================

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class FireInput(BaseModel):
    """
    Mirrors fire_risk/api.py PredictRequest + PredictResponse.
    The frontend (or InfernoGuard itself) posts this payload.
    """
    floor_id: str

    # InfernoGuard output fields
    people_count: int = Field(..., ge=0)
    fire_conf: float = Field(..., ge=0.0, le=1.0)
    movement_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str        # LOW | MEDIUM | HIGH | CRITICAL
    risk_score: float
    action: str            # MONITOR | NOTIFY_STAFF | ALERT | EVACUATE
    density_label: str     # LOW | MEDIUM | HIGH
    density_value: float

    @field_validator("fire_conf", "movement_score", mode="before")
    @classmethod
    def _round(cls, v):
        return round(float(v), 4)


class FireEventResponse(BaseModel):
    id: str
    floor_id: str
    risk_level: str
    risk_score: float
    action: str
    density_label: str
    density_value: float
    people_count: int
    fire_conf: float
    movement_score: float
    alert_created: bool
    timestamp: str
