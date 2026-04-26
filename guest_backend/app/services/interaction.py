"""
Guest interaction and logging service.

Handles:
- Guest action logging
- Step updates, reroutes, help requests
- Activity tracking
"""
from motor.motor_asyncio import AsyncIOMotorClient
from app.models.schemas import GuestLog, ActionType
from app.core.database import get_db
from datetime import datetime, timezone
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class InteractionService:
    """Service for managing guest interactions and logs."""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.guest_logs
    
    async def log_action(
        self,
        session_id: str,
        step: int,
        action: ActionType,
        node_id: Optional[str] = None,
        details: Optional[str] = None
    ) -> bool:
        """
        Log a guest action (completed step, reroute, help request).
        
        Args:
            session_id: Guest session ID
            step: Step number in the route
            action: Type of action (completed, reroute, help)
            node_id: Associated node ID
            details: Additional details
        
        Returns:
            True if log was recorded
        """
        log_doc = {
            "session_id": session_id,
            "step": step,
            "action": action.value,
            "node_id": node_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc)
        }
        
        result = await self.collection.insert_one(log_doc)
        logger.info(f"Logged {action.value} for session {session_id} at step {step}")
        return result.inserted_id is not None
    
    async def get_session_log(self, session_id: str) -> List[GuestLog]:
        """Retrieve all logs for a session."""
        cursor = self.collection.find({"session_id": session_id}).sort("timestamp", 1)
        logs = []
        async for doc in cursor:
            doc.pop("_id", None)
            logs.append(GuestLog(**doc))
        return logs
    
    async def count_action_type(self, session_id: str, action_type: ActionType) -> int:
        """Count how many times a specific action occurred in a session."""
        count = await self.collection.count_documents({
            "session_id": session_id,
            "action": action_type.value
        })
        return count
    
    async def get_help_requests(self, session_id: str) -> List[GuestLog]:
        """Get all help requests from a session."""
        cursor = self.collection.find({
            "session_id": session_id,
            "action": ActionType.HELP.value
        }).sort("timestamp", 1)
        
        requests = []
        async for doc in cursor:
            doc.pop("_id", None)
            requests.append(GuestLog(**doc))
        return requests
    
    async def delete_session_logs(self, session_id: str) -> int:
        """Delete all logs for a session (cleanup)."""
        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count


async def get_interaction_service() -> InteractionService:
    """Dependency injection for interaction service."""
    db = get_db()
    return InteractionService(db)
