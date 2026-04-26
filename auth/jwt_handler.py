# ============================================================
#  auth/jwt_handler.py
#  Purpose: JWT creation, decoding, and refresh-token logic.
#
#  Security decisions:
#  - HS256 (HMAC-SHA256) — fast and sufficient for single-server
#    or shared-secret deployments. Upgrade to RS256 if you ever
#    need public-key verification by external services.
#  - All secrets are read from environment variables; never
#    hard-coded. The app refuses to start if JWT_SECRET is absent.
#  - Access tokens are short-lived (15–30 min) to minimise the
#    blast radius of a leaked token.
#  - Refresh tokens are long-lived but stored in MongoDB so they
#    can be revoked at logout or on suspicious activity.
#  - `exp` and `iat` are standard JWT claims that every
#    compliant library validates automatically.
# ============================================================

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt  # PyJWT

logger = logging.getLogger(__name__)

# ── Secret & algorithm ────────────────────────────────────────────────────────
# Must be set in .env.  A missing secret is a fatal misconfiguration.
JWT_SECRET: str = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(64))\""
    )

# ── Token lifetimes ───────────────────────────────────────────────────────────
ACCESS_TOKEN_EXPIRE_MINUTES_STAFF: int = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_STAFF", "20")
)
ACCESS_TOKEN_EXPIRE_MINUTES_GUEST: int = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES_GUEST", "10")   # Guests get shorter windows
)
REFRESH_TOKEN_EXPIRE_HOURS: int = int(
    os.getenv("REFRESH_TOKEN_EXPIRE_HOURS", "24")
)


# ============================================================
#  Access Token
# ============================================================

def create_access_token(payload: dict, expires_in_minutes: Optional[int] = None) -> str:
    """
    Create a signed JWT access token.

    `payload` should contain at minimum:
        - sub  : unique user identifier (str)
        - role : "staff" | "guest"

    Optional fields the caller may add:
        - permissions : list[str]  (staff only)
        - room_number : str        (guest only)
    """
    if expires_in_minutes is None:
        role = payload.get("role", "guest")
        expires_in_minutes = (
            ACCESS_TOKEN_EXPIRE_MINUTES_STAFF
            if role == "staff"
            else ACCESS_TOKEN_EXPIRE_MINUTES_GUEST
        )

    now = datetime.now(tz=timezone.utc)
    claims = {
        **payload,
        "iat": now,                                            # issued-at
        "exp": now + timedelta(minutes=expires_in_minutes),   # expiry
        "jti": str(uuid.uuid4()),                              # unique token id (replay protection)
        "type": "access",
    }

    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.debug("Access token created | sub=%s role=%s", payload.get("sub"), payload.get("role"))
    return token


def create_refresh_token(user_id: str, role: str) -> tuple[str, datetime]:
    """
    Create a signed JWT refresh token.

    Returns (token_string, expiry_datetime) so the caller can persist
    the expiry in MongoDB alongside the token.

    Refresh tokens are intentionally minimal — they carry only the
    identity needed to issue a new access token.  All sensitive claims
    live only in short-lived access tokens.
    """
    now = datetime.now(tz=timezone.utc)
    expiry = now + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)

    claims = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": expiry,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }

    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.debug("Refresh token created | sub=%s role=%s", user_id, role)
    return token, expiry


# ============================================================
#  Token Decoding & Validation
# ============================================================

def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.

    Raises:
        jwt.ExpiredSignatureError  — token has passed its `exp`
        jwt.InvalidTokenError      — signature tampered / malformed
        ValueError                 — wrong token type (e.g. refresh used as access)

    PyJWT automatically validates `exp` and `iat` — we do NOT need
    to check them manually.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError:
        logger.warning("JWT validation failed: token expired")
        raise
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise

    return payload


def decode_access_token(token: str) -> dict:
    """Decode an access token and assert its type."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ValueError("Token is not an access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode a refresh token and assert its type."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Token is not a refresh token")
    return payload
