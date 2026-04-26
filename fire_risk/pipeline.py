# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : pipeline.py
#  Purpose : Real-time webcam / video detection loop
# ============================================================
#
#  Per-frame pipeline:
#    1. Capture frame  →  webcam or video file
#    2. YOLO detect    →  person count + fire/smoke confidence
#    3. Frame diff     →  movement intensity score
#    4. Density calc   →  LOW / MEDIUM / HIGH crowd label
#    5. Risk engine    →  CRITICAL / HIGH / MEDIUM / LOW + action
#    6. Overlay + log  →  burn stats onto frame, print coloured log
#
#  CLI usage:
#    python pipeline.py                      # webcam (device 0)
#    python pipeline.py --source video.mp4   # video file
#    python pipeline.py --fire-sim 0.8       # simulate fire at 80% confidence
#    python pipeline.py --headless           # console logs only, no window
#
#  Press 'q' in the video window to quit.
# ============================================================

import argparse
import time
from typing import Optional, Union
import cv2

from detector    import run_detection
from movement    import compute_movement
from density     import compute_density
from risk_engine import evaluate_risk


# ── ANSI colour palette for terminal logs ────────────────────────────────────
_COLOUR = {
    "LOW"      : "\033[92m",    # green
    "MEDIUM"   : "\033[93m",    # yellow
    "HIGH"     : "\033[91m",    # red
    "CRITICAL" : "\033[95m",    # magenta
    "RESET"    : "\033[0m",
}

# ── BGR colours for on-frame text overlay ────────────────────────────────────
_OVERLAY_COLOUR = {
    "LOW"      : (0, 200, 0),
    "MEDIUM"   : (0, 200, 255),
    "HIGH"     : (0, 60, 255),
    "CRITICAL" : (180, 0, 255),
}


def _coloured(text: str, level: str) -> str:
    """Wrap text in ANSI colour codes for terminal output."""
    return f"{_COLOUR.get(level, '')}{text}{_COLOUR['RESET']}"


def _draw_overlay(frame, detection: dict, movement_score: float, result: dict) -> None:
    """Burn the current risk metrics onto the video frame."""
    colour = _OVERLAY_COLOUR.get(result["risk"], (255, 255, 255))
    lines  = [
        f"People : {detection['people_count']}",
        f"Fire   : {detection['fire_conf']:.2f}",
        f"Move   : {movement_score:.3f}",
        f"Risk   : {result['risk']}  ({result['score']:.1f})",
        f"Action : {result['action']}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (10, 30 + i * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2, cv2.LINE_AA)


# ── Main pipeline loop ───────────────────────────────────────────────────────

def run_pipeline(
    source   : Union[int, str] = 0,
    fire_sim : Optional[float] = None,
    headless : bool            = False,
) -> None:
    """
    Start the real-time detection and risk evaluation loop.

    Parameters
    ----------
    source   : Webcam device index (int) or video file path (str)
    fire_sim : If set, overrides fire_conf with this fixed value every frame
    headless : If True, skips the display window (console logs only)
    """
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {source!r}")

    prev_frame  = None
    frame_count = 0
    fps_time    = time.time()

    print("[🚀 InfernoGuard] Pipeline started — press 'q' to quit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[INFO] End of stream.")
                break

            frame_count += 1

            # ── Step 1 · YOLO detection ───────────────────────────────────────
            detection = run_detection(frame)
            if fire_sim is not None:
                detection["fire_conf"] = round(float(fire_sim), 3)
                detection["has_fire"]  = fire_sim >= 0.7
                detection["has_smoke"] = fire_sim >= 0.5

            # ── Step 2 · Movement intensity ───────────────────────────────────
            movement_score = compute_movement(prev_frame, frame)
            prev_frame     = frame.copy()

            # ── Step 3 · Crowd density ────────────────────────────────────────
            density_value, density_label = compute_density(detection["people_count"])

            # ── Step 4 · Risk evaluation ──────────────────────────────────────
            result = evaluate_risk(
                fire_conf      = detection["fire_conf"],
                density_label  = density_label,
                density_value  = density_value,
                movement_score = movement_score,
            )

            # ── Step 5 · Coloured console log ─────────────────────────────────
            fire_tag = ""
            if detection.get("has_fire"):  fire_tag = " 🔥FIRE"
            elif detection.get("has_smoke"): fire_tag = " 💨SMOKE"

            log = (
                f"[INFO] People: {detection['people_count']:3d} | "
                f"Fire: {detection['fire_conf']:.2f}{fire_tag} | "
                f"Move: {movement_score:.3f} | "
                f"Density: {density_label} | "
                f"→ {result['risk']} ({result['score']:.1f}) | {result['action']}"
            )
            print(_coloured(log, result["risk"]))

            # ── FPS counter (every 30 frames) ─────────────────────────────────
            if frame_count % 30 == 0:
                elapsed  = time.time() - fps_time
                fps      = 30 / elapsed if elapsed > 0 else 0
                fps_time = time.time()
                print(f"[FPS] {fps:.1f}")

            # ── Step 6 · Video window ─────────────────────────────────────────
            if not headless:
                try:
                    _draw_overlay(frame, detection, movement_score, result)
                    cv2.imshow("🔥 InfernoGuard — Fire Risk Monitor", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        print("[INFO] User quit.")
                        break
                except cv2.error:
                    print("[WARN] Display unavailable — switching to headless mode.")
                    print("[HINT] Fix: pip uninstall opencv-python-headless -y && pip install opencv-python")
                    headless = True

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user (Ctrl+C). Shutting down…")

    finally:
        cap.release()
        if not headless:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InfernoGuard — Real-time Fire Risk Pipeline")
    parser.add_argument("--source",   default=0,    help="Webcam index or video file path")
    parser.add_argument("--fire-sim", type=float,   default=None, help="Simulate fire confidence (0–1)")
    parser.add_argument("--headless", action="store_true",        help="Run without display window")
    args = parser.parse_args()

    try:
        src = int(args.source)
    except (ValueError, TypeError):
        src = args.source

    run_pipeline(source=src, fire_sim=args.fire_sim, headless=args.headless)
