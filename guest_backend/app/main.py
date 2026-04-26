"""
Main FastAPI application for guest-side emergency evacuation system.

Server initialization, route registration, and lifecycle management.
"""
import os
import sys
from pathlib import Path

# ── Load .env file BEFORE any other imports ────────────────────────────────
# This must happen before importing config and auth modules
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, attach_db_to_app

# ── Auth module path (fallback for direct `uvicorn app.main:app` launches) ───
# run.py already sets PYTHONPATH for --reload subprocesses.
# This block handles direct invocation without run.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from auth.routes import guest_auth_router as auth_router  # noqa: E402  — guest-only (no staff login/register)

# ── Domain routers (imported AFTER sys.path is ready) ────────────────────────
from app.routes.guest import router as guest_router  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle:
    - Startup: Connect to MongoDB
    - Shutdown: Close MongoDB connection
    """
    # Startup
    logger.info("🚀 Starting up Guest Backend...")
    try:
        await connect_to_mongo()
        attach_db_to_app(app)   # expose Motor DB on app.state.db for auth routes
        logger.info("✓ MongoDB connected")
    except Exception as e:
        logger.error(f"✗ Failed to connect to MongoDB: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Guest Backend...")
    await close_mongo_connection()
    logger.info("✓ MongoDB connection closed")


# ============================================================================
# CREATE FASTAPI APP
# ============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="REST API for guest-side smart emergency evacuation system",
    lifespan=lifespan
)


# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# REGISTER ROUTES
# ============================================================================

app.include_router(guest_router)

# Auth endpoints (/auth/guest/checkin, /auth/refresh, /auth/logout, /auth/me)
app.include_router(auth_router)


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "guest-backend"
    }


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An error occurred"
        }
    )


# ============================================================================
# STARTUP/SHUTDOWN HOOKS (Alternative approach if not using lifespan)
# ============================================================================

# These are kept as examples but lifespan context manager is preferred in FastAPI 0.104+

# @app.on_event("startup")
# async def startup():
#     logger.info("Starting up...")
#     await connect_to_mongo()
#
# @app.on_event("shutdown")
# async def shutdown():
#     logger.info("Shutting down...")
#     await close_mongo_connection()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
