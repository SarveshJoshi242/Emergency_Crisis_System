# ============================================================
#  Emergency Backend · database.py
#  Purpose: Motor async MongoDB client + collection accessor
# ============================================================

import logging
from typing import Optional
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where(),   # fixes SSL handshake on Python 3.9 Windows
        )
    return _client


def get_db():
    return get_client()[settings.DB_NAME]


def get_collection(name: str):
    """Return a Motor collection by name."""
    return get_db()[name]


# Expose the Motor DB instance so auth routes can access it via request.app.state.db
def attach_db_to_app(app) -> None:
    """Call this at startup to attach the Motor database to app.state."""
    app.state.db = get_db()

async def ensure_indexes() -> None:
    """
    Create MongoDB indexes on startup (idempotent — safe to call repeatedly).
    Uses background=True so existing data is not locked during index build.
    """
    db = get_db()
    try:
        # fire_events: queried by floor + time for history
        await db["fire_events"].create_index(
            [("floor_id", ASCENDING), ("timestamp", DESCENDING)],
            background=True, name="fire_events_floor_time",
        )

        # alerts: active alerts filtered by floor + status
        await db["alerts"].create_index(
            [("floor_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="alerts_floor_status",
        )
        await db["alerts"].create_index(
            [("source_room", ASCENDING)],
            background=True, name="alerts_source_room",
            sparse=True,
        )

        # ai_danger_events: queried by floor + room + time
        await db["ai_danger_events"].create_index(
            [("floor_id", ASCENDING), ("timestamp", DESCENDING)],
            background=True, name="ai_events_floor_time",
        )
        await db["ai_danger_events"].create_index(
            [("floor_id", ASCENDING), ("room_id", ASCENDING), ("timestamp", DESCENDING)],
            background=True, name="ai_events_room_time",
            sparse=True,
        )

        # tasks: queried by floor for dashboard
        await db["tasks"].create_index(
            [("floor_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="tasks_floor_status",
        )

        # floors: queried by name, floor_id slug, and sorted by creation time
        await db["floors"].create_index(
            [("name", ASCENDING)],
            background=True, name="floors_name",
        )
        await db["floors"].create_index(
            [("created_at", DESCENDING)],
            background=True, name="floors_created_at",
        )
        await db["floors"].create_index(
            [("floor_id", ASCENDING)],
            background=True, name="floors_floor_id_slug",
        )

        # help_requests: staff dashboard queries pending requests by floor/status
        await db["help_requests"].create_index(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            background=True, name="help_requests_status_time",
        )
        await db["help_requests"].create_index(
            [("floor_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="help_requests_floor_status",
        )
        await db["help_requests"].create_index(
            [("session_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"status": "pending"},
            background=True,
            name="help_requests_session_pending_unique",
        )

        # messages: guest notification polling — filter by type+status, sort by time
        await db["messages"].create_index(
            [("type", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
            background=True, name="messages_type_status_time",
        )

        # guest_sessions: shared collection — staff can query evacuees per floor
        await db["guest_sessions"].create_index(
            [("session_id", ASCENDING)], unique=True,
            background=True, name="guest_sessions_sid_unique",
        )
        await db["guest_sessions"].create_index(
            [("floor_id", ASCENDING), ("status", ASCENDING)],
            background=True, name="guest_sessions_floor_status",
        )

        # emergency_state: single-doc collection — fast read for guest polling
        await db["emergency_state"].create_index(
            [("updated_at", DESCENDING)],
            background=True, name="emergency_state_time",
        )

        # floors: multi-key index on embedded graph nodes — enables fast room→floor lookup
        # Used by GET /guest-api/rooms/{room_id}/floor and /guest/session/start
        await db["floors"].create_index(
            [("graph.nodes.id", ASCENDING), ("graph.nodes.type", ASCENDING)],
            background=True, name="floors_graph_nodes_id_type",
        )

        # ai_fire_alerts: YOLO detection alerts — queried by room + state
        await db["ai_fire_alerts"].create_index(
            [("room_id", ASCENDING), ("state", ASCENDING)],
            background=True, name="ai_fire_alerts_room_state",
        )
        await db["ai_fire_alerts"].create_index(
            [("room_id", ASCENDING), ("created_at", DESCENDING)],
            background=True, name="ai_fire_alerts_room_time",
        )
        await db["ai_fire_alerts"].create_index(
            [("state", ASCENDING), ("created_at", DESCENDING)],
            background=True, name="ai_fire_alerts_state_time",
        )

        # ── Auth indexes ──────────────────────────────────────────────────────
        # staff_accounts: unique email lookup for login
        await db["staff_accounts"].create_index(
            [("email", ASCENDING)],
            unique=True,
            background=True,
            name="staff_accounts_email_unique",
        )

        # refresh_tokens: fast lookup by token string + automatic TTL expiry
        await db["refresh_tokens"].create_index(
            [("token", ASCENDING)],
            unique=True,
            background=True,
            name="refresh_tokens_token_unique",
        )
        await db["refresh_tokens"].create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,   # MongoDB TTL — auto-deletes expired tokens
            background=True,
            name="refresh_tokens_ttl",
        )
        await db["refresh_tokens"].create_index(
            [("user_id", ASCENDING)],
            background=True,
            name="refresh_tokens_user_id",
        )

        logger.info("✅ MongoDB indexes ensured")
    except Exception as e:
        # Non-fatal — indexes are a performance optimization, not required for correctness
        logger.warning(f"Index creation warning (non-fatal): {e}")

