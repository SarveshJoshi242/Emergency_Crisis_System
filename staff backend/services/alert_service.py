# ============================================================
#  Emergency Backend · services/alert_service.py
#  Purpose: Alert CRUD with mandatory deduplication
# ============================================================

import logging
from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from database import get_collection

logger = logging.getLogger(__name__)


async def _sync_emergency_state(
    is_active: bool,
    floor_id: Optional[str] = None,
    risk_level: Optional[str] = None,
    blocked_nodes: Optional[List[str]] = None,
    affected_floors: Optional[List[str]] = None,
) -> None:
    """
    Write-through: keep emergency_state collection in sync with alerts.
    Guest backend reads this directly — no HTTP call needed.
    Non-fatal: exceptions are logged but do not break the alert flow.

    IMPORTANT: always stores timezone-aware UTC datetime objects, never strings.
    Uses replace_one upsert so there is exactly ONE document in this collection.
    """
    try:
        col = get_collection("emergency_state")
        doc = {
            "is_active": is_active,
            "emergency_type": risk_level,
            # FIXED: floor_id=None no longer pollutes affected_floors with ""
            "affected_floors": affected_floors or ([floor_id] if floor_id else []),
            "blocked_nodes": blocked_nodes or [],
            "safe_exits": [],
            "updated_at": datetime.now(timezone.utc),  # always a tz-aware datetime object
        }
        await col.replace_one({}, doc, upsert=True)
        logger.info(
            "emergency_state synced | active=%s floors=%s blocked=%s",
            is_active, doc["affected_floors"], doc["blocked_nodes"],
        )

        # Real-time broadcast to connected staff WebSocket clients
        try:
            from services.websocket_manager import manager
            await manager.broadcast("emergency_state", {
                "is_active": is_active,
                "emergency_type": risk_level,
                "affected_floors": doc["affected_floors"],
                "blocked_nodes": doc["blocked_nodes"],
                "updated_at": doc["updated_at"].isoformat(),
            })
        except Exception as ws_err:
            logger.warning("emergency_state WS broadcast failed (non-fatal): %s", ws_err)

    except Exception as e:
        logger.warning("emergency_state write-through failed (non-fatal): %s", e)


async def create_auto_alert(
    floor_id: str,
    fire_event_id: str,
    risk_level: str,
    message: Optional[str] = None,
    source_room: Optional[str] = None,
    danger_zones: Optional[List[str]] = None,
    scope: str = "floor",
) -> Optional[dict]:
    """
    Create an alert triggered by a fire event or AI danger detection.

    DEDUPLICATION: If an ACTIVE alert already exists for this fire_event_id,
    skip and return None — prevents duplicate task floods.

    Args:
        source_room: Optional room_id that is the source of danger.
        scope:       "floor" (whole floor) or "room" (specific room).
    """
    col = get_collection("alerts")

    existing_event = await col.find_one(
        {"fire_event_id": fire_event_id, "status": "ACTIVE"}
    )
    if existing_event:
        logger.debug("Alert for fire_event_id=%s already exists — skipping", fire_event_id)
        return None  # already handled
        
    # Deduplicate by room/floor to prevent duplicate active alerts if multiple sensors/AI detections trigger
    room_filter = {"source_room": source_room} if source_room else {}
    existing_alert = await col.find_one({
        "floor_id": floor_id,
        "status": "ACTIVE",
        **room_filter
    })
    if existing_alert:
        logger.debug("Active alert already exists for floor=%s room=%s — skipping", floor_id, source_room)
        return None

    location = f"Room {source_room}" if source_room else f"Floor {floor_id}"
    auto_message = message or f"Auto-alert: {risk_level} risk detected on {location}"
    blocked = danger_zones or ([source_room] if source_room else [])
    now = datetime.now(timezone.utc)

    doc = {
        "floor_id":      floor_id,
        "type":          "AUTO",
        "status":        "ACTIVE",
        "risk_level":    risk_level,
        "fire_event_id": fire_event_id,
        "message":       auto_message,
        "source_room":   source_room,
        "danger_zones":  danger_zones or [],
        "scope":         scope,
        "created_at":    now,  # stored as datetime object — NOT isoformat string
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    doc["created_at"] = now.isoformat()  # serialize for response only
    logger.info(
        "Alert created | id=%s floor=%s room=%s level=%s scope=%s",
        doc["id"], floor_id, source_room or "N/A", risk_level, scope,
    )

    # Write-through: update emergency_state so guest reads it directly (no HTTP)
    await _sync_emergency_state(
        is_active=True,
        floor_id=floor_id,
        risk_level=risk_level,
        blocked_nodes=blocked,
        affected_floors=[floor_id],
    )

    return doc


async def create_manual_alert(floor_id: str, message: Optional[str]) -> dict:
    """Staff-triggered manual alert."""
    col = get_collection("alerts")
    now = datetime.now(timezone.utc)
    doc = {
        "floor_id":      floor_id,
        "type":          "MANUAL",
        "status":        "ACTIVE",
        "risk_level":    None,
        "fire_event_id": None,
        "message":       message or "Manual alert triggered",
        "source_room":   None,
        "scope":         "floor",
        "created_at":    now,  # stored as datetime object
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    doc["created_at"] = now.isoformat()  # serialize for response only

    # Write-through for manual alerts
    await _sync_emergency_state(
        is_active=True,
        floor_id=floor_id,
        risk_level="MANUAL",
        affected_floors=[floor_id],
    )

    return doc


async def get_active_alerts() -> List[dict]:
    col = get_collection("alerts")
    docs = []
    async for doc in col.find({"status": "ACTIVE"}).sort("created_at", -1):
        doc["id"] = str(doc.pop("_id"))
        # Serialize datetime fields for JSON safety
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        docs.append(doc)
    return docs


async def resolve_alert(alert_id: str) -> bool:
    col = get_collection("alerts")
    try:
        oid = ObjectId(alert_id)
    except Exception:
        return False

    result = await col.update_one(
        {"_id": oid},
        {"$set": {"status": "RESOLVED", "resolved_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count != 1:
        return False

    active_alerts = await get_active_alerts()
    if not active_alerts:
        # All alerts resolved — clear emergency state
        await _sync_emergency_state(
            is_active=False,
            floor_id=None,   # FIXED: was "" which stored "" in affected_floors
            risk_level=None,
            blocked_nodes=[],
            affected_floors=[],
        )
        return True

    # Still have active alerts — recalculate state
    affected_floors = list({a["floor_id"] for a in active_alerts if a.get("floor_id")})
    blocked_nodes: List[str] = []
    for alert in active_alerts:
        blocked_nodes.extend(alert.get("danger_zones") or [])
        if alert.get("source_room"):
            blocked_nodes.append(alert["source_room"])

    await _sync_emergency_state(
        is_active=True,
        floor_id=affected_floors[0] if affected_floors else None,
        risk_level=active_alerts[0].get("risk_level") or "ACTIVE",
        blocked_nodes=list(dict.fromkeys(blocked_nodes)),  # deduplicate, preserve order
        affected_floors=affected_floors,
    )
    return True
