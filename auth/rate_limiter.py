# ============================================================
#  auth/rate_limiter.py
#  Purpose: Simple in-memory sliding-window rate limiter.
#
#  Security decisions:
#  - Brute-force protection on login endpoints is non-negotiable.
#  - This implementation uses a per-IP sliding window (deque)
#    stored in a module-level dict — works fine for a single-process
#    server (development + small deployments).
#  - For multi-worker / multi-server production deployments, swap
#    the in-memory store for Redis (e.g. using slowapi + redis).
#  - The check is done BEFORE credential verification so the
#    attacker is blocked even before we touch the database.
# ============================================================

import time
import logging
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Global in-memory store: { "key": deque([timestamp, ...]) }
_windows: dict[str, deque] = defaultdict(deque)
_lock = Lock()          # thread-safe for sync code paths


def check_rate_limit(
    identifier: str,
    max_requests: int = 5,
    window_seconds: int = 60,
    key_prefix: str = "login",
) -> None:
    """
    Sliding-window rate limiter.

    Args:
        identifier:     Typically the client IP address.
        max_requests:   Maximum allowed requests in the window.
        window_seconds: Length of the sliding window in seconds.
        key_prefix:     Namespace key (e.g. "staff" vs "guest") to
                        keep buckets separate for different endpoints.

    Raises:
        HTTP 429 Too Many Requests — when limit exceeded.
    """
    key = f"{key_prefix}:{identifier}"
    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        window = _windows[key]

        # Remove timestamps outside the current window
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= max_requests:
            retry_after = int(window[0] + window_seconds - now) + 1
            logger.warning(
                "Rate limit exceeded | key=%s attempts=%d window=%ds",
                key, len(window), window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many attempts. Try again in {retry_after} second(s)."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
