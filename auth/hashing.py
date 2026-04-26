# ============================================================
#  auth/hashing.py
#  Purpose: Bcrypt password hashing helpers for staff accounts.
#
#  Security decisions:
#  - bcrypt is the industry standard for password storage.
#    It is deliberately slow (cost-factor/rounds) to make
#    offline dictionary attacks expensive.
#  - We never store plain-text passwords anywhere.
#  - `checkpw` uses a constant-time comparison internally,
#    which prevents timing-based side-channel attacks.
# ============================================================

import bcrypt


def hash_password(plain: str) -> str:
    """
    Hash a plain-text password with bcrypt.

    Returns a UTF-8 decoded string so it can be stored as a
    normal string field in MongoDB (no binary BSON needed).

    Cost factor defaults to 12 — a good balance between security
    and latency (~250 ms on modern hardware, negligible UX impact).
    """
    # bcrypt.gensalt(rounds=12) is the default; explicit for clarity
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")  # store as string in MongoDB


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain-text password against its stored bcrypt hash.

    Uses bcrypt's built-in constant-time comparison to prevent
    timing attacks — never use `==` for password comparison.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
