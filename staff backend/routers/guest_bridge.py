# ============================================================
#  Emergency Backend · routers/guest_bridge.py
#  Purpose: Bridge endpoints consumed by the guest backend.
#           All routes live under /guest-api/ prefix.
#
#  Guest backend calls these instead of non-existent endpoints.
#  Staff dashboard also uses some of these (help-requests, messages).
#
#  Endpoints:
#    GET  /guest-api/floors/{floor_id}/graph      — floor graph for pathfinding
#    GET  /guest-api/rooms/{room_id}/floor         — room → floor mapping
#    GET  /guest-api/emergency/state               — live emergency state
#    POST /guest-api/help-requests                 — guest submits help
#    GET  /guest-api/help-requests                 — staff reads pending
#    PATCH /guest-api/help-requests/{id}/resolve   — staff resolves
#    POST /guest-api/messages/broadcast            — staff broadcasts message
#    GET  /guest-api/notifications                 — guest polls alerts+msgs
#    POST /guest-api/safe-confirmations            — guest reached safe zone
# ============================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database import get_collection
from services.alert_service import get_active_alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guest-api", tags=["Guest Bridge"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    """Pop _id, set id as string, and serialize datetime fields."""
    doc["id"] = str(doc.pop("_id"))
    # Iterate over a snapshot — cannot mutate dict while iterating it
    for key, val in list(doc.items()):
        if isinstance(val, datetime):
            doc[key] = val.isoformat()
    return doc


# ── 1. Floor graph (C5 fix) ───────────────────────────────────────────────────

@router.get(
    "/floors/{floor_id}/graph",
    summary="Get floor graph for guest pathfinding",
    description=(
        "Accepts ObjectId string, floor slug (floor_id field), or floor name. "
        "Returns nodes and edges in the format expected by the guest backend."
    ),
)
async def get_floor_graph_for_guest(floor_id: str):
    col = get_collection("floors")
    doc = None

    # Try ObjectId first
    if ObjectId.is_valid(floor_id):
        doc = await col.find_one({"_id": ObjectId(floor_id)})

    # Try slug field
    if not doc:
        doc = await col.find_one({"floor_id": floor_id})

    # Try name field as last resort
    if not doc:
        doc = await col.find_one({"name": floor_id})

    if not doc:
        raise HTTPException(status_code=404, detail=f"Floor '{floor_id}' not found")

    graph = doc.get("graph") or {"nodes": [], "edges": []}
    return {
        "floor_id": str(doc["_id"]),
        "name": doc.get("name"),
        "floor_slug": doc.get("floor_id"),
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
        "updated_at": doc.get("updated_at", doc.get("created_at")),
    }


# ── 2. Room → Floor mapping (C6 fix) ──────────────────────────────────────────

@router.get(
    "/rooms/{room_id}/floor",
    summary="Get which floor a room belongs to",
    description="Searches inside floor graphs. Returns floor_id (ObjectId string) and name.",
)
async def get_floor_for_room(room_id: str):
    col = get_collection("floors")
    # Sort by created_at descending — newest floor wins when room_id appears in
    # multiple floors (e.g. stub graph applied to old AND new floors).
    # Prefer floors that have an explicit floor_id slug over raw ObjectId floors.
    cursor = col.find(
        {"graph.nodes": {"$elemMatch": {"id": room_id, "type": "room"}}}
    ).sort("created_at", -1)

    best_doc = None
    async for doc in cursor:
        if not best_doc:
            best_doc = doc  # first (newest) result is fallback
        if doc.get("floor_id"):  # prefer one with an explicit slug like "floor_1"
            best_doc = doc
            break

    if not best_doc:
        # Type-agnostic fallback: match any node with this id (no type filter)
        best_doc = await col.find_one({"graph.nodes.id": room_id})

    if not best_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Room '{room_id}' not found in any floor graph"
        )
    return {
        "floor_id": str(best_doc["_id"]),
        "floor_slug": best_doc.get("floor_id"),  # human slug e.g. "floor_1"
        "name":       best_doc.get("name"),
    }



# ── 3. Emergency state (C3 fix) ───────────────────────────────────────────────

@router.get(
    "/emergency/state",
    summary="Get current emergency state (derived from active alerts)",
    description=(
        "Primary source of truth for guest emergency status. "
        "Reads from emergency_state collection (written-through by alert_service). "
        "Falls back to aggregating active alerts if emergency_state is absent."
    ),
)
async def get_emergency_state_for_guest():
    # Primary: read write-through doc (updated on every alert create/resolve)
    state_col = get_collection("emergency_state")
    state_doc = await state_col.find_one({}, sort=[("updated_at", -1)])

    if state_doc:
        state_doc.pop("_id", None)
        # Ensure updated_at is always a serializable ISO string
        if isinstance(state_doc.get("updated_at"), datetime):
            state_doc["updated_at"] = state_doc["updated_at"].isoformat()
        return state_doc

    # Fallback: aggregate active alerts
    alerts = await get_active_alerts()
    if not alerts:
        return {
            "is_active": False,
            "emergency_type": None,
            "affected_floors": [],
            "blocked_nodes": [],
            "safe_exits": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    affected_floors = list({a["floor_id"] for a in alerts})
    danger_zones: List[str] = []
    for a in alerts:
        danger_zones.extend(a.get("danger_zones") or [])
        if a.get("source_room"):
            danger_zones.append(a["source_room"])

    latest = alerts[0]
    return {
        "is_active": True,
        "emergency_type": latest.get("risk_level", "UNKNOWN"),
        "affected_floors": affected_floors,
        "blocked_nodes": list(set(danger_zones)),
        "safe_exits": [],
        "updated_at": latest.get("created_at"),
    }


# ── 4. Help requests — guest writes, staff reads (C4 fix, S6 fix) ─────────────

class HelpRequestPayload(BaseModel):
    session_id: str
    current_node: str
    issue: str
    floor_id: Optional[str] = None


@router.post(
    "/help-requests",
    status_code=201,
    summary="Guest submits a help request",
)
async def receive_help_request(body: HelpRequestPayload):
    col = get_collection("help_requests")
    now = datetime.now(timezone.utc)

    # Idempotency: if a pending request from this session already exists, return it
    result = await col.update_one(
        {"session_id": body.session_id, "status": "pending"},
        {
            "$setOnInsert": {
                "session_id":   body.session_id,
                "current_node": body.current_node,
                "issue":        body.issue,
                "floor_id":     body.floor_id,
                "status":       "pending",
                "created_at":   now,
                "resolved_at":  None,
                "resolved_by":  None,
            }
        },
        upsert=True,
    )

    if result.upserted_id is not None:
        doc = {
            "id":           str(result.upserted_id),
            "session_id":   body.session_id,
            "current_node": body.current_node,
            "issue":        body.issue,
            "floor_id":     body.floor_id,
            "status":       "pending",
            "created_at":   now.isoformat(),
            "resolved_at":  None,
            "resolved_by":  None,
        }
        logger.info("Help request created | session=%s node=%s floor=%s",
                    body.session_id, body.current_node, body.floor_id)
    else:
        existing = await col.find_one({"session_id": body.session_id, "status": "pending"})
        if existing is None:
            # Race condition: matched filter but doc vanished — force a fresh insert
            insert_result = await col.insert_one({
                "session_id":   body.session_id,
                "current_node": body.current_node,
                "issue":        body.issue,
                "floor_id":     body.floor_id,
                "status":       "pending",
                "created_at":   now,
                "resolved_at":  None,
                "resolved_by":  None,
            })
            doc = {
                "id":           str(insert_result.inserted_id),
                "session_id":   body.session_id,
                "current_node": body.current_node,
                "issue":        body.issue,
                "floor_id":     body.floor_id,
                "status":       "pending",
                "created_at":   now.isoformat(),
                "resolved_at":  None,
                "resolved_by":  None,
            }
            logger.info("Help request force-inserted (race recovery) | session=%s", body.session_id)
        else:
            doc = _serialize(existing)
            logger.info("Help request already pending | session=%s", body.session_id)

    # Broadcast to staff WebSocket clients for real-time visibility
    try:
        from services.websocket_manager import manager
        await manager.broadcast("help_request", doc)
    except Exception as e:
        logger.warning(f"WebSocket broadcast for help_request failed (non-fatal): {e}")

    return doc



@router.get(
    "/help-requests",
    summary="Staff: list help requests (filter by floor_id and/or status)",
)
async def list_help_requests(
    floor_id: Optional[str] = Query(None, description="Filter by floor_id. Leave blank for all floors."),
    status: Optional[str] = Query(None, description="Filter by status (pending/resolved). Leave blank for ALL."),
):
    col = get_collection("help_requests")
    query: dict = {}
    if status:
        query["status"] = status
    if floor_id:
        query["floor_id"] = floor_id

    docs: List[dict] = []
    async for doc in col.find(query).sort("created_at", -1):
        docs.append(_serialize(doc))
    return docs



@router.patch(
    "/help-requests/{request_id}/resolve",
    summary="Staff: resolve a help request",
)
async def resolve_help_request(
    request_id: str,
    resolved_by: Optional[str] = Query(None),
):
    try:
        oid = ObjectId(request_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid request_id format")

    col = get_collection("help_requests")
    from pymongo import ReturnDocument
    updated_doc = await col.find_one_and_update(
        {"_id": oid},
        {
            "$set": {
                "status":      "resolved",
                "resolved_at": datetime.now(timezone.utc),
                "resolved_by": resolved_by,
            }
        },
        return_document=ReturnDocument.AFTER
    )
    if not updated_doc:
        raise HTTPException(status_code=404, detail="Help request not found or already resolved")

    # Real-time broadcast so both staff and guest receive instant update
    try:
        from services.websocket_manager import manager
        await manager.broadcast("help_resolved", {
            "request_id": request_id,
            "session_id": updated_doc.get("session_id"),
            "resolved_by": resolved_by,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as ws_err:
        logger.warning("help_resolved WS broadcast failed (non-fatal): %s", ws_err)

    return {"id": request_id, "status": "resolved"}


# ── 5. Broadcast messages — staff writes, guest reads (S7 fix) ────────────────

class BroadcastMessagePayload(BaseModel):
    message: str
    priority: Literal["info", "warning", "critical"] = "info"
    floor_id: Optional[str] = None  # None = all floors


@router.post(
    "/messages/broadcast",
    status_code=201,
    summary="Staff: broadcast a message to guests",
)
async def broadcast_message(body: BroadcastMessagePayload):
    col = get_collection("messages")
    doc = {
        "type":       "broadcast",
        "message":    body.message,
        "priority":   body.priority,
        "floor_id":   body.floor_id,
        "status":     "active",
        "created_at": datetime.now(timezone.utc),
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    logger.info(f"Broadcast message created | priority={body.priority} floor={body.floor_id or 'ALL'}")

    # Broadcast over WebSocket for connected clients
    try:
        from services.websocket_manager import manager
        await manager.broadcast("broadcast_message", doc)
    except Exception as e:
        logger.warning(f"WebSocket broadcast for message failed (non-fatal): {e}")

    return doc


# ── 6. Notifications — merged alerts + messages (C1 fix) ─────────────────────

@router.get(
    "/notifications",
    summary="Guest: poll for alerts and broadcast messages",
    description=(
        "Returns active alerts and active broadcast messages. "
        "Optionally filtered by floor_id. "
        "Messages with floor_id=null are returned for all floors."
    ),
)
async def get_notifications(floor_id: Optional[str] = Query(None)):
    # Active alerts
    alerts = await get_active_alerts()
    if floor_id:
        alerts = [a for a in alerts if a.get("floor_id") == floor_id]

    # Active broadcast messages (floor-specific + global)
    msg_col = get_collection("messages")
    msg_query: dict = {"type": "broadcast", "status": "active"}
    if floor_id:
        msg_query = {
            **msg_query,
            "$or": [{"floor_id": floor_id}, {"floor_id": None}],
        }

    messages: List[dict] = []
    async for msg in msg_col.find(msg_query).sort("created_at", -1).limit(20):
        messages.append(_serialize(msg))

    return {
        "alerts":   alerts,
        "messages": messages,
    }


# ── 7. Safe zone confirmation ─────────────────────────────────────────────────

class SafeConfirmPayload(BaseModel):
    session_id: str
    final_location: str


@router.post(
    "/safe-confirmations",
    summary="Guest: confirm they reached the safe zone",
)
async def receive_safe_confirmation(body: SafeConfirmPayload):
    col = get_collection("guest_sessions")
    now = datetime.now(timezone.utc)
    await col.update_one(
        {"session_id": body.session_id},
        {
            "$set": {
                "status":     "safe",
                "updated_at": now,
            }
        },
        upsert=True,
    )
    logger.info("Safe confirmation | session=%s location=%s", body.session_id, body.final_location)

    # Real-time broadcast so staff headcount dashboards update
    try:
        from services.websocket_manager import manager
        await manager.broadcast("safe_confirmation", {
            "session_id": body.session_id,
            "final_location": body.final_location,
            "timestamp": now.isoformat(),
        })
    except Exception as ws_err:
        logger.warning("safe_confirmation WS broadcast failed (non-fatal): %s", ws_err)

    return {"status": "ok", "session_id": body.session_id}


# ── 8. Guest sessions — staff headcount (bonus) ────────────────────────────────

@router.get(
    "/sessions",
    summary="Staff: list active guest sessions per floor (headcount)",
)
async def list_guest_sessions(
    floor_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    col = get_collection("guest_sessions")
    query: dict = {}
    if floor_id:
        query["floor_id"] = floor_id
    if status:
        query["status"] = status

    docs: List[dict] = []
    async for doc in col.find(query).sort("created_at", -1):
        doc.pop("_id", None)
        docs.append(doc)
    return docs
