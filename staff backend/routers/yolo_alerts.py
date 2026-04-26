# ============================================================
#  Emergency Backend · routers/yolo_alerts.py
#  Purpose: YOLO fire detection integration endpoints.
#
#  Endpoints:
#    POST /alerts/fire-detection       — YOLO medium risk → staff review
#    POST /emergency/auto-trigger      — YOLO high/critical → auto-evac
#    GET  /alerts/ai-pending           — list pending AI alerts for staff
#    POST /alerts/ai/{id}/confirm      — staff confirms → triggers evacuation
#    POST /alerts/ai/{id}/dismiss      — staff dismisses → no action
#
#  Design:
#    • Cleanly decoupled from the existing webhook/danger_tracker path
#    • Reuses fire_service.handle_fire_input() for evacuation (no duplication)
#    • Non-blocking: returns immediately, heavy work in service layer
# ============================================================

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.yolo_alert import (
    AIFireAlertResponse,
    AutoTriggerPayload,
    FireDetectionPayload,
)
from services import yolo_alert_service
from services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["YOLO Fire Detection"])


# ─────────────────────────────────────────────────────────────────────────────
#  1. Fire Detection Alert (medium risk — staff review)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/alerts/fire-detection",
    status_code=201,
    summary="YOLO medium-risk fire detection (staff review required)",
    description="""
Called by the YOLO Room Service when the sliding window buffer confirms
≥70% MEDIUM frames over a 5-second window.

**Behaviour:**
- Stores alert with state = `pending`
- Broadcasts `ai_fire_alert` via WebSocket to staff
- Does **NOT** trigger evacuation

**Safety controls:**
- 30s cooldown per room
- Only one pending alert per room at a time
""",
)
async def fire_detection_alert(payload: FireDetectionPayload):
    try:
        alert = await yolo_alert_service.create_fire_detection_alert(
            room_id=payload.room_id,
            risk=payload.risk,
            confidence=payload.confidence,
            source=payload.source,
            floor_id=payload.floor_id,
        )
    except ValueError as e:
        msg = str(e)
        if "Cooldown" in msg:
            raise HTTPException(status_code=429, detail=msg)
        if "Pending alert already" in msg:
            raise HTTPException(status_code=409, detail=msg)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        logger.error("Fire detection alert failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

    # Broadcast to staff WebSocket clients
    try:
        await manager.broadcast("ai_fire_alert", alert)
    except Exception as ws_err:
        logger.warning("WS broadcast for ai_fire_alert failed (non-fatal): %s", ws_err)

    return alert


# ─────────────────────────────────────────────────────────────────────────────
#  2. Automatic Emergency Trigger (high/critical — auto-evacuation)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/emergency/auto-trigger",
    status_code=200,
    summary="YOLO high/critical risk — automatic evacuation trigger",
    description="""
Called by the YOLO Room Service when the sliding window buffer confirms
≥70% HIGH or CRITICAL frames over a 5-second window.

**Behaviour:**
- Stores alert with state = `confirmed` (auto-confirmed by model)
- Triggers evacuation via `fire_service.handle_fire_input()`
- Updates `emergency_state` for guest app
- Broadcasts emergency + tasks via WebSocket

**Safety controls:**
- 30s cooldown per room
""",
)
async def auto_trigger(payload: AutoTriggerPayload):
    try:
        result = await yolo_alert_service.create_auto_trigger(
            room_id=payload.room_id,
            risk=payload.risk,
            confidence=payload.confidence,
            triggered_by=payload.triggered_by,
            floor_id=payload.floor_id,
        )
    except ValueError as e:
        msg = str(e)
        if "Cooldown" in msg:
            raise HTTPException(status_code=429, detail=msg)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  3. List Pending AI Alerts (staff polling)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/alerts/ai-pending",
    summary="List all pending AI fire alerts for staff review",
    description="Returns AI fire alerts with state='pending', newest first.",
)
async def list_pending_alerts():
    return await yolo_alert_service.get_pending_alerts()


# ─────────────────────────────────────────────────────────────────────────────
#  4. Confirm AI Alert → Trigger Evacuation
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/alerts/ai/{alert_id}/confirm",
    summary="Staff confirms AI alert → triggers evacuation",
    description="""
Staff reviews a pending AI fire alert and confirms it.

**Behaviour:**
- Transitions alert state: pending → confirmed
- Triggers evacuation via `fire_service.handle_fire_input()`
- Generates tasks, broadcasts WebSocket events
""",
)
async def confirm_ai_alert(
    alert_id: str,
    confirmed_by: Optional[str] = Query(None, description="Staff identifier"),
):
    try:
        result = await yolo_alert_service.confirm_alert(
            alert_id=alert_id,
            confirmed_by=confirmed_by,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "cannot confirm" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    # Broadcast state update to staff WebSocket clients
    try:
        await manager.broadcast("ai_alert_update", {
            "alert_id": alert_id,
            "state": "confirmed",
            "resolved_at": result["resolved_at"],
        })
    except Exception as ws_err:
        logger.warning("WS broadcast for ai_alert_update failed (non-fatal): %s", ws_err)

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  5. Dismiss AI Alert
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/alerts/ai/{alert_id}/dismiss",
    summary="Staff dismisses AI alert — no evacuation",
    description="""
Staff reviews a pending AI fire alert and dismisses it.

**Behaviour:**
- Transitions alert state: pending → dismissed
- No evacuation triggered
""",
)
async def dismiss_ai_alert(
    alert_id: str,
    dismissed_by: Optional[str] = Query(None, description="Staff identifier"),
):
    try:
        result = await yolo_alert_service.dismiss_alert(
            alert_id=alert_id,
            dismissed_by=dismissed_by,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "cannot dismiss" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    # Broadcast state update to staff WebSocket clients
    try:
        await manager.broadcast("ai_alert_update", {
            "alert_id": alert_id,
            "state": "dismissed",
            "resolved_at": result["resolved_at"],
        })
    except Exception as ws_err:
        logger.warning("WS broadcast for ai_alert_update failed (non-fatal): %s", ws_err)

    return result
