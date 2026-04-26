# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : detector.py
#  Purpose : YOLO-based detection of persons, fire, and smoke
# ============================================================
#
#  Models used:
#    ▸ YOLOv8s (COCO)        — person detection
#    ▸ InfernoGuard (D-Fire)  — fire & smoke detection
#
#  Fire detection classes (InfernoGuard):
#    Class 0 → smoke  (early warning, weighted 0.7×)
#    Class 1 → fire   (confirmed flame, weighted 1.0×)
#
#  To enable real fire detection, set the environment variable:
#    Windows PowerShell : $env:FIRE_MODEL_PATH='infernoguard_best.pt'
#    Windows CMD        : set FIRE_MODEL_PATH=infernoguard_best.pt
# ============================================================

import os
import random
from typing import Optional
from ultralytics import YOLO

# ── Constants ────────────────────────────────────────────────────────────────

PERSON_CLASS_ID     = 0       # COCO: person
SMOKE_CLASS_ID      = 0       # InfernoGuard: smoke (early warning)
FIRE_CLASS_ID       = 1       # InfernoGuard: confirmed fire
SMOKE_WEIGHT        = 0.7     # smoke raises risk, but less than confirmed fire
FIRE_CONF_THRESHOLD = 0.35    # recommended by InfernoGuard authors

# ── Lazy model singletons (loaded once at first call) ────────────────────────

_person_model = None
_fire_model   = None


def _get_person_model() -> YOLO:
    """Load YOLOv8s on first call; reuse singleton afterwards."""
    global _person_model
    if _person_model is None:
        _person_model = YOLO("yolov8s.pt")          # auto-downloads if absent
    return _person_model


def _get_fire_model() -> Optional[YOLO]:
    """
    Load the InfernoGuard fire/smoke model.

    Resolution order:
      1. FIRE_MODEL_PATH env var (explicit override)
      2. infernoguard_best.pt in the same directory as this script (auto-detect)
    """
    global _fire_model
    if _fire_model is not None:
        return _fire_model

    # 1. Explicit env var
    path = os.getenv("FIRE_MODEL_PATH", "")

    # 2. Auto-detect in script directory
    if not path or not os.path.exists(path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(script_dir, "infernoguard_best.pt")
        if os.path.exists(candidate):
            path = candidate

    if path and os.path.exists(path):
        print(f"[🔥 InfernoGuard] Loading fire model → {path}")
        _fire_model = YOLO(path)

    return _fire_model


# ── Public API ───────────────────────────────────────────────────────────────

def run_detection(frame) -> dict:
    """
    Run person + fire/smoke detection on a single BGR video frame.

    Returns
    -------
    {
        "people_count" : int    — number of persons detected
        "fire_conf"    : float  — weighted fire/smoke confidence (0.0–1.0)
        "has_fire"     : bool   — confirmed flame detected
        "has_smoke"    : bool   — smoke (pre-ignition) detected
    }
    """
    # ── Person detection ─────────────────────────────────────────────────────
    people_count = sum(
        1 for box in _get_person_model()(frame, verbose=False)[0].boxes
        if int(box.cls[0]) == PERSON_CLASS_ID
    )

    # ── Fire / smoke detection ───────────────────────────────────────────────
    fire_model = _get_fire_model()
    fire_conf  = 0.0
    has_fire   = False
    has_smoke  = False

    if fire_model is not None:
        detections = fire_model(frame, verbose=False, conf=FIRE_CONF_THRESHOLD)[0]
        for box in detections.boxes:
            cls_id    = int(box.cls[0])
            raw_conf  = float(box.conf[0])

            if cls_id == FIRE_CLASS_ID:
                has_fire  = True
                effective = raw_conf                # full weight — confirmed flame
            elif cls_id == SMOKE_CLASS_ID:
                has_smoke = True
                effective = raw_conf * SMOKE_WEIGHT # partial weight — early warning
            else:
                continue

            if effective > fire_conf:
                fire_conf = effective
    else:
        # ── Simulation mode (no fire model loaded) ───────────────────────────
        # Returns low random noise; override via --fire-sim flag in pipeline
        fire_conf = round(random.uniform(0.0, 0.15), 3)

    return {
        "people_count" : people_count,
        "fire_conf"    : round(fire_conf, 3),
        "has_fire"     : has_fire,
        "has_smoke"    : has_smoke,
    }
