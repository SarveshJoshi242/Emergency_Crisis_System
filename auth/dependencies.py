# ============================================================
#  auth/dependencies.py
#  Purpose: FastAPI dependency-injection guards for JWT auth.
#
#  Security decisions:
#  - Token is extracted exclusively from the Authorization header
#    (Bearer scheme).  Cookie-based tokens are skipped to keep
#    the API stateless and CSRF-free.
#  - Role checks are enforced via separate dependencies so each
#    route explicitly declares what it needs — no magic globals.
#  - HTTP 401 (not 403) is returned when the token is missing or
#    invalid; 403 is returned only when the token is valid but the
#    role is insufficient.  This distinction matters for clients.
#  - We attach the decoded payload to request.state so downstream
#    handlers can read it without re-decoding.
# ============================================================

import logging
from typing import Optional

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.jwt_handler import decode_access_token

logger = logging.getLogger(__name__)

# ── Bearer token extractor ────────────────────────────────────────────────────
# auto_error=False means we get None instead of a 403 when the header is
# missing, giving us a clean 401 with our own message.
bearer_scheme = HTTPBearer(auto_error=False)


# ============================================================
#  Core: extract + validate any valid access token
# ============================================================

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    Extract and validate the JWT access token from the Authorization header.

    Returns the decoded payload dict, e.g.:
        {
            "sub": "user_id_here",
            "role": "staff",
            "permissions": ["evacuate", "analytics"],
            "exp": ..., "iat": ..., "jti": ...
        }

    Raises HTTP 401 on any auth failure so the client knows to re-authenticate.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Strip accidental whitespace/newlines — Swagger UI sometimes adds them
    # when copying tokens from the response body.
    token = credentials.credentials.strip()

    # A valid JWT has exactly 3 base64url segments separated by dots
    if token.count(".") != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: must be a JWT with 3 segments (header.payload.signature). "
                   "Ensure you copied the full access_token from the check-in response.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        err = str(exc)
        logger.warning("Invalid token attempt: %s", err)
        # Give a more actionable message for padding errors (truncated token)
        if "padding" in err.lower() or "invalid" in err.lower():
            detail = (
                "Token decoding failed — the token may be truncated or corrupted. "
                "Copy the full access_token value from the check-in/login response and retry."
            )
        else:
            detail = "Invalid or tampered token."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attach to request state for convenience in route handlers
    request.state.user = payload
    return payload


# ============================================================
#  Role guards — compose on top of get_current_user
# ============================================================

async def require_staff(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Guard: allow only staff-role tokens.

    Usage:
        @router.post("/emergency/trigger")
        async def trigger(user = Depends(require_staff)):
            ...
    """
    if current_user.get("role") != "staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required for this endpoint.",
        )
    return current_user


async def require_guest(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Guard: allow only guest-role tokens.

    Usage:
        @router.get("/evacuation/instructions")
        async def instructions(user = Depends(require_guest)):
            ...
    """
    if current_user.get("role") != "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for guests only.",
        )
    return current_user


async def require_staff_or_guest(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Guard: allow both staff and guests (any authenticated user).

    Use this for shared endpoints like emergency status reads.
    """
    role = current_user.get("role")
    if role not in ("staff", "guest"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required.",
        )
    return current_user


# ============================================================
#  Permission check helper (optional granular control)
# ============================================================

def require_permission(permission: str):
    """
    Factory that returns a dependency requiring a specific permission.

    Permissions are stored as a list inside the staff JWT payload, e.g.:
        ["evacuate", "analytics", "manage_staff"]

    Usage:
        @router.post("/analytics")
        async def analytics(user = Depends(require_permission("analytics"))):
            ...
    """
    async def _check(current_user: dict = Depends(require_staff)) -> dict:
        permissions: list = current_user.get("permissions", [])
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' is required for this action.",
            )
        return current_user

    return _check
