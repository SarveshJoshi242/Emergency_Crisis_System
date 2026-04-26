# ============================================================
#  auth/routes.py
#  Purpose: Authentication endpoints — staff login, guest check-in,
#           token refresh, and logout.
#
#  Mounts at prefix /auth (registered in each backend's main.py).
#
#  Security decisions:
#  - Staff login uses email + bcrypt-verified password.
#  - Guest login uses room_number + phone OR booking_id (no password).
#  - Refresh tokens are stored in MongoDB; on use the old one is
#    deleted and a new one is issued (token rotation).
#  - Logout deletes the refresh token from DB (server-side revocation).
#  - Rate limiting on /auth/staff/login prevents brute-force attacks.
#    Uses an in-memory sliding-window counter per IP.
#    For production with multiple workers, replace with Redis.
# ============================================================

import logging
from datetime import datetime, timezone
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorDatabase

from auth.hashing import hash_password, verify_password
from auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES_STAFF,
    ACCESS_TOKEN_EXPIRE_MINUTES_GUEST,
)
from auth.dependencies import get_current_user
from auth.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── DB helper — injected via request.app.state ─────────────────────────────────
# Each backend attaches its Motor database to app.state.db at startup.
# Routes read it from there to avoid circular imports.

def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


# ============================================================
#  Pydantic request/response models
# ============================================================

class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str


class GuestCheckInRequest(BaseModel):
    """
    Guest check-in — zero friction.

    Accepted combinations (priority order):
      1. booking_id alone
      2. room_id + phone  (any format — last 4 digits stored)
      3. room_id alone    (fastest — auto-creates guest)

    If the guest does NOT exist, one is auto-created.
    """
    room_id:     Optional[str] = None
    phone:       Optional[str] = None   # full number or last-4, normalised internally
    phone_last4: Optional[str] = None   # legacy compat
    booking_id:  Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    expires_in_minutes: int


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterStaffRequest(BaseModel):
    """
    One-time staff registration. In production, restrict this endpoint
    to admin-only or remove it entirely after seeding accounts.
    """
    name: str
    email: EmailStr
    password: str
    permissions: list[str] = ["view_alerts"]  # default minimal permissions


# ============================================================
#  Staff: Register (seeding / admin use)
# ============================================================

@router.post(
    "/staff/register",
    status_code=201,
    summary="Register a new staff account",
    description=(
        "Creates a staff account with a bcrypt-hashed password. "
        "Restrict or remove this endpoint after initial seeding."
    ),
)
async def register_staff(body: RegisterStaffRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    # Check duplicate email
    existing = await db["staff_accounts"].find_one({"email": body.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A staff account with this email already exists.",
        )

    now = datetime.now(tz=timezone.utc)
    doc = {
        "name": body.name,
        "email": body.email,
        "password_hash": hash_password(body.password),   # bcrypt — never plain-text
        "role": "staff",
        "permissions": body.permissions,
        "created_at": now,
        "is_active": True,
    }

    result = await db["staff_accounts"].insert_one(doc)
    logger.info("New staff account created | email=%s", body.email)

    return {
        "id": str(result.inserted_id),
        "name": body.name,
        "email": body.email,
        "permissions": body.permissions,
        "created_at": now.isoformat(),
    }


# ============================================================
#  Staff: Login
# ============================================================

@router.post(
    "/staff/login",
    response_model=TokenResponse,
    summary="Staff login — email + password",
)
async def staff_login(
    body: StaffLoginRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Verify staff credentials and issue access + refresh tokens.

    Rate limited: max 5 attempts per IP per minute.
    Returns generic error messages to avoid leaking account existence.
    """
    # ── Rate limit: 5 requests/minute per IP ─────────────────────────────────
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip, max_requests=5, window_seconds=60)

    # ── Lookup account ────────────────────────────────────────────────────────
    account = await db["staff_accounts"].find_one({"email": body.email, "is_active": True})

    # Deliberately vague — do not confirm whether the email exists
    if not account or not verify_password(body.password, account["password_hash"]):
        logger.warning("Failed staff login attempt | ip=%s email=%s", client_ip, body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    user_id = str(account["_id"])
    permissions: list[str] = account.get("permissions", [])

    # ── Issue tokens ──────────────────────────────────────────────────────────
    access_token = create_access_token({
        "sub": user_id,
        "role": "staff",
        "email": account["email"],
        "name": account["name"],
        "permissions": permissions,
    })

    refresh_token, refresh_expiry = create_refresh_token(user_id, "staff")

    # Store refresh token in DB for server-side revocation at logout
    await db["refresh_tokens"].insert_one({
        "token": refresh_token,
        "user_id": user_id,
        "role": "staff",
        "expires_at": refresh_expiry,
        "created_at": datetime.now(tz=timezone.utc),
    })

    logger.info("Staff login successful | user_id=%s ip=%s", user_id, client_ip)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role="staff",
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES_STAFF,
    )


# ============================================================
#  Guest: Check-in / Session creation
# ============================================================

@router.post(
    "/guest/checkin",
    response_model=TokenResponse,
    summary="Guest check-in — auto-creates guest if not found",
)
async def guest_checkin(
    body: GuestCheckInRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Zero-friction guest check-in for the emergency system.

    Lookup priority:
      1. booking_id provided → find by booking_id
      2. room_id + phone     → find by room_id + last-4 of phone
      3. room_id only        → find by room_id alone

    Auto-create: if no matching guest is found, one is created immediately.
    """
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip, max_requests=10, window_seconds=60, key_prefix="guest")

    # ── Normalise phone → last 4 digits ──────────────────────────────────────
    raw_phone   = body.phone or body.phone_last4 or ""
    phone_last4 = raw_phone.replace(" ", "").replace("-", "")[-4:] if raw_phone else None

    # ── Lookup (most → least specific) ───────────────────────────────────────
    guest = None

    if body.booking_id:
        logger.info("Guest checkin attempt | booking_id=%s", body.booking_id)
        guest = await db["guests"].find_one({"booking_id": body.booking_id})

    elif body.room_id and phone_last4:
        logger.info("Guest checkin attempt | room_id=%s phone_last4=%s", body.room_id, phone_last4)
        guest = await db["guests"].find_one({"room_id": body.room_id, "phone_last4": phone_last4})

    elif body.room_id:
        logger.info("Guest checkin attempt | room_id=%s (no phone)", body.room_id)
        guest = await db["guests"].find_one({"room_id": body.room_id})

    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least room_id, or booking_id.",
        )

    # ── Auto-create if not found ──────────────────────────────────────────────
    if not guest:
        now = datetime.now(tz=timezone.utc)
        new_guest = {
            "room_id":      body.room_id or "",
            "phone_last4":  phone_last4 or "0000",
            "booking_id":   body.booking_id or f"AUTO-{(body.room_id or 'GUEST').upper()}",
            "floor_id":     "",
            "status":       "checked_in",
            "created_at":   now,
            "auto_created": True,
        }

        # Try to resolve floor_id from floor graph (non-fatal if it fails)
        if body.room_id:
            try:
                floor_doc = await db["floors"].find_one(
                    {"graph.nodes": {"$elemMatch": {"id": body.room_id}}},
                    sort=[("created_at", -1)],
                )
                if floor_doc:
                    new_guest["floor_id"] = floor_doc.get("floor_id") or str(floor_doc["_id"])
            except Exception:
                pass

        result = await db["guests"].insert_one(new_guest)
        guest = {**new_guest, "_id": result.inserted_id}
        logger.info("Guest auto-created | room_id=%s", body.room_id)

    # ── Issue tokens ──────────────────────────────────────────────────────────
    guest_id = str(guest["_id"])
    room_id  = guest.get("room_id") or body.room_id or ""
    floor_id = guest.get("floor_id", "")

    access_token = create_access_token({
        "sub":        guest_id,
        "role":       "guest",
        "room_id":    room_id,
        "floor_id":   floor_id,
        "booking_id": guest.get("booking_id", ""),
    })

    refresh_token, refresh_expiry = create_refresh_token(guest_id, "guest")

    await db["refresh_tokens"].insert_one({
        "token":      refresh_token,
        "user_id":    guest_id,
        "role":       "guest",
        "room_id":    room_id,
        "floor_id":   floor_id,
        "expires_at": refresh_expiry,
        "created_at": datetime.now(tz=timezone.utc),
    })

    logger.info(
        "Guest check-in OK | guest_id=%s room_id=%s auto_created=%s",
        guest_id, room_id, guest.get("auto_created", False),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role="guest",
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES_GUEST,
    )



# ============================================================
#  Token Refresh
# ============================================================

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using a valid refresh token",
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Validate the refresh token, delete it (rotation), and issue a
    new access + refresh token pair.

    Token rotation means a stolen refresh token can only be used once
    before it becomes invalid — the legitimate user's next refresh
    will fail and alert them to re-login.
    """
    # ── Decode + validate JWT signature ───────────────────────────────────────
    try:
        payload = decode_refresh_token(body.refresh_token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )
    except (pyjwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    # ── Check DB: token must exist (not already used / revoked) ──────────────
    stored = await db["refresh_tokens"].find_one({"token": body.refresh_token})
    if not stored:
        # Token was already rotated or revoked — possible replay attack
        logger.warning(
            "Refresh token reuse detected | user_id=%s", payload.get("sub")
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already used or revoked. Please log in again.",
        )

    user_id: str = payload["sub"]
    role: str = payload["role"]

    # ── Delete old refresh token (rotation) ───────────────────────────────────
    await db["refresh_tokens"].delete_one({"token": body.refresh_token})

    # ── Build new access token payload ────────────────────────────────────────
    if role == "staff":
        account = await db["staff_accounts"].find_one({"_id": stored.get("user_id") or user_id})
        new_access_payload = {
            "sub": user_id,
            "role": "staff",
            "email": account["email"] if account else "",
            "name": account["name"] if account else "",
            "permissions": account.get("permissions", []) if account else [],
        }
    else:  # guest
        new_access_payload = {
            "sub": user_id,
            "role": "guest",
            "room_id": stored.get("room_id", ""),      # use room_id (node ID)
            "floor_id": stored.get("floor_id", ""),
        }

    # ── Issue new pair ────────────────────────────────────────────────────────
    new_access_token = create_access_token(new_access_payload)
    new_refresh_token, new_refresh_expiry = create_refresh_token(user_id, role)

    await db["refresh_tokens"].insert_one({
        "token": new_refresh_token,
        "user_id": user_id,
        "role": role,
        "room_number": stored.get("room_number"),
        "expires_at": new_refresh_expiry,
        "created_at": datetime.now(tz=timezone.utc),
    })

    expires = (
        ACCESS_TOKEN_EXPIRE_MINUTES_STAFF
        if role == "staff"
        else ACCESS_TOKEN_EXPIRE_MINUTES_GUEST
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        role=role,
        expires_in_minutes=expires,
    )


# ============================================================
#  Logout
# ============================================================

@router.post(
    "/logout",
    status_code=200,
    summary="Logout — revoke refresh token",
)
async def logout(
    body: RefreshRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Revoke the provided refresh token by deleting it from the DB.

    The access token cannot be invalidated (it's stateless), but its
    short expiry makes it low-risk.  Clients should discard it locally.
    """
    result = await db["refresh_tokens"].delete_one({
        "token": body.refresh_token,
        "user_id": current_user["sub"],  # ensure users can only revoke their own tokens
    })

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found or already revoked.",
        )

    logger.info("User logged out | user_id=%s role=%s", current_user["sub"], current_user["role"])
    return {"message": "Logged out successfully. Please discard your access token."}


# ============================================================
#  Me — current user info
# ============================================================

@router.get("/me", summary="Get current authenticated user info")
async def me(current_user: dict = Depends(get_current_user)):
    """
    Returns identity info from the decoded JWT payload.

    Staff response:  user_id, role, name, email, permissions
    Guest response:  user_id, role, room_id, floor_id, booking_id
    """
    role = current_user.get("role")

    base = {
        "user_id": current_user["sub"],
        "role": role,
    }

    if role == "staff":
        base.update({
            "name":        current_user.get("name"),
            "email":       current_user.get("email"),
            "permissions": current_user.get("permissions", []),
        })
    else:  # guest
        base.update({
            "room_id":    current_user.get("room_id"),    # node ID e.g. "master_bedroom"
            "floor_id":   current_user.get("floor_id"),   # e.g. "Third Floor"
            "booking_id": current_user.get("booking_id"),
        })

    return base


# ============================================================
#  Guest-only auth router
#  Import this in guest_backend/app/main.py.
#  Excludes /staff/register and /staff/login — those are
#  staff-backend concerns only and must not appear in the
#  guest Swagger UI or be reachable from port 8000.
# ============================================================

guest_auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

# Guest check-in (the guest equivalent of "login")
guest_auth_router.add_api_route(
    "/guest/checkin",
    guest_checkin,
    methods=["POST"],
    response_model=TokenResponse,
    summary="Guest check-in — room + phone OR booking_id",
)

# Shared: token refresh (guests need this too)
guest_auth_router.add_api_route(
    "/refresh",
    refresh_token,
    methods=["POST"],
    response_model=TokenResponse,
    summary="Refresh access token using a valid refresh token",
)

# Shared: logout
guest_auth_router.add_api_route(
    "/logout",
    logout,
    methods=["POST"],
    status_code=200,
    summary="Logout — revoke refresh token",
)

# Shared: current user info
guest_auth_router.add_api_route(
    "/me",
    me,
    methods=["GET"],
    summary="Get current authenticated user info",
)
