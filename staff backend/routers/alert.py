# ============================================================
#  Emergency Backend · routers/alert.py
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
import subprocess
import os
from models.alert import AlertCreate, AlertResolve
from services import alert_service
from services.websocket_manager import manager
from auth.dependencies import require_staff  # JWT guard — staff only

router = APIRouter(prefix="/alerts", tags=["Alert"])


@router.post("", summary="Unified alert creation endpoint")
async def create_alert(
    body: AlertCreate,
):
    from database import get_collection
    from datetime import datetime, timezone
    col = get_collection("alerts")
    
    # 1. Deduplicate: Prevent spamming if an active alert for this room already exists
    existing = await col.find_one({"room_id": body.room_id, "status": "ACTIVE"})
    if existing:
        existing["id"] = str(existing.pop("_id"))
        if isinstance(existing.get("created_at"), datetime):
            existing["created_at"] = existing["created_at"].isoformat()
        return existing
        
    # 2. Insert standard fields directly
    now = datetime.now(timezone.utc)
    doc = {
        "floor_id": body.floor,
        "room_id": body.room_id,
        "type": body.type,
        "status": "ACTIVE",
        "risk_level": body.risk_level,
        "confidence": body.confidence,
        "source": body.source,
        "message": f"{body.type.upper()} alert in {body.room_id} (confidence: {body.confidence})",
        "created_at": now
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    doc["created_at"] = now.isoformat()
    
    # 3. Write-through to emergency_state
    from services.alert_service import _sync_emergency_state
    await _sync_emergency_state(
        is_active=True,
        floor_id=body.floor,
        risk_level=body.risk_level,
        affected_floors=[body.floor]
    )

    await manager.broadcast("new_alert", doc)
    return doc


@router.get("/status", summary="List all ACTIVE alerts")
async def alert_status(
    _auth: dict = Depends(require_staff),   # 🔒 staff only
):
    return await alert_service.get_active_alerts()


@router.post("/resolve", summary="Resolve an alert")
async def resolve_alert(
    body: AlertResolve,
    _auth: dict = Depends(require_staff),   # 🔒 staff only
):
    ok = await alert_service.resolve_alert(body.alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    await manager.broadcast("resolve_alert", {"alert_id": body.alert_id})
    return {"alert_id": body.alert_id, "status": "RESOLVED"}


@router.post("/resolve-all", summary="Resolve ALL active alerts and clear emergency state")
async def resolve_all_alerts(
    _auth: dict = Depends(require_staff),   # 🔒 staff only
):
    """
    Bulk-resolve every ACTIVE alert in the database.
    Clears emergency_state to is_active=False when done.
    Useful for resetting stale test data.
    """
    alerts = await alert_service.get_active_alerts()
    if not alerts:
        return {"resolved": 0, "message": "No active alerts found"}

    resolved = []
    failed = []
    for alert in alerts:
        ok = await alert_service.resolve_alert(alert["id"])
        if ok:
            resolved.append(alert["id"])
        else:
            failed.append(alert["id"])

    await manager.broadcast("bulk_update", {"action": "resolve_all", "resolved_ids": resolved})

    return {
        "resolved": len(resolved),
        "failed": len(failed),
        "resolved_ids": resolved,
        "failed_ids": failed,
        "message": f"Resolved {len(resolved)} alert(s). Emergency state cleared."
    }

def run_demo_script():
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../yolo_test_runner.py"))
    video_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../fire_risk/MKBAAG.mp4"))
    subprocess.Popen(["python", script_path, "--video", video_path, "--room", "demo_101", "--floor", "1"])

@router.post("/demo", summary="Trigger demo mode script internally")
async def trigger_demo(
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_staff)
):
    background_tasks.add_task(run_demo_script)
    return {"status": "Demo started"}
