# ============================================================
#  InfernoGuard · YOLO Room Service
#  Module  : yolo_room_service.py
#  Purpose : Multi-room YOLO detection orchestrator with
#            sliding window buffers and HTTP emission to backend.
#
#  Architecture:
#    • Standalone process — completely decoupled from the backend
#    • On startup: fetches floor graphs from backend, discovers
#      rooms with model_enabled=true + camera_source set
#    • Per room: spawns a detection thread running the existing
#      InfernoGuard pipeline (detector → movement → density → risk)
#    • Per room: maintains a sliding window buffer (5s)
#    • When buffer stability threshold is met:
#      - ≥70% MEDIUM  → POST /alerts/fire-detection
#      - ≥70% HIGH/CRITICAL → POST /emergency/auto-trigger
#    • 30s cooldown per room after emitting an event
#
#  Usage:
#    # Dynamic discovery from backend:
#    python yolo_room_service.py --backend http://localhost:8001
#
#    # Demo mode (single video file):
#    python yolo_room_service.py --demo \
#        --video MKBAAG.mp4 \
#        --room room_101 \
#        --floor FLOOR_ID_HERE \
#        --backend http://localhost:8001
#
#    # Simulate fire on webcam:
#    python yolo_room_service.py --demo \
#        --room room_101 \
#        --floor FLOOR_ID_HERE \
#        --fire-sim 0.8
# ============================================================

import argparse
import logging
import sys
import threading
import time
from collections import Counter, deque
from statistics import mean
from typing import Dict, List, Optional, Union

import cv2
import httpx

from detector import run_detection
from movement import compute_movement
from density import compute_density
from risk_engine import evaluate_risk

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("yolo_room_service")

# ── ANSI colours ─────────────────────────────────────────────────────────────

_COLOUR = {
    "LOW":      "\033[92m",
    "MEDIUM":   "\033[93m",
    "HIGH":     "\033[91m",
    "CRITICAL": "\033[95m",
    "RESET":    "\033[0m",
}


def _c(text: str, level: str) -> str:
    return f"{_COLOUR.get(level, '')}{text}{_COLOUR['RESET']}"


# ════════════════════════════════════════════════════════════════════════════
#  Sliding Window Risk Buffer (per room)
# ════════════════════════════════════════════════════════════════════════════

class RiskBuffer:
    """
    Circular buffer holding per-frame risk evaluations for a room.
    Evaluates stability over the window and emits events when
    the threshold is met, then enters a cooldown period.
    """

    def __init__(
        self,
        window_seconds: float = 5.0,
        fps: float = 10.0,
        threshold: float = 0.70,
        cooldown_seconds: float = 30.0,
    ):
        self.max_frames = max(int(window_seconds * fps), 10)
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.buffer: deque = deque(maxlen=self.max_frames)
        self.last_emit_time: float = 0.0

    def add(self, risk_level: str, risk_score: float):
        """Add a frame's risk evaluation to the buffer."""
        self.buffer.append({
            "risk": risk_level,
            "score": risk_score,
            "time": time.time(),
        })

    def evaluate(self) -> Optional[dict]:
        """
        Check if the buffer has met a stability threshold.

        Returns:
            {"risk": "medium"|"high"|"critical", "confidence": float}
            or None if no threshold met or cooldown is active.
        """
        # Need at least 50% buffer fill
        if len(self.buffer) < self.max_frames * 0.5:
            return None

        # Cooldown check
        if time.time() - self.last_emit_time < self.cooldown_seconds:
            return None

        counts = Counter(entry["risk"] for entry in self.buffer)
        total = len(self.buffer)

        # Check HIGH/CRITICAL first (higher severity takes priority)
        high_critical = counts.get("HIGH", 0) + counts.get("CRITICAL", 0)
        if high_critical / total >= self.threshold:
            self.last_emit_time = time.time()
            scores = [
                e["score"] for e in self.buffer
                if e["risk"] in ("HIGH", "CRITICAL")
            ]
            # Determine predominant level
            if counts.get("CRITICAL", 0) >= counts.get("HIGH", 0):
                level = "critical"
            else:
                level = "high"
            return {
                "risk": level,
                "confidence": round(min(mean(scores) / 100.0, 1.0), 3),
            }

        # Check MEDIUM
        medium_count = counts.get("MEDIUM", 0)
        if medium_count / total >= self.threshold:
            self.last_emit_time = time.time()
            scores = [
                e["score"] for e in self.buffer
                if e["risk"] == "MEDIUM"
            ]
            return {
                "risk": "medium",
                "confidence": round(min(mean(scores) / 100.0, 1.0), 3),
            }

        return None


# ════════════════════════════════════════════════════════════════════════════
#  Room Discovery (Dynamic)
# ════════════════════════════════════════════════════════════════════════════

def discover_rooms(backend_url: str) -> List[dict]:
    """
    Fetch floor graphs from the backend and extract rooms with
    model_enabled=true and a camera_source set.

    Returns list of:
        {"room_id": str, "floor_id": str, "camera_source": str}
    """
    rooms = []
    try:
        resp = httpx.get(f"{backend_url}/staff/floors", timeout=10.0)
        resp.raise_for_status()
        floors = resp.json()
    except Exception as e:
        logger.error("Failed to fetch floors from backend: %s", e)
        return rooms

    for floor in floors:
        floor_id = floor.get("id", "")
        graph = floor.get("graph") or {}
        nodes = graph.get("nodes", [])
        for node in nodes:
            if node.get("model_enabled") and node.get("camera_source"):
                rooms.append({
                    "room_id": node["id"],
                    "floor_id": floor_id,
                    "camera_source": node["camera_source"],
                })
                logger.info(
                    "Discovered room: %s (floor=%s, source=%s)",
                    node["id"], floor_id, node["camera_source"],
                )

    if not rooms:
        logger.warning("No rooms with model_enabled=true found in any floor graph.")
    return rooms


# ════════════════════════════════════════════════════════════════════════════
#  HTTP Emitter (non-blocking)
# ════════════════════════════════════════════════════════════════════════════

class AlertEmitter:
    """Sends stabilized risk events to the backend via HTTP."""

    def __init__(self, backend_url: str):
        self.backend_url = backend_url.rstrip("/")
        self._client = httpx.Client(timeout=5.0)

    def emit(self, room_id: str, floor_id: str, event: dict):
        """
        Send a stabilized risk event to the appropriate backend endpoint.
        Non-blocking: errors are logged but do not crash the pipeline.
        """
        risk = event["risk"]
        confidence = event["confidence"]

        if risk == "medium":
            url = f"{self.backend_url}/alerts/fire-detection"
            payload = {
                "room_id": room_id,
                "risk": "medium",
                "confidence": confidence,
                "source": "yolo",
                "floor_id": floor_id,
            }
        else:
            url = f"{self.backend_url}/emergency/auto-trigger"
            payload = {
                "room_id": room_id,
                "risk": risk,
                "confidence": confidence,
                "triggered_by": "model",
                "floor_id": floor_id,
            }

        try:
            resp = self._client.post(url, json=payload)
            if resp.status_code in (200, 201):
                logger.warning(
                    "🚨 ALERT SENT | room=%s risk=%s conf=%.3f → %s %d",
                    room_id, risk, confidence, url, resp.status_code,
                )
            elif resp.status_code == 429:
                logger.info(
                    "Cooldown active (backend) | room=%s → %s",
                    room_id, resp.json().get("detail", ""),
                )
            elif resp.status_code == 409:
                logger.info(
                    "Dedup rejected (backend) | room=%s → %s",
                    room_id, resp.json().get("detail", ""),
                )
            else:
                logger.warning(
                    "Backend returned %d | room=%s → %s",
                    resp.status_code, room_id, resp.text[:200],
                )
        except Exception as e:
            logger.error("Failed to emit alert for room=%s: %s", room_id, e)

    def close(self):
        self._client.close()


# ════════════════════════════════════════════════════════════════════════════
#  Room Detection Loop (runs in a thread per room)
# ════════════════════════════════════════════════════════════════════════════

def run_room_detection(
    room_id: str,
    floor_id: str,
    source: Union[int, str],
    emitter: AlertEmitter,
    fire_sim: Optional[float] = None,
    stop_event: Optional[threading.Event] = None,
):
    """
    Per-room detection loop. Opens the video source, runs YOLO detection
    per frame, feeds the risk buffer, and emits alerts when thresholds are met.
    """
    logger.info("Starting detection for room=%s source=%s", room_id, source)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        logger.error("Cannot open video source for room=%s: %s", room_id, source)
        return

    # ── Startup delay — let codec / backend fully initialize ──────────────
    time.sleep(0.5)

    # Estimate FPS from source (default 10 for RTSP/webcam)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    fps = src_fps if src_fps and src_fps > 0 else 10.0
    buffer = RiskBuffer(window_seconds=5.0, fps=fps)

    # ── Explicit state reset (every cold start) ───────────────────────────
    prev_frame = None
    frame_count = 0
    movement_score = 0.0
    people_count = 0

    # ── Warm-up phase — discard first 10 frames ──────────────────────────
    # Stabilizes codec buffers and avoids garbage / black initial frames
    # that plague cold-start video files (webcam naturally self-warms).
    warmup_frames = 10
    warmup_ok = 0
    for i in range(warmup_frames):
        ret, warmup_frame = cap.read()
        if not ret:
            break
        warmup_ok += 1
        # Seed prev_frame with the last warm-up frame so movement
        # detection has a valid reference from frame #1.
        prev_frame = warmup_frame.copy()

    logger.info(
        "Warm-up complete for room=%s | %d/%d frames consumed, prev_frame seeded=%s",
        room_id, warmup_ok, warmup_frames, prev_frame is not None,
    )

    try:
        while not (stop_event and stop_event.is_set()):
            ret, frame = cap.read()
            if not ret:
                # For video files: loop or stop
                if isinstance(source, str):
                    logger.info("End of video for room=%s — stopping", room_id)
                    break
                continue

            frame_count += 1

            # ── Validate frame integrity ──────────────────────────────────
            if frame is None or frame.size == 0:
                logger.debug("[%s] Skipping empty frame #%d", room_id, frame_count)
                continue

            # ── YOLO detection ────────────────────────────────────────────
            detection = run_detection(frame)
            if fire_sim is not None:
                detection["fire_conf"] = round(float(fire_sim), 3)
                detection["has_fire"] = fire_sim >= 0.7
                detection["has_smoke"] = fire_sim >= 0.5

            # ── Movement ──────────────────────────────────────────────────
            # prev_frame is seeded during warm-up, so first real frame
            # already gets a valid (non-zero) movement score.
            if prev_frame is None:
                # Fallback: if warm-up produced nothing, seed now & skip
                prev_frame = frame.copy()
                movement_score = 0.0
                logger.debug("[%s] Seeding prev_frame on first valid frame", room_id)
                continue
            movement_score = compute_movement(prev_frame, frame)
            prev_frame = frame.copy()

            # ── Density ───────────────────────────────────────────────────
            density_value, density_label = compute_density(detection["people_count"])

            # ── Risk evaluation ───────────────────────────────────────────
            result = evaluate_risk(
                fire_conf=detection["fire_conf"],
                density_label=density_label,
                density_value=density_value,
                movement_score=movement_score,
            )

            risk_level = result["risk"]
            risk_score = result["score"]

            # ── Debug log (every frame for first 30, then periodic) ───────
            if frame_count <= 30 or frame_count % 30 == 0:
                log = (
                    f"[{room_id}] #{frame_count:4d} | "
                    f"People: {detection['people_count']:3d} | "
                    f"Fire: {detection['fire_conf']:.3f} | "
                    f"Move: {movement_score:.4f} | "
                    f"Density: {density_label}({density_value:.3f}) | "
                    f"→ {risk_level} ({risk_score:.1f})"
                )
                if frame_count <= 30:
                    logger.info("STARTUP %s", log)
                else:
                    print(_c(log, risk_level))

            # ── Feed sliding window ───────────────────────────────────────
            buffer.add(risk_level, risk_score)

            # ── Evaluate and emit ─────────────────────────────────────────
            event = buffer.evaluate()
            if event:
                logger.warning(
                    "Threshold met | room=%s risk=%s conf=%.3f → sending to backend",
                    room_id, event["risk"], event["confidence"],
                )
                # Emit in a separate thread to avoid blocking the pipeline
                threading.Thread(
                    target=emitter.emit,
                    args=(room_id, floor_id, event),
                    daemon=True,
                ).start()

            # Rate limit to approximate target FPS
            time.sleep(max(0, 1.0 / fps - 0.01))

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        logger.info("Detection stopped for room=%s (processed %d frames)", room_id, frame_count)


# ════════════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="🔥 InfernoGuard · YOLO Room Service — Multi-room fire detection"
    )
    parser.add_argument(
        "--backend", default="http://localhost:8001",
        help="Backend API base URL (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run in demo mode with a single video/webcam source",
    )
    parser.add_argument(
        "--video", default=None,
        help="Video file path for demo mode (uses webcam if not set)",
    )
    parser.add_argument(
        "--room", default="room_101",
        help="Room ID for demo mode (default: room_101)",
    )
    parser.add_argument(
        "--floor", default=None,
        help="Floor ID for demo mode (required in demo without backend discovery)",
    )
    parser.add_argument(
        "--fire-sim", type=float, default=None,
        help="Simulate fire confidence (0–1) — overrides YOLO fire detection",
    )
    args = parser.parse_args()

    emitter = AlertEmitter(args.backend)
    stop_event = threading.Event()

    if args.demo:
        # ── Demo mode: single room ────────────────────────────────────────
        source = args.video if args.video else 0
        floor_id = args.floor or "unknown_floor"

        print(f"[🔥 InfernoGuard] Demo mode: room={args.room} source={source}")
        print(f"[🔥 InfernoGuard] Backend: {args.backend}")
        if args.fire_sim is not None:
            print(f"[🔥 InfernoGuard] Fire simulation: {args.fire_sim}")
        print("[🔥 InfernoGuard] Press Ctrl+C to stop.\n")

        try:
            run_room_detection(
                room_id=args.room,
                floor_id=floor_id,
                source=source,
                emitter=emitter,
                fire_sim=args.fire_sim,
                stop_event=stop_event,
            )
        except KeyboardInterrupt:
            pass
        finally:
            emitter.close()
            print("\n[INFO] Demo stopped.")
        return

    # ── Dynamic discovery mode ────────────────────────────────────────────
    print(f"[🔥 InfernoGuard] Room Service starting — backend: {args.backend}")
    rooms = discover_rooms(args.backend)

    if not rooms:
        print("[ERROR] No model-enabled rooms found. Exiting.")
        print("[HINT] Set model_enabled=true and camera_source on floor nodes via:")
        print(f"  PUT {args.backend}/staff/floors/{{floor_id}}/graph")
        sys.exit(1)

    print(f"[🔥 InfernoGuard] Monitoring {len(rooms)} room(s):")
    for r in rooms:
        print(f"  • {r['room_id']} (floor={r['floor_id']}, source={r['camera_source']})")
    print("[🔥 InfernoGuard] Press Ctrl+C to stop.\n")

    threads: List[threading.Thread] = []
    for room in rooms:
        t = threading.Thread(
            target=run_room_detection,
            kwargs={
                "room_id": room["room_id"],
                "floor_id": room["floor_id"],
                "source": room["camera_source"],
                "emitter": emitter,
                "fire_sim": args.fire_sim,
                "stop_event": stop_event,
            },
            daemon=True,
            name=f"yolo-{room['room_id']}",
        )
        t.start()
        threads.append(t)
        logger.info("Spawned detection thread for %s", room["room_id"])

    try:
        # Keep main thread alive
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down all detection threads...")
        stop_event.set()
        for t in threads:
            t.join(timeout=5.0)
        emitter.close()
        print("[INFO] YOLO Room Service stopped cleanly.")


if __name__ == "__main__":
    main()
