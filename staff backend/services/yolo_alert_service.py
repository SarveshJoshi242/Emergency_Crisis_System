# ============================================================
#  Emergency Backend · services/yolo_alert_service.py
#  Purpose: CRUD + cooldown + dedup + state machine for
#           AI fire detection alerts from the YOLO Room Service.
#
#  State machine:
#    pending → confirmed   (staff confirms or auto-trigger)
#    pending → dismissed   (staff dismisses)
#
#  Safety controls:
#    • 30s cooldown per room after last alert
#    • Only one pending alert per room at a time
#    • Confirm action reuses existing fire_service pipeline
# ============================================================

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from bson import ObjectId

from database import get_collection

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

COOLDOWN_SECONDS = 30  # seconds between alerts for the same room


# ── Room → Floor resolution ──────────────────────────────────────────────────

async def _resolve_floor_id(room_id: str) -> Optional[str]:
    """
    Look up which floor a room belongs to by searching floor graphs.
    Returns the floor document's ObjectId as a string, or None.
    """
    col = get_collection("floors")

    # Prefer floors with an explicit slug
    cursor = col.find(
        {"graph.nodes": {"$elemMatch": {"id": room_id}}}
    ).sort("created_at", -1)

    best = None
    async for doc in cursor:
        if not best:
            best = doc
        if doc.get("floor_id"):  # prefer slug-based floor
            best = doc
            break

    return str(best["_id"]) if best else None


# ── Cooldown check ────────────────────────────────────────────────────────────

async def _is_cooldown_active(room_id: str) -> tuple[bool, float]:
    """
    Check if a cooldown is active for a room.
    Returns (is_active, remaining_seconds).
    """
    col = get_collection("ai_fire_alerts")
    last_alert = await col.find_one(
        {"room_id": room_id},
        sort=[("created_at", -1)],
    )
    if not last_alert:
        return False, 0.0

    created = last_alert["created_at"]
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    # MongoDB may return naive datetimes — normalize to UTC-aware
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - created).total_seconds()
    if elapsed < COOLDOWN_SECONDS:
        return True, round(COOLDOWN_SECONDS - elapsed, 1)
    return False, 0.0


# ── Create fire detection alert (medium risk — staff review) ──────────────────

async def create_fire_detection_alert(
    room_id: str,
    risk: str,
    confidence: float,
    source: str = "yolo",
    floor_id: Optional[str] = None,
) -> dict:
    """
    Store a medium-risk AI fire detection alert for staff review.

    Enforces:
    - 30s cooldown per room
    - Only one pending alert per room at a time

    Returns:
        Alert dict on success.

    Raises:
        ValueError with descriptive message on cooldown or dedup rejection.
    """
    col = get_collection("ai_fire_alerts")

    # ── Resolve floor_id if not provided ──────────────────────────────────────
    if not floor_id:
        floor_id = await _resolve_floor_id(room_id)
        if not floor_id:
            raise ValueError(f"Room '{room_id}' not found in any floor graph")

    # ── Cooldown check ────────────────────────────────────────────────────────
    is_cooling, remaining = await _is_cooldown_active(room_id)
    if is_cooling:
        raise ValueError(
            f"Cooldown active for {room_id}. {remaining}s remaining."
        )

    # ── Dedup: reject if pending alert already exists ─────────────────────────
    existing = await col.find_one({"room_id": room_id, "state": "pending"})
    if existing:
        raise ValueError(
            f"Pending alert already exists for {room_id}."
        )

    # ── Store alert ───────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    doc = {
        "room_id":     room_id,
        "floor_id":    floor_id,
        "risk":        risk,
        "confidence":  round(confidence, 4),
        "source":      source,
        "state":       "pending",
        "created_at":  now,
        "resolved_at": None,
        "resolved_by": None,
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    doc["created_at"] = now.isoformat()

    logger.info(
        "AI fire alert created | id=%s room=%s floor=%s risk=%s conf=%.3f",
        doc["id"], room_id, floor_id, risk, confidence,
    )
    return doc


# ── Create auto-trigger alert (high/critical — automatic evacuation) ─────────

async def create_auto_trigger(
    room_id: str,
    risk: str,
    confidence: float,
    triggered_by: str = "model",
    floor_id: Optional[str] = None,
) -> dict:
    """
    Store a high/critical AI fire alert as auto-confirmed and trigger
    evacuation via the existing fire_service pipeline.

    Enforces:
    - 30s cooldown per room

    Returns dict with alert info + evacuation result.
    """
    from services.fire_service import handle_fire_input

    col = get_collection("ai_fire_alerts")

    # ── Resolve floor_id ──────────────────────────────────────────────────────
    if not floor_id:
        floor_id = await _resolve_floor_id(room_id)
        if not floor_id:
            raise ValueError(f"Room '{room_id}' not found in any floor graph")

    # ── Cooldown check ────────────────────────────────────────────────────────
    is_cooling, remaining = await _is_cooldown_active(room_id)
    if is_cooling:
        raise ValueError(
            f"Cooldown active for {room_id}. {remaining}s remaining."
        )

    # ── Store alert as confirmed (auto) ───────────────────────────────────────
    now = datetime.now(timezone.utc)
    doc = {
        "room_id":      room_id,
        "floor_id":     floor_id,
        "risk":         risk,
        "confidence":   round(confidence, 4),
        "source":       "yolo",
        "state":        "confirmed",
        "triggered_by": triggered_by,
        "created_at":   now,
        "resolved_at":  now,
        "resolved_by":  triggered_by,
    }
    result = await col.insert_one(doc)
    ai_alert_id = str(result.inserted_id)

    logger.warning(
        "Auto-trigger alert | id=%s room=%s floor=%s risk=%s conf=%.3f",
        ai_alert_id, room_id, floor_id, risk, confidence,
    )

    # ── Trigger evacuation via existing fire_service pipeline ──────────────────
    message = (
        f"🚨 {risk.upper()} danger auto-detected in Room {room_id} "
        f"(confidence: {confidence:.0%}). "
        f"Immediate evacuation required. Avoid Room {room_id}."
    )

    synthetic_payload = {
        "floor_id":         floor_id,
        "risk_level":       risk.upper(),
        "risk_score":       round(confidence * 100, 2),
        "action":           "EVACUATE",
        "density_label":    "HIGH",
        "density_value":    0.9,
        "people_count":     0,
        "fire_conf":        confidence,
        "movement_score":   0.7,
        "source_room":      room_id,
        "danger_zones":     [room_id],
        "scope":            "floor",
        "override_message": message,
    }

    fire_result = await handle_fire_input(synthetic_payload)

    return {
        "status":          "evacuation_triggered",
        "room_id":         room_id,
        "floor_id":        floor_id,
        "risk":            risk,
        "confidence":      confidence,
        "alert_created":   fire_result.get("alert_created", False),
        "ai_alert_id":     ai_alert_id,
        "message":         message,
    }


# ── Get pending AI alerts ─────────────────────────────────────────────────────

async def get_pending_alerts() -> List[dict]:
    """Return all AI fire alerts with state='pending', newest first."""
    col = get_collection("ai_fire_alerts")
    docs = []
    async for doc in col.find({"state": "pending"}).sort("created_at", -1):
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        if isinstance(doc.get("resolved_at"), datetime):
            doc["resolved_at"] = doc["resolved_at"].isoformat()
        docs.append(doc)
    return docs


# ── Confirm alert → trigger evacuation ────────────────────────────────────────

async def confirm_alert(
    alert_id: str,
    confirmed_by: Optional[str] = None,
) -> dict:
    """
    Staff confirms a pending AI fire alert → triggers evacuation.

    State transition: pending → confirmed
    Then calls fire_service.handle_fire_input() to reuse the full pipeline.
    """
    from services.fire_service import handle_fire_input

    col = get_collection("ai_fire_alerts")

    try:
        oid = ObjectId(alert_id)
    except Exception:
        raise ValueError(f"Invalid alert_id format: {alert_id}")

    doc = await col.find_one({"_id": oid})
    if not doc:
        raise ValueError(f"Alert {alert_id} not found")
    if doc["state"] != "pending":
        raise ValueError(
            f"Alert {alert_id} is already {doc['state']} — cannot confirm"
        )

    now = datetime.now(timezone.utc)
    await col.update_one(
        {"_id": oid},
        {"$set": {
            "state":       "confirmed",
            "resolved_at": now,
            "resolved_by": confirmed_by or "staff",
        }},
    )

    logger.warning(
        "AI alert confirmed by staff | alert_id=%s room=%s floor=%s",
        alert_id, doc["room_id"], doc["floor_id"],
    )

    # ── Trigger evacuation ────────────────────────────────────────────────────
    room_id  = doc["room_id"]
    floor_id = doc["floor_id"]
    risk     = doc["risk"]
    conf     = doc["confidence"]

    # Staff confirmation elevates any risk to HIGH so fire_service
    # passes the ALERT_TRIGGER_LEVELS gate (HIGH / CRITICAL).
    # Without this, MEDIUM alerts are silently ignored by the pipeline.
    effective_risk = "HIGH" if risk.upper() not in ("HIGH", "CRITICAL") else risk.upper()

    message = (
        f"🚨 {risk.upper()} danger confirmed by staff in Room {room_id} "
        f"(AI confidence: {conf:.0%}). "
        f"Immediate evacuation required. Avoid Room {room_id}."
    )

    logger.warning(
        f"Triggering evacuation from AI confirm | room={room_id} floor={floor_id}"
    )

    synthetic_payload = {
        "floor_id":         floor_id,
        "risk_level":       effective_risk,
        "risk_score":       round(conf * 100, 2),
        "action":           "EVACUATE",
        "density_label":    "HIGH",
        "density_value":    0.9,
        "people_count":     0,
        "fire_conf":        conf,
        "movement_score":   0.7,
        "source_room":      room_id,
        "danger_zones":     [room_id],
        "scope":            "floor",
        "override_message": message,
    }

    await handle_fire_input(synthetic_payload)

    return {
        "id":                   alert_id,
        "state":                "confirmed",
        "evacuation_triggered": True,
        "resolved_at":          now.isoformat(),
        "resolved_by":          confirmed_by or "staff",
    }


# ── Dismiss alert ─────────────────────────────────────────────────────────────

async def dismiss_alert(
    alert_id: str,
    dismissed_by: Optional[str] = None,
) -> dict:
    """
    Staff dismisses a pending AI fire alert.
    State transition: pending → dismissed. No evacuation.
    """
    col = get_collection("ai_fire_alerts")

    try:
        oid = ObjectId(alert_id)
    except Exception:
        raise ValueError(f"Invalid alert_id format: {alert_id}")

    doc = await col.find_one({"_id": oid})
    if not doc:
        raise ValueError(f"Alert {alert_id} not found")
    if doc["state"] != "pending":
        raise ValueError(
            f"Alert {alert_id} is already {doc['state']} — cannot dismiss"
        )

    now = datetime.now(timezone.utc)
    await col.update_one(
        {"_id": oid},
        {"$set": {
            "state":       "dismissed",
            "resolved_at": now,
            "resolved_by": dismissed_by or "staff",
        }},
    )

    logger.info(
        "AI alert dismissed | alert_id=%s room=%s dismissed_by=%s",
        alert_id, doc["room_id"], dismissed_by or "staff",
    )

    return {
        "id":          alert_id,
        "state":       "dismissed",
        "resolved_at": now.isoformat(),
        "resolved_by": dismissed_by or "staff",
    }
