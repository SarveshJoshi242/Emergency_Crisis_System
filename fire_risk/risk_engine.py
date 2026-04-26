# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : risk_engine.py
#  Purpose : Rule-based risk level evaluation
# ============================================================
#
#  Inputs:
#    fire_conf     float  [0–1]   Weighted fire/smoke confidence
#    density_label str            "LOW" | "MEDIUM" | "HIGH"
#    density_value float  [0–1+]  Numeric density (capped at 1 for scoring)
#    movement_score float [0–1]   Frame-differencing movement intensity
#
#  Risk levels (priority order — first match wins):
#    ┌──────────┬────────────────────────────────────────────────────┐
#    │ CRITICAL │ fire > 0.70  AND  density == HIGH  AND  move > 0.60│
#    │ HIGH     │ fire > 0.60  AND  density ∈ {MEDIUM, HIGH}         │
#    │ MEDIUM   │ fire > 0.50  OR   movement > 0.60                  │
#    │ LOW      │ none of the above                                  │
#    └──────────┴────────────────────────────────────────────────────┘
#
#  Risk score formula (0 – 100):
#    score = (fire_conf × 50) + (density × 30) + (movement × 20)
#
#  Actions:
#    LOW      → MONITOR
#    MEDIUM   → NOTIFY_STAFF
#    HIGH     → ALERT
#    CRITICAL → EVACUATE
# ============================================================

# ── Action mapping ───────────────────────────────────────────────────────────
ACTION_MAP = {
    "LOW"      : "MONITOR",
    "MEDIUM"   : "NOTIFY_STAFF",
    "HIGH"     : "ALERT",
    "CRITICAL" : "EVACUATE",
}


def evaluate_risk(
    fire_conf      : float,
    density_label  : str,
    density_value  : float,
    movement_score : float,
) -> dict:
    """
    Apply rule-based logic to produce a risk level, score, and action.

    Returns
    -------
    {
        "risk"   : str    — "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
        "score"  : float  — composite risk score [0–100]
        "action" : str    — recommended response action
    }
    """
    # ── Rule evaluation (highest priority first) ─────────────────────────────
    if fire_conf > 0.7 and density_label == "HIGH" and movement_score > 0.6:
        risk_level = "CRITICAL"

    elif fire_conf > 0.6 and density_label in ("MEDIUM", "HIGH"):
        risk_level = "HIGH"

    elif fire_conf > 0.5 or movement_score > 0.6:
        risk_level = "MEDIUM"

    else:
        risk_level = "LOW"

    # ── Weighted composite score ─────────────────────────────────────────────
    capped_density = min(density_value, 1.0)          # cap density at 1.0 for clean 0–100 range
    risk_score     = (fire_conf * 50) + (capped_density * 30) + (movement_score * 20)
    risk_score     = round(min(risk_score, 100.0), 2)

    return {
        "risk"   : risk_level,
        "score"  : risk_score,
        "action" : ACTION_MAP[risk_level],
    }
