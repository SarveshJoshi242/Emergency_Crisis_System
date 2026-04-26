"""
MongoDB connection and initialization.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_db = None


async def connect_to_mongo():
    """Connect to MongoDB Atlas."""
    global _db
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        # Test connection
        await client.admin.command('ping')
        _db = client[settings.MONGODB_DB_NAME]

        # Index for room lookup inside floors collection (staff-written)
        # Covers both the guest route fallback and staff bridge room→floor endpoint
        await _db.floors.create_index(
            [("nodes.id", 1)],
            name="idx_floors_nodes_id",
            background=True
        )
        await _db.floors.create_index(
            [("graph.nodes.id", 1), ("graph.nodes.type", 1)],
            name="idx_floors_graph_nodes_id_type",
            background=True
        )

        # guest_sessions — every /guest/* call looks up by session_id
        await _db.guest_sessions.create_index(
            [("session_id", 1)], unique=True,
            name="idx_guest_sessions_sid", background=True,
        )
        await _db.guest_sessions.create_index(
            [("floor_id", 1), ("status", 1)],
            name="idx_guest_sessions_floor_status", background=True,
        )

        # guest_logs — action history lookup per session
        await _db.guest_logs.create_index(
            [("session_id", 1), ("timestamp", -1)],
            name="idx_guest_logs_session", background=True,
        )

        # emergency_state — fast single-doc fetch sorted by recency
        await _db.emergency_state.create_index(
            [("updated_at", -1)],
            name="idx_emergency_state_time", background=True,
        )

        # ── Auth indexes ──────────────────────────────────────────────
        # refresh_tokens: shared collection — must match staff backend indexes
        await _db.refresh_tokens.create_index(
            [("token", 1)], unique=True,
            name="idx_refresh_tokens_token", background=True,
        )
        await _db.refresh_tokens.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="idx_refresh_tokens_ttl", background=True,
        )
        await _db.refresh_tokens.create_index(
            [("user_id", 1)],
            name="idx_refresh_tokens_user_id", background=True,
        )

        logger.info("✓ Connected to MongoDB Atlas")
    except Exception as e:
        logger.error(f"✗ Failed to connect to MongoDB: {e}")
        raise


async def close_mongo_connection():
    """Close MongoDB connection."""
    global _db
    if _db is not None:
        try:
            # Use the public client reference for Motor database
            _db.client.close()
            logger.info("✓ MongoDB connection closed")
        except Exception as e:
            logger.warning(f"Failed while closing MongoDB connection: {e}")


def get_db():
    """Get MongoDB database instance."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongo() first.")
    return _db


def attach_db_to_app(app) -> None:
    """Attach the Motor database to app.state.db for auth dependency injection."""
    app.state.db = get_db()
