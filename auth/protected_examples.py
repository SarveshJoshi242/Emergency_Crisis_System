# ============================================================
#  auth/protected_examples.py
#  Purpose: Concrete examples showing how to protect routes
#           with the auth dependencies from dependencies.py.
#
#  These examples demonstrate all three access patterns:
#    1. Staff-only routes (evacuation control, analytics)
#    2. Guest-only routes (emergency status, instructions)
#    3. Shared routes    (both roles allowed)
#
#  Copy/adapt the patterns into your real routers.
#  Register this router in main.py with:
#      app.include_router(examples_router)
# ============================================================

from fastapi import APIRouter, Depends

from auth.dependencies import (
    require_staff,
    require_guest,
    require_staff_or_guest,
    require_permission,
)

router = APIRouter(prefix="/examples", tags=["Protected Route Examples"])


# ============================================================
#  STAFF-ONLY ROUTES
#  Use: Depends(require_staff)
#  Returns 401 if no token, 403 if token is guest-role.
# ============================================================

@router.post(
    "/emergency/trigger",
    summary="[Staff only] Trigger an emergency",
)
async def trigger_emergency(
    staff_user: dict = Depends(require_staff),
):
    """
    Only accessible with a valid staff JWT.
    `staff_user` contains the decoded payload, e.g.:
        { "sub": "...", "role": "staff", "permissions": [...] }
    """
    return {
        "triggered_by": staff_user["sub"],
        "name": staff_user.get("name"),
        "message": "Emergency triggered successfully.",
    }


@router.get(
    "/analytics/summary",
    summary="[Staff only] Get analytics summary",
)
async def analytics_summary(
    staff_user: dict = Depends(require_staff),
):
    """Dashboard analytics — staff access only."""
    return {
        "accessed_by": staff_user["sub"],
        "data": "analytics_payload_here",
    }


@router.post(
    "/evacuation/control",
    summary="[Staff + analytics permission] Evacuation control",
)
async def evacuation_control(
    # Requires staff role AND the 'evacuate' permission in the token
    staff_user: dict = Depends(require_permission("evacuate")),
):
    """
    Fine-grained permission check on top of the staff role guard.
    Staff without the 'evacuate' permission get HTTP 403.
    """
    return {
        "initiated_by": staff_user["sub"],
        "message": "Evacuation sequence initiated.",
    }


# ============================================================
#  GUEST-ONLY ROUTES
#  Use: Depends(require_guest)
#  Returns 401 if no token, 403 if token is staff-role.
# ============================================================

@router.get(
    "/emergency/status",
    summary="[Guest only] Get current emergency status",
)
async def emergency_status(
    guest_user: dict = Depends(require_guest),
):
    """
    Guests poll this to know if there's an active emergency.
    Scoped to the guest's room from the token payload.
    """
    return {
        "guest_id": guest_user["sub"],
        "room_number": guest_user.get("room_number"),
        "emergency_active": False,   # replace with real DB query
        "message": "No active emergency in your area.",
    }


@router.get(
    "/evacuation/instructions",
    summary="[Guest only] Get evacuation route instructions",
)
async def evacuation_instructions(
    guest_user: dict = Depends(require_guest),
):
    """
    Returns personalized evacuation route for this guest's room.
    Room number is read directly from the JWT — no need to pass it
    as a query param (prevents spoofing).
    """
    room = guest_user.get("room_number", "unknown")
    return {
        "room_number": room,
        "route": f"Exit via stairwell B from room {room}.",
        "assembly_point": "Parking lot A",
    }


# ============================================================
#  SHARED ROUTES — staff and guests both allowed
#  Use: Depends(require_staff_or_guest)
# ============================================================

@router.get(
    "/alerts/active",
    summary="[Staff + Guest] View active alerts",
)
async def active_alerts(
    current_user: dict = Depends(require_staff_or_guest),
):
    """
    Both staff and guests can view active alerts, but the
    response could be filtered by role in a real implementation.
    """
    role = current_user["role"]
    return {
        "viewer_role": role,
        "viewer_id": current_user["sub"],
        # Staff see all alerts; guests see only their floor's alerts
        "filter": "all" if role == "staff" else f"floor_{current_user.get('room_number', 'unknown')}",
        "alerts": [],   # replace with real DB query
    }


@router.get(
    "/system/health",
    summary="[Staff + Guest] System health check",
)
async def system_health(
    current_user: dict = Depends(require_staff_or_guest),
):
    """Any authenticated user can ping the system status."""
    return {
        "status": "operational",
        "requested_by": current_user["sub"],
        "role": current_user["role"],
    }
