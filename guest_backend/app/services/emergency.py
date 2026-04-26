"""
Emergency state management service.

Primary path:  reads from db.emergency_state — written through by staff backend
               alert_service on every alert create/resolve (no HTTP needed).

Fallback chain:
  1. In-memory cache (trusted up to 60s)      — survives DB hiccup
  2. Staff bridge HTTP call                    — survives local DB outage
  3. Stale in-memory cache (any age)           — last resort
  4. Fail-safe default: is_active=True         — NEVER assume no emergency

SAFE DEFAULT IS is_active=True.
During a real emergency + DB outage, returning False would route guests
into danger. Returning True causes inconvenience at worst.
"""
import time
import logging
from app.core.database import get_db
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── In-memory last-known-good cache ──────────────────────────────────────────
_last_known_state: Optional[Dict[str, Any]] = None
_last_known_state_ts: float = 0.0
_CACHE_TRUST_SECONDS: float = 60.0   # trust cached state for up to 60s


def _update_cache(state: Dict[str, Any]) -> None:
    global _last_known_state, _last_known_state_ts
    _last_known_state = state
    _last_known_state_ts = time.monotonic()


def _cached_state_age() -> float:
    return time.monotonic() - _last_known_state_ts


# ── Service class ─────────────────────────────────────────────────────────────

class EmergencyService:
    """Service for managing emergency state (read-through from shared DB)."""

    def __init__(self, db):
        self.db = db
        self.emergency_collection = db.emergency_state

    async def get_current_emergency_state(self) -> Dict[str, Any]:
        """
        Retrieve the current emergency state.

        Resolution order:
          1. db.emergency_state (written by staff alert_service on every change)
          2. In-memory cache (< 60s old)
          3. Staff bridge HTTP fallback
          4. Stale in-memory cache (any age) — better than wrong default
          5. Fail-safe: {is_active: True} — NEVER silently hide an emergency
        """
        # ── 1. Primary: direct DB read ────────────────────────────────────────
        try:
            state_doc = await self.emergency_collection.find_one(
                {},
                sort=[("updated_at", -1)],
                max_time_ms=2000,
            )
            if state_doc:
                state_doc.pop("_id", None)
                _update_cache(state_doc)
                logger.debug(
                    f"Emergency state from DB: active={state_doc.get('is_active')}"
                )
                return state_doc
        except Exception as e:
            logger.warning(f"DB read for emergency_state failed: {e}")

        # ── 2. In-memory cache (fresh) ────────────────────────────────────────
        if _last_known_state is not None:
            age = _cached_state_age()
            if age < _CACHE_TRUST_SECONDS:
                logger.warning(
                    f"DB unavailable — using in-memory cache "
                    f"(age={age:.0f}s, active={_last_known_state.get('is_active')})"
                )
                return _last_known_state

        # ── 3. Staff bridge HTTP fallback ─────────────────────────────────────
        try:
            from app.services.integration import get_integration_service
            integration = get_integration_service()
            bridge_state = await integration.get_emergency_state()
            if bridge_state:
                logger.info("Emergency state retrieved from staff bridge HTTP fallback")
                await self._cache_state(bridge_state)
                _update_cache(bridge_state)
                return bridge_state
        except Exception as e:
            logger.error(f"Staff bridge HTTP fallback failed: {e}")

        # ── 4. Stale in-memory cache — any age ───────────────────────────────
        if _last_known_state is not None:
            age = _cached_state_age()
            logger.error(
                f"All emergency state sources failed. Using stale cache "
                f"(age={age:.0f}s, active={_last_known_state.get('is_active')}). "
                "Manual check required."
            )
            return _last_known_state

        # ── 5. Absolute fail-safe: assume emergency is ACTIVE ─────────────────
        logger.critical(
            "No emergency state available from any source. "
            "Defaulting to is_active=True for guest safety. "
            "Check MongoDB and staff backend connectivity immediately."
        )
        return {
            "is_active": True,
            "emergency_type": "UNKNOWN",
            "affected_floors": [],
            "blocked_nodes": [],
            "safe_exits": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _cache_state(self, state: Dict[str, Any]) -> None:
        """Write HTTP-fetched state into local emergency_state collection."""
        try:
            state_copy = {k: v for k, v in state.items() if k != "_id"}
            await self.emergency_collection.replace_one({}, state_copy, upsert=True)
        except Exception as e:
            logger.warning(f"Failed to cache emergency state locally: {e}")

    async def get_blocked_nodes(self, floor_id: str) -> List[str]:
        """
        Get nodes blocked due to emergency on the given floor.
        Used by navigation service to avoid dangerous regions.
        """
        state = await self.get_current_emergency_state()
        if not state or not state.get("is_active"):
            return []

        affected = state.get("affected_floors", [])
        # If affected_floors is empty or contains this floor, return blocked nodes
        if not affected or floor_id in affected:
            return state.get("blocked_nodes", [])
        return []

    async def get_safe_exits(self, floor_id: str) -> List[str]:
        """Get recommended safe exits for a floor."""
        state = await self.get_current_emergency_state()
        if state:
            return state.get("safe_exits", [])
        return []

    async def is_emergency_active(self) -> bool:
        """Quick check: is there an active emergency?"""
        state = await self.get_current_emergency_state()
        return bool(state and state.get("is_active"))


async def get_emergency_service() -> EmergencyService:
    """Dependency injection for emergency service."""
    db = get_db()
    return EmergencyService(db)
