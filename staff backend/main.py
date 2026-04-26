# ============================================================
#  Emergency Backend · main.py
#  Purpose: FastAPI app factory + router mounts
# ============================================================

import os
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# ── Load .env file BEFORE any other imports ────────────────────────────────
# This must happen before importing config and auth modules
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import ensure_indexes, attach_db_to_app

# ── Auth module sys.path MUST be patched before any domain router imports ─────
# Domain routers import `from auth.dependencies import require_staff` at module
# load time, so the auth package must be on sys.path first.
_HERE = os.path.dirname(os.path.abspath(__file__))
_AUTH_ROOT = os.path.join(_HERE, "..")
if _AUTH_ROOT not in sys.path:
    sys.path.insert(0, _AUTH_ROOT)

from auth.routes import router as auth_router  # noqa: E402

# ── Domain routers (imported AFTER sys.path is ready) ────────────────────────
from routers import alert, fire, tasks, staff, websocket  # noqa: E402
from routers import webhook                                # noqa: E402
from routers import staff_floors                          # noqa: E402
from routers import guest_bridge                          # noqa: E402
from routers import yolo_alerts                           # noqa: E402


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "floorplans"), exist_ok=True)
    await ensure_indexes()
    attach_db_to_app(app)   # expose Motor DB on app.state.db for auth routes
    logger.info(f"✅ Emergency Backend running on port {settings.PORT}")
    logger.info(f"📦 MongoDB: {settings.DB_NAME}")
    logger.info(f"📂 Uploads: {settings.UPLOAD_DIR}/")
    logger.info(f"📡 WebSocket: ws://localhost:{settings.PORT}/ws/live")
    logger.info(f"🔗 Webhook:   POST http://localhost:{settings.PORT}/webhook/ai-danger-detection")
    logger.info(f"🏨 FloorMgmt: http://localhost:{settings.PORT}/staff/floors")
    logger.info(f"📖 Swagger:   http://localhost:{settings.PORT}/docs")
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("🛑 Emergency Backend shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="🚨 Smart Emergency Management Platform",
    description=(
        "Real-time emergency management backend for hotels and buildings. "
        "Integrates with InfernoGuard fire detection and an AI webhook system "
        "for sustained danger validation. Auto-generates alerts and tasks, "
        "and pushes live updates over WebSocket with room-level precision."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
# Auth (mounts at /auth: login, refresh, logout, /me)
app.include_router(auth_router)

# Domain routers
app.include_router(alert.router)
app.include_router(fire.router)
app.include_router(tasks.router)
app.include_router(staff.router)
app.include_router(websocket.router)
app.include_router(webhook.router)
app.include_router(staff_floors.router)
app.include_router(guest_bridge.router)  # guest ↔ staff bridge
app.include_router(yolo_alerts.router)   # YOLO fire detection endpoints

# ── Static file serving for uploads (floor plans, etc.) ──────────────────────
# Serves everything under the uploads/ directory at /uploads/<path>
# e.g. /uploads/floorplans/floor1.png → http://localhost:8001/uploads/floorplans/floor1.png
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR, check_dir=False), name="uploads")


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health():
    return {
        "status":  "ok",
        "service": "Smart Emergency Management Platform",
        "version": "2.0.0",
    }


# ── Debug: active danger states ───────────────────────────────────────────────
@app.get("/debug/danger-states", tags=["Debug"], include_in_schema=False)
def debug_danger_states():
    """Returns current in-memory danger states — for dev/debugging only."""
    from services.danger_tracker import get_all_states
    return get_all_states()

