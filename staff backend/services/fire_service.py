# ============================================================
#  Emergency Backend · services/fire_service.py
#  Purpose: Receive InfernoGuard payload, store event, trigger alert
# ============================================================

import logging
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
from database import get_collection
from services.alert_service import create_auto_alert
from services.task_service import generate_tasks
from services.websocket_manager import manager
from services.gemini_service import format_alert_message

logger = logging.getLogger(__name__)

# MVP trigger rule: only HIGH or CRITICAL creates an alert
ALERT_TRIGGER_LEVELS = {"HIGH", "CRITICAL"}


async def _get_floor_name(floor_id: str) -> str:
    """Fetch floor name from DB for Gemini context. Falls back to floor_id."""
    try:
        col = get_collection("floors")
        doc = await col.find_one({"_id": ObjectId(floor_id)}, {"name": 1})
        return doc["name"] if doc else floor_id
    except Exception:
        return floor_id


async def handle_fire_input(payload: dict) -> dict:
    """
    1. Store fire_event in DB
    2. If risk HIGH/CRITICAL → create alert (deduplicated)
    3. Gemini formats the alert message
    4. Generate tasks (Gemini enriches each task sentence)
    5. Broadcast everything via WebSocket

    Extended fields (optional, non-breaking):
        source_room      : room_id if danger is localized to a specific room
        scope            : "floor" | "room"
        override_message : pre-formatted message (skips Gemini formatting)
    """
    col = get_collection("fire_events")

    # ── Optional room / zone context (non-breaking) ───────────────────────────
    source_room: Optional[str]  = payload.get("source_room")
    danger_zones: List[str]     = payload.get("danger_zones") or []
    scope: str                  = payload.get("scope", "floor")
    override_message: Optional[str] = payload.get("override_message")

    # Backward compat: if zones present but no explicit source_room, derive it
    if not source_room and danger_zones:
        source_room = danger_zones[0]

    event_doc = {
        "floor_id":       payload["floor_id"],
        "risk_level":     payload["risk_level"],
        "risk_score":     payload["risk_score"],
        "action":         payload["action"],
        "density_label":  payload["density_label"],
        "density_value":  payload["density_value"],
        "people_count":   payload["people_count"],
        "fire_conf":      payload["fire_conf"],
        "movement_score": payload["movement_score"],
        "source_room":    source_room,
        "scope":          scope,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }

    result = await col.insert_one(event_doc)
    fire_event_id = str(result.inserted_id)
    event_doc["id"] = fire_event_id
    event_doc.pop("_id", None)

    alert_created = False

    if payload["risk_level"] in ALERT_TRIGGER_LEVELS:
        # Fetch floor name for Gemini context
        floor_name = await _get_floor_name(payload["floor_id"])

        # Use override_message if provided (e.g. from danger_tracker),
        # otherwise let Gemini format a message
        if override_message:
            alert_message = override_message
        else:
            alert_message = await format_alert_message(
                floor_name=floor_name,
                risk_level=payload["risk_level"],
                action=payload["action"],
                people_count=payload["people_count"],
                fire_conf=payload["fire_conf"],
                density_label=payload["density_label"],
                source_room=source_room,
            )

        alert = await create_auto_alert(
            floor_id=payload["floor_id"],
            fire_event_id=fire_event_id,
            risk_level=payload["risk_level"],
            message=alert_message,
            source_room=source_room,
            danger_zones=danger_zones,
            scope=scope,
        )

        if alert:
            alert_created = True

            # Broadcast alert with full room context for guest/staff dashboards
            ws_payload = {
                **alert,
                "type":         "emergency",
                "floor_id":     payload["floor_id"],
                "danger_zones": danger_zones,
                "source_room":  source_room,
                "severity":     payload["risk_level"].lower(),
                "message":      alert_message,
            }
            await manager.broadcast("emergency", ws_payload)

            # Also broadcast legacy "alert" type for backward-compatible clients
            await manager.broadcast("alert", alert)

            # Generate + broadcast tasks (Gemini formats each sentence)
            tasks = await generate_tasks(
                alert_id=alert["id"],
                floor_id=payload["floor_id"],
                floor_name=floor_name,
                risk_level=payload["risk_level"],
                fire_conf=payload["fire_conf"],
                density_label=payload["density_label"],
                movement_score=payload["movement_score"],
                people_count=payload["people_count"],
                source_room=source_room,
            )
            for task in tasks:
                await manager.broadcast("task", task)

            logger.warning(
                f"Emergency triggered | floor={payload['floor_id']} "
                f"room={source_room or 'N/A'} level={payload['risk_level']} "
                f"scope={scope} alert_id={alert['id']}"
            )

    event_doc["alert_created"] = alert_created
    return event_doc

