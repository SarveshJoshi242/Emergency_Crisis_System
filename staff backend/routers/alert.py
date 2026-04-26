# ============================================================
#  Emergency Backend · routers/alert.py
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from models.alert import AlertCreate, AlertResolve
from services import alert_service
from services.websocket_manager import manager
from auth.dependencies import require_staff  # JWT guard — staff only

router = APIRouter(prefix="/alert", tags=["Alert"])


@router.post("/manual", summary="Staff-triggered manual alert")
async def manual_alert(
    body: AlertCreate,
    _auth: dict = Depends(require_staff),   # 🔒 staff only
):
    alert = await alert_service.create_manual_alert(
        floor_id=body.floor_id,
        message=body.message,
    )
    await manager.broadcast("alert", alert)
    return alert


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

    return {
        "resolved": len(resolved),
        "failed": len(failed),
        "resolved_ids": resolved,
        "failed_ids": failed,
        "message": f"Resolved {len(resolved)} alert(s). Emergency state cleared."
    }
