# ============================================================
#  InfernoGuard · Fire Risk Prediction System
#  Module  : main.py
#  Purpose : System entry point — starts API + pipeline together
# ============================================================
#
#  Usage:
#    python main.py                           # webcam + REST API (port 8000)
#    python main.py --fire-sim 0.8            # force-simulate fire at 80%
#    python main.py --source video.mp4        # run on a video file
#    python main.py --headless                # no display window, logs only
#    python main.py --api-only                # REST API server only
#    python main.py --pipeline-only           # camera pipeline only
#    python main.py --port 9000               # custom API port
# ============================================================

import argparse
import threading
import sys
import uvicorn

from pipeline import run_pipeline


def start_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """
    Launch the FastAPI server via uvicorn.
    When used as a daemon thread it exits automatically when the main thread ends.
    """
    try:
        uvicorn.run("api:app", host=host, port=port,
                    log_level="warning", reload=False)
    except (KeyboardInterrupt, SystemExit):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="🔥 InfernoGuard — AI Fire Risk Prediction System"
    )
    parser.add_argument("--source",        default="0",    help="Webcam index or video file path")
    parser.add_argument("--fire-sim",      type=float,     default=None, help="Simulate fire confidence (0–1)")
    parser.add_argument("--headless",      action="store_true",          help="No display window — console logs only")
    parser.add_argument("--api-only",      action="store_true",          help="Start only the REST API server")
    parser.add_argument("--pipeline-only", action="store_true",          help="Start only the video pipeline")
    parser.add_argument("--host",          default="0.0.0.0",            help="API host  (default: 0.0.0.0)")
    parser.add_argument("--port",          type=int, default=8000,       help="API port  (default: 8000)")
    args = parser.parse_args()

    # Convert source to int for webcam index
    try:
        src = int(args.source)
    except (ValueError, TypeError):
        src = args.source

    # ── API-only mode ─────────────────────────────────────────────────────────
    if args.api_only:
        print(f"[🌐 InfernoGuard] API running at http://{args.host}:{args.port}")
        print("[🌐 InfernoGuard] Swagger docs → http://localhost:8000/docs")
        print("[INFO] Press Ctrl+C to stop.\n")
        try:
            start_api(host=args.host, port=args.port)
        except (KeyboardInterrupt, SystemExit):
            pass
        print("\n[INFO] API server stopped.")
        return

    # ── Combined mode: API thread + pipeline on main thread ───────────────────
    if not args.pipeline_only:
        print(f"[🌐 InfernoGuard] API running at http://{args.host}:{args.port}/docs")
        threading.Thread(
            target=start_api,
            kwargs={"host": args.host, "port": args.port},
            daemon=True,
        ).start()

    run_pipeline(source=src, fire_sim=args.fire_sim, headless=args.headless)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print("\n[INFO] InfernoGuard stopped cleanly.")
        sys.exit(0)
