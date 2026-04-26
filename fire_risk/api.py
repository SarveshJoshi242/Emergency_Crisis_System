# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : api.py
#  Purpose : FastAPI REST endpoint for risk prediction
# ============================================================
#
#  Endpoints:
#    GET  /               → health check
#    POST /predict        → evaluate risk from sensor signals
#    GET  /test/{scene}   → built-in demo scenarios
#
#  Run standalone:
#    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
#
#  Swagger docs available at:
#    http://localhost:8000/docs
# ============================================================

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from density import compute_density
from risk_engine import evaluate_risk

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "🔥 InfernoGuard — Fire Risk API",
    description = "Real-time fire risk assessment using computer vision signals.",
    version     = "1.0.0",
)


# ── Request / Response schemas ───────────────────────────────────────────────

class PredictRequest(BaseModel):
    people_count   : int   = Field(..., ge=0,   description="Persons detected in frame")
    fire_conf      : float = Field(..., ge=0.0, le=1.0, description="Fire/smoke confidence (0–1)")
    movement_score : float = Field(..., ge=0.0, le=1.0, description="Movement intensity score (0–1)")

    @field_validator("fire_conf", "movement_score", mode="before")
    @classmethod
    def _round(cls, v):
        return round(float(v), 4)


class PredictResponse(BaseModel):
    risk           : str
    score          : float
    action         : str
    density_label  : str
    density_value  : float
    people_count   : int
    fire_conf      : float
    movement_score : float


# ── Built-in demo scenarios ──────────────────────────────────────────────────

_SCENARIOS = {
    "no_people"     : {"people_count": 0,  "fire_conf": 0.00, "movement_score": 0.00},
    "crowd_no_fire" : {"people_count": 20, "fire_conf": 0.10, "movement_score": 0.40},
    "fire_crowd"    : {"people_count": 35, "fire_conf": 0.75, "movement_score": 0.40},
    "critical"      : {"people_count": 40, "fire_conf": 0.85, "movement_score": 0.75},
}


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health_check():
    """Service health check."""
    return {"status": "ok", "service": "InfernoGuard Fire Risk API"}


@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
def predict(payload: PredictRequest):
    """
    Evaluate fire risk level from vision signals.

    - **people_count**   : integer ≥ 0
    - **fire_conf**      : float 0–1 (InfernoGuard output or --fire-sim value)
    - **movement_score** : float 0–1 (frame-differencing output)
    """
    density_value, density_label = compute_density(payload.people_count)

    result = evaluate_risk(
        fire_conf      = payload.fire_conf,
        density_label  = density_label,
        density_value  = density_value,
        movement_score = payload.movement_score,
    )

    return PredictResponse(
        risk           = result["risk"],
        score          = result["score"],
        action         = result["action"],
        density_label  = density_label,
        density_value  = density_value,
        people_count   = payload.people_count,
        fire_conf      = payload.fire_conf,
        movement_score = payload.movement_score,
    )


@app.get("/test/{scenario}", tags=["Demo"])
def run_scenario(scenario: str):
    """
    Run a predefined demo scenario.

    Available: **no_people** | **crowd_no_fire** | **fire_crowd** | **critical**
    """
    if scenario not in _SCENARIOS:
        raise HTTPException(
            status_code = 404,
            detail      = f"Unknown scenario. Choose from: {list(_SCENARIOS)}",
        )
    return predict(PredictRequest(**_SCENARIOS[scenario]))
