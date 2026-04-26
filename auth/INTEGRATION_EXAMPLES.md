"""
Integration Example: How to use JWT Auth in Staff Backend

This file shows concrete examples of how to integrate the JWT authentication
system into your existing staff backend routes.

Copy these patterns into your routers.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from auth.dependencies import (
    require_staff,
    require_permission,
    require_staff_or_guest,
)

router = APIRouter(prefix="/staff", tags=["Staff Routes"])


# ============================================================
#  Example 1: Staff-Only Route (Simple)
# ============================================================

@router.post(
    "/emergency/trigger",
    summary="Trigger an emergency",
    description="Staff-only endpoint to initiate emergency procedures",
)
async def trigger_emergency(staff_user: dict = Depends(require_staff)):
    """
    Only accessible to staff members with valid JWT token.
    
    The `staff_user` dict contains:
    {
        "sub": "user_id",
        "role": "staff",
        "email": "alice@hotel.local",
        "name": "Manager Alice",
        "permissions": ["view_alerts", "evacuate"],
        "iat": 1698789600,
        "exp": 1698790800
    }
    """
    staff_id = staff_user["sub"]
    staff_name = staff_user.get("name", "Unknown")
    
    # Log the action
    print(f"Emergency triggered by {staff_name} ({staff_id})")
    
    # Your business logic here
    # e.g., db.emergencies.insert_one({...})
    
    return {
        "status": "success",
        "message": "Emergency triggered",
        "triggered_by": staff_id,
        "triggered_by_name": staff_name,
    }


# ============================================================
#  Example 2: Permission-Based Route (Granular Control)
# ============================================================

@router.post(
    "/analytics/export",
    summary="Export analytics data",
    description="Only staff with 'analytics' permission can export",
)
async def export_analytics(staff_user: dict = Depends(require_permission("analytics"))):
    """
    Staff must have 'analytics' permission in their token.
    
    If permission is missing, returns 403 Forbidden automatically.
    """
    staff_id = staff_user["sub"]
    
    # Generate analytics
    analytics_data = {
        "date_range": "2026-04-25 to 2026-04-26",
        "incidents": 3,
        "evacuations": 1,
        "response_time_avg": "2.5 minutes",
    }
    
    # Log export
    print(f"Analytics exported by {staff_id}")
    
    return {
        "status": "success",
        "data": analytics_data,
        "exported_by": staff_id,
    }


# ============================================================
#  Example 3: Multiple Permission Check
# ============================================================

from auth.dependencies import require_staff

@router.post(
    "/admin/staff/deactivate",
    summary="Deactivate a staff account",
    description="Requires both 'manage_staff' AND 'admin' permissions",
)
async def deactivate_staff(
    target_user_id: str,
    staff_user: dict = Depends(require_staff),
):
    """
    Check multiple permissions on a staff action.
    """
    permissions = staff_user.get("permissions", [])
    
    # Require both permissions
    required = {"manage_staff", "admin"}
    has_all = required.issubset(set(permissions))
    
    if not has_all:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You need both {required} permissions",
        )
    
    # Prevent self-deactivation
    if staff_user["sub"] == target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate your own account",
        )
    
    # Deactivate user
    print(f"Staff account {target_user_id} deactivated by {staff_user['sub']}")
    
    return {
        "status": "success",
        "deactivated_user": target_user_id,
        "deactivated_by": staff_user["sub"],
    }


# ============================================================
#  Example 4: Extract User Data from Token
# ============================================================

@router.get(
    "/profile",
    summary="Get current staff member's profile",
)
async def get_profile(staff_user: dict = Depends(require_staff)):
    """
    Use the token payload to return user-specific data.
    """
    return {
        "id": staff_user["sub"],
        "name": staff_user.get("name"),
        "email": staff_user.get("email"),
        "role": staff_user["role"],
        "permissions": staff_user.get("permissions", []),
    }


# ============================================================
#  Example 5: Activity Logging with Auth Context
# ============================================================

@router.post(
    "/floors/{floor_id}/evacuate",
    summary="Evacuate a specific floor",
)
async def evacuate_floor(
    floor_id: str,
    staff_user: dict = Depends(require_permission("evacuate")),
):
    """
    Log actions with staff member context from JWT.
    """
    from datetime import datetime, timezone
    
    staff_id = staff_user["sub"]
    staff_name = staff_user.get("name", "Unknown")
    
    # Create activity log entry
    activity_log = {
        "action": "floor_evacuation",
        "floor_id": floor_id,
        "initiated_by_id": staff_id,
        "initiated_by_name": staff_name,
        "initiated_by_email": staff_user.get("email"),
        "timestamp": datetime.now(tz=timezone.utc),
    }
    
    # Log to database or logging system
    print(f"Activity Log: {activity_log}")
    
    return {
        "status": "evacuation_initiated",
        "floor_id": floor_id,
        "initiated_by": staff_name,
    }


# ============================================================
#  Example 6: Combining Multiple Guards
# ============================================================

from auth.dependencies import get_current_user

@router.get(
    "/debug/token-info",
    summary="Debug endpoint - show current token",
)
async def debug_token_info(current_user: dict = Depends(get_current_user)):
    """
    This endpoint works for ANY authenticated user (staff or guest).
    
    Useful for debugging or frontend token inspection.
    
    In production, restrict this endpoint to admin staff only.
    """
    # Verify user is staff
    if current_user.get("role") != "staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for staff only",
        )
    
    # Verify staff has debug permission
    permissions = current_user.get("permissions", [])
    if "debug" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug permission required",
        )
    
    # Return token info
    return {
        "message": "Token info (debug mode)",
        "sub": current_user.get("sub"),
        "role": current_user.get("role"),
        "email": current_user.get("email"),
        "permissions": current_user.get("permissions"),
        "issued_at": current_user.get("iat"),
        "expires_at": current_user.get("exp"),
        "token_id": current_user.get("jti"),
    }


# ============================================================
#  Example 7: Access Control at Data Level
# ============================================================

@router.get(
    "/floors/{floor_id}/incidents",
    summary="Get incidents for a floor",
)
async def get_floor_incidents(
    floor_id: str,
    staff_user: dict = Depends(require_staff),
):
    """
    Use staff permissions to determine data visibility.
    """
    permissions = staff_user.get("permissions", [])
    
    # Fetch incidents from database
    # incidents = db.incidents.find({"floor_id": floor_id})
    
    # Filter based on staff permissions
    if "view_all_incidents" in permissions:
        # Manager: see all incidents including resolved ones
        incidents = []  # [all incidents]
    elif "view_alerts" in permissions:
        # Staff: see only unresolved incidents
        incidents = []  # [unresolved incidents only]
    else:
        # No permission
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required to view incidents",
        )
    
    return {
        "floor_id": floor_id,
        "incident_count": len(incidents),
        "incidents": incidents,
        "user_permission_level": "manager" if "view_all_incidents" in permissions else "staff",
    }


# ============================================================
#  Example 8: Error Handling
# ============================================================

@router.post(
    "/configuration/update",
    summary="Update system configuration",
)
async def update_config(
    config_update: dict,
    staff_user: dict = Depends(require_permission("admin")),
):
    """
    Example of error handling with auth context.
    """
    try:
        # Validate config
        if not isinstance(config_update, dict):
            raise ValueError("Config must be a dictionary")
        
        if len(config_update) == 0:
            raise ValueError("Config update cannot be empty")
        
        # Apply config
        print(f"Config updated: {config_update}")
        
        return {
            "status": "success",
            "message": "Configuration updated",
            "updated_by": staff_user["sub"],
            "updated_fields": list(config_update.keys()),
        }
    
    except ValueError as e:
        # Log who tried what
        print(f"Config update failed by {staff_user['sub']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        # Log unexpected errors
        print(f"Unexpected error during config update by {staff_user['sub']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration update failed",
        )


# ============================================================
#  Usage in main.py
# ============================================================

"""
To use this router in your staff backend:

In staff_backend/main.py:
    
    from auth.routes import router as auth_router
    from routers.staff_integration import router as staff_router
    
    app = FastAPI()
    
    # Mount auth router first (handles /auth/* endpoints)
    app.include_router(auth_router)
    
    # Mount other routers (protected by auth dependencies)
    app.include_router(staff_router)
    
    # Now you can:
    # POST /auth/staff/login → get token
    # POST /staff/emergency/trigger → (requires token from login)
    # POST /staff/analytics/export → (requires token + analytics permission)
    # etc.
"""


# ============================================================
#  Testing These Endpoints
# ============================================================

"""
Test with curl:

# 1. Login
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/staff/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@hotel.local",
    "password": "password"
  }')

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

# 2. Use protected endpoint
curl -X POST http://localhost:8000/staff/emergency/trigger \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 3. Export analytics (if permission exists)
curl -X POST http://localhost:8000/staff/analytics/export \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 4. Get current user profile
curl -X GET http://localhost:8000/staff/profile \
  -H "Authorization: Bearer $ACCESS_TOKEN"
"""
