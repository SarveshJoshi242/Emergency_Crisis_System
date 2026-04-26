# ============================================================
#  fire_risk/api.py
#  Purpose: Fire risk assessment relay API (port 8002)
#
#  Accepts fire sensor events, scores them, and optionally
#  forwards HIGH/CRITICAL events to the staff backend webhook.
#
#  Port: 8002
#  Start: uvicorn api:app --host 0.0.0.0 --port 8002 --reload
# ============================================================

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Literal
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STAFF_BACKEND_URL = os.getenv("STAFF_BACKEND_URL", "http://localhost:8001")

# In-memory store of last N assessments (no DB needed for relay service)
_assessments: List[dict] = []
_last_status: dict = {"risk_level": "SAFE", "updated_at": None, "total_events": 0}


# ── Risk scoring ──────────────────────────────────────────────────────────────

def compute_risk(
    temperature: Optional[float],
    smoke_density: Optional[float],
    co_level: Optional[float],
    flame_detected: bool,
) -> dict:
    """
    Simple rule-based risk scorer.
    Returns { risk_level, risk_score, triggers }
    """
    score = 0.0
    triggers = []

    if flame_detected:
        score += 60
        triggers.append("flame_detected")

    if temperature is not None:
        if temperature > 80:
            score += 30; triggers.append(f"temp_critical:{temperature}°C")
        elif temperature > 55:
            score += 15; triggers.append(f"temp_high:{temperature}°C")
        elif temperature > 40:
            score += 5;  triggers.append(f"temp_elevated:{temperature}°C")

    if smoke_density is not None:
        if smoke_density > 0.8:
            score += 25; triggers.append(f"smoke_critical:{smoke_density}")
        elif smoke_density > 0.4:
            score += 12; triggers.append(f"smoke_elevated:{smoke_density}")

    if co_level is not None:
        if co_level > 150:
            score += 20; triggers.append(f"co_critical:{co_level}ppm")
        elif co_level > 70:
            score += 8;  triggers.append(f"co_elevated:{co_level}ppm")

    score = min(score, 100.0)

    if score >= 80 or flame_detected:
        level = "CRITICAL"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    elif score >= 10:
        level = "LOW"
    else:
        level = "SAFE"

    return {"risk_level": level, "risk_score": round(score, 1), "triggers": triggers}


# ── Models ────────────────────────────────────────────────────────────────────

class SensorEvent(BaseModel):
    room_id: str
    floor_id: Optional[str] = None
    temperature: Optional[float] = None       # °C
    smoke_density: Optional[float] = None     # 0.0–1.0
    co_level: Optional[float] = None          # ppm
    flame_detected: bool = False
    source: Optional[str] = "sensor"          # "sensor" | "camera" | "manual"


class AssessmentResponse(BaseModel):
    room_id: str
    floor_id: Optional[str]
    risk_level: Literal["SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    risk_score: float
    triggers: List[str]
    timestamp: str
    forwarded_to_staff: bool


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 Fire Risk API starting on port 8002")
    yield
    logger.info("🛑 Fire Risk API shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="🔥 Fire Risk Assessment API",
    description=(
        "Receives fire sensor events, computes risk levels, and relays "
        "HIGH/CRITICAL alerts to the staff backend webhook."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Forward to staff backend ──────────────────────────────────────────────────

async def forward_to_staff(event: SensorEvent, risk: dict):
    """POST to staff backend /webhook/ai-danger-detection (non-fatal)."""
    payload = {
        "floor_id":   event.floor_id or event.room_id,
        "room_id":    event.room_id,
        "risk_level": risk["risk_level"],
        "risk_score": risk["risk_score"],
        "triggers":   risk["triggers"],
        "source":     event.source,
        "raw": {
            "temperature":   event.temperature,
            "smoke_density": event.smoke_density,
            "co_level":      event.co_level,
            "flame_detected":event.flame_detected,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{STAFF_BACKEND_URL}/webhook/ai-danger-detection",
                json=payload,
            )
            logger.info(
                "Forwarded to staff backend | room=%s level=%s status=%d",
                event.room_id, risk["risk_level"], resp.status_code,
            )
    except Exception as e:
        logger.warning("Could not forward to staff backend: %s", e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health():
    return {
        "status":     "ok",
        "service":    "Fire Risk Assessment API",
        "version":    "1.0.0",
        "staff_url":  STAFF_BACKEND_URL,
        "last_status": _last_status,
    }


@app.post("/fire-risk/assess", response_model=AssessmentResponse, tags=["Assessment"])
async def assess_risk(event: SensorEvent, background_tasks: BackgroundTasks):
    """
    Score a fire sensor event and return the risk level.

    - SAFE / LOW  : logged only
    - MEDIUM      : logged + stored
    - HIGH / CRITICAL : logged + stored + forwarded to staff backend webhook
    """
    risk = compute_risk(
        temperature=event.temperature,
        smoke_density=event.smoke_density,
        co_level=event.co_level,
        flame_detected=event.flame_detected,
    )

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "room_id":   event.room_id,
        "floor_id":  event.floor_id,
        "risk_level": risk["risk_level"],
        "risk_score": risk["risk_score"],
        "triggers":  risk["triggers"],
        "timestamp": now,
        "source":    event.source,
    }
    _assessments.insert(0, record)
    if len(_assessments) > 200:
        _assessments.pop()

    # Update global status
    _last_status.update({
        "risk_level": risk["risk_level"],
        "updated_at": now,
        "total_events": _last_status["total_events"] + 1,
    })

    forwarded = False
    if risk["risk_level"] in ("HIGH", "CRITICAL"):
        background_tasks.add_task(forward_to_staff, event, risk)
        forwarded = True
        logger.warning(
            "🔥 HIGH RISK DETECTED | room=%s level=%s score=%.1f triggers=%s",
            event.room_id, risk["risk_level"], risk["risk_score"], risk["triggers"],
        )
    else:
        logger.info(
            "Assessment | room=%s level=%s score=%.1f",
            event.room_id, risk["risk_level"], risk["risk_score"],
        )

    return AssessmentResponse(
        room_id=event.room_id,
        floor_id=event.floor_id,
        risk_level=risk["risk_level"],
        risk_score=risk["risk_score"],
        triggers=risk["triggers"],
        timestamp=now,
        forwarded_to_staff=forwarded,
    )


@app.post("/fire-risk/webhook", tags=["Relay"])
async def relay_webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    Pass-through relay — accepts any JSON payload and forwards directly
    to the staff backend /webhook/ai-danger-detection.

    Use this when the sensor already formats InfernoGuard-style events.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{STAFF_BACKEND_URL}/webhook/ai-danger-detection",
                json=payload,
            )
        return {"relayed": True, "staff_status": resp.status_code}
    except Exception as e:
        logger.warning("Relay failed: %s", e)
        return {"relayed": False, "error": str(e)}


@app.get("/fire-risk/status", tags=["Assessment"])
def get_status():
    """Current risk status and last 20 assessments."""
    return {
        "current": _last_status,
        "recent": _assessments[:20],
    }
