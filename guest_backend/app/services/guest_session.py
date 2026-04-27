"""
Guest session management service.

Handles:
- Session creation and tracking
- Session state updates
- Location tracking
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from app.models.schemas import (
    GuestSession, GuestSessionCreate, GuestSessionResponse, SessionStatus
)
from app.core.database import get_db

logger = logging.getLogger(__name__)


class GuestSessionService:
    """Service for managing guest sessions."""

    def __init__(self, db):
        self.db = db
        self.collection = db.guest_sessions

    async def create_session(
        self,
        room_id: str,
        floor_id: str,
        phone_number: Optional[str] = None,
    ) -> GuestSessionResponse:
        """
        Create a new guest session.

        Handles DuplicateKeyError on the unique session_id index by
        regenerating a longer ID (collision probability: ~1 in 2^48).
        """
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        session_doc = {
            "session_id":   session_id,
            "room_id":      room_id,
            "floor_id":     floor_id,
            "phone_number": phone_number,
            "current_node": room_id,
            "status":       SessionStatus.ACTIVE.value,
            "created_at":   now,
            "updated_at":   now,
        }

        try:
            await self.collection.insert_one(session_doc)
        except DuplicateKeyError:
            # UUID collision — regenerate with more entropy
            session_id = f"sess_{uuid.uuid4().hex}"
            session_doc["session_id"] = session_id
            await self.collection.insert_one(session_doc)
            logger.warning(
                f"session_id collision on short ID — regenerated full UUID: {session_id}"
            )

        logger.info(f"Session created: {session_id} | room={room_id} floor={floor_id}")
        return GuestSessionResponse(
            session_id=session_id,
            floor_id=floor_id,
            room_id=room_id,
            current_node=room_id,
            status=SessionStatus.ACTIVE,
            created_at=now,
        )

    async def get_session(self, session_id: str) -> Optional[GuestSession]:
        """Retrieve a session by ID."""
        doc = await self.collection.find_one({"session_id": session_id})
        if doc:
            doc.pop("_id", None)
            return GuestSession(**doc)
        return None

    async def update_current_node(self, session_id: str, node_id: str) -> bool:
        """Update the guest's current location node."""
        result = await self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "current_node": node_id,
                    "updated_at":   datetime.now(timezone.utc),
                }
            },
        )
        # matched_count > 0 means session exists (even if node didn't change — idempotent)
        if result.matched_count > 0:
            logger.info("Session '%s' moved to node '%s'", session_id, node_id)
            return True
        logger.warning("update_current_node: session '%s' not found", session_id)
        return False


    async def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
    ) -> bool:
        """Update session status."""
        result = await self.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status":     status.value,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    async def mark_safe(self, session_id: str) -> bool:
        """Mark session as having reached safe zone."""
        return await self.update_session_status(session_id, SessionStatus.SAFE)

    async def list_active_sessions(self, floor_id: str) -> list:
        """List all active + evacuating sessions on a floor."""
        cursor = self.collection.find({
            "floor_id": floor_id,
            "status": {"$in": [SessionStatus.ACTIVE.value, SessionStatus.EVACUATING.value]},
        })
        sessions = []
        async for doc in cursor:
            doc.pop("_id", None)
            sessions.append(GuestSession(**doc))
        return sessions

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session (after timeout or completion)."""
        result = await self.collection.delete_one({"session_id": session_id})
        return result.deleted_count > 0


async def get_guest_session_service() -> GuestSessionService:
    """Dependency injection for guest session service."""
    db = get_db()
    return GuestSessionService(db)
