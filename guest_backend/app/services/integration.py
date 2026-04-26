"""
Staff backend integration service.

Handles REST API calls to the staff backend's guest bridge endpoints.
All endpoint URLs are under /guest-api/ prefix on the staff backend.

URL Map (old → new):
  GET  /staff/building/room/{id}           → GET  /guest-api/rooms/{id}/floor
  GET  /staff/building/floor/{id}/graph    → GET  /guest-api/floors/{id}/graph
  GET  /staff/emergency/current-state      → GET  /guest-api/emergency/state
  POST /staff/emergency/guest-help-request → POST /guest-api/help-requests
  POST /staff/emergency/guest-safe-conf..  → POST /guest-api/safe-confirmations
  GET  /staff/emergency/notifications      → GET  /guest-api/notifications
  GET  /health                             → GET  /  (staff root health check)

Timeout strategy:
  connect=2s  — fail immediately if host is unreachable
  read=3s     — fast fail on slow response; DB fallback takes over
  write=2s
  pool=2s
"""
import logging
import httpx
from typing import Optional, Dict, Any, List

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(
    connect=2.0,
    read=float(settings.STAFF_BACKEND_TIMEOUT),
    write=2.0,
    pool=2.0,
)


class StaffBackendIntegrationService:
    """Service for integrating with staff backend via REST API (guest bridge endpoints)."""

    def __init__(self):
        self.base_url = settings.STAFF_BACKEND_URL.rstrip("/")

    async def get_room_floor_mapping(self, room_id: str) -> Optional[str]:
        """
        Get the floor ID for a given room from staff backend.
        Calls: GET /guest-api/rooms/{room_id}/floor
        Returns floor_slug ("floor_1") if available, else ObjectId string, else None.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/guest-api/rooms/{room_id}/floor"
                )
                if response.status_code == 200:
                    data = response.json()
                    # Prefer human-readable slug (e.g. "floor_1") over raw ObjectId
                    # floor_slug = doc.get("floor_id") field set by staff when creating floor
                    floor_id = data.get("floor_slug") or data.get("floor_id")
                    logger.info(f"Room '{room_id}' → floor '{floor_id}'")
                    return floor_id
                logger.warning(
                    f"Staff bridge returned {response.status_code} for room '{room_id}'"
                )
        except httpx.ConnectError:
            logger.warning(
                f"Staff backend unreachable (ConnectError) for room lookup '{room_id}'. "
                "Will fall back to local DB."
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Staff backend timed out for room lookup '{room_id}'. "
                "Will fall back to local DB."
            )
        except Exception as e:
            logger.error(f"Unexpected error in get_room_floor_mapping: {e}")
        return None


    async def sync_floor_plan(self, floor_id: str) -> Optional[Dict[str, Any]]:
        """
        Sync floor plan/graph from staff backend.

        NOTE: Only used as a last-resort fallback when the shared DB has no
        floor doc. Both backends share emergency_db so this should rarely
        be needed in production.

        Calls: GET /guest-api/floors/{floor_id}/graph
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/guest-api/floors/{floor_id}/graph"
                )
                if response.status_code == 200:
                    graph_data = response.json()
                    logger.info(f"Floor plan for '{floor_id}' fetched from staff bridge")
                    return graph_data
                logger.warning(
                    f"Staff bridge returned {response.status_code} for floor '{floor_id}'"
                )
        except httpx.ConnectError:
            logger.warning(
                f"Staff backend unreachable (ConnectError) for floor sync '{floor_id}'."
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Staff backend timed out for floor sync '{floor_id}'."
            )
        except Exception as e:
            logger.error(f"Unexpected error in sync_floor_plan: {e}")
        return None

    async def get_emergency_state(self) -> Optional[Dict[str, Any]]:
        """
        Get current emergency state from staff backend (HTTP fallback).

        NOTE: EmergencyService reads db.emergency_state directly in primary path.
        This is only called when the DB read fails.

        Calls: GET /guest-api/emergency/state
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/guest-api/emergency/state"
                )
                if response.status_code == 200:
                    state = response.json()
                    logger.info(
                        f"Emergency state from staff bridge: active={state.get('is_active')}"
                    )
                    return state
                logger.warning(
                    f"Staff bridge returned {response.status_code} for emergency state"
                )
        except httpx.ConnectError:
            logger.warning("Staff backend unreachable (ConnectError) for emergency state.")
        except httpx.TimeoutException:
            logger.warning("Staff backend timed out for emergency state.")
        except Exception as e:
            logger.error(f"Unexpected error in get_emergency_state: {e}")
        return None

    async def send_help_request(
        self,
        session_id: str,
        current_node: str,
        issue: str,
        floor_id: Optional[str] = None,
    ) -> bool:
        """
        Send a help request to the staff backend.
        Calls: POST /guest-api/help-requests
        Returns True only if staff backend acknowledged the request.
        """
        try:
            payload = {
                "session_id":   session_id,
                "current_node": current_node,
                "issue":        issue,
                "floor_id":     floor_id,
            }
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/guest-api/help-requests",
                    json=payload,
                )
                if response.status_code in (200, 201):
                    logger.info(f"Help request sent for session '{session_id}'")
                    return True
                logger.warning(
                    f"Staff bridge returned {response.status_code} for help request "
                    f"(session={session_id})"
                )
        except httpx.ConnectError:
            logger.warning(
                f"Staff backend unreachable — help request for session '{session_id}' "
                "stored locally only."
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Staff backend timed out — help request for session '{session_id}' "
                "stored locally only."
            )
        except Exception as e:
            logger.error(f"Unexpected error in send_help_request: {e}")
        return False

    async def notify_safe_reached(
        self,
        session_id: str,
        final_location: str,
    ) -> bool:
        """
        Notify staff backend that guest reached safe zone.
        Calls: POST /guest-api/safe-confirmations
        """
        try:
            payload = {
                "session_id":     session_id,
                "final_location": final_location,
            }
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/guest-api/safe-confirmations",
                    json=payload,
                )
                if response.status_code in (200, 201):
                    logger.info(
                        f"Safe confirmation sent for session '{session_id}' "
                        f"at '{final_location}'"
                    )
                    return True
                logger.warning(
                    f"Staff bridge returned {response.status_code} for safe confirmation"
                )
        except httpx.ConnectError:
            logger.warning(
                f"Staff backend unreachable — safe confirmation for '{session_id}' not forwarded."
            )
        except httpx.TimeoutException:
            logger.warning(
                f"Staff backend timed out for safe confirmation '{session_id}'."
            )
        except Exception as e:
            logger.error(f"Unexpected error in notify_safe_reached: {e}")
        return False

    async def get_notifications(self, floor_id: str) -> List[Dict[str, Any]]:
        """
        Get current notifications/alerts from staff backend.
        Calls: GET /guest-api/notifications?floor_id={floor_id}
        Returns a merged list of active alert + message dicts.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/guest-api/notifications",
                    params={"floor_id": floor_id},
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("alerts", []) + data.get("messages", [])
                logger.warning(
                    f"Staff bridge returned {response.status_code} for notifications"
                )
        except httpx.ConnectError:
            logger.warning("Staff backend unreachable for notifications — returning empty list.")
        except httpx.TimeoutException:
            logger.warning("Staff backend timed out for notifications — returning empty list.")
        except Exception as e:
            logger.error(f"Unexpected error in get_notifications: {e}")
        return []

    async def health_check(self) -> bool:
        """Check if staff backend is accessible."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=2.0, read=2.0)) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Staff backend health check failed: {e}")
            return False


# Singleton instance
_integration_service: Optional[StaffBackendIntegrationService] = None


def get_integration_service() -> StaffBackendIntegrationService:
    """Get or create singleton integration service."""
    global _integration_service
    if _integration_service is None:
        _integration_service = StaffBackendIntegrationService()
    return _integration_service
