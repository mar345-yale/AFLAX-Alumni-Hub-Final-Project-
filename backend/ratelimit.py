"""Simple in-memory sliding-window rate limits (one server process).

Used for login attempts, sign-ups, password-reset requests, and chat bursts. The chat
*daily* cap is enforced from the chat_usage table instead (see main.py), so it survives a
restart. Limits are deliberately generous for real members and tight for scripts.
"""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()

# name -> (max events, window seconds)
LIMITS = {
    "login_email": (5, 15 * 60),     # failed logins per account
    "login_ip": (20, 15 * 60),       # failed logins per IP across accounts
    "signup_ip": (5, 60 * 60),
    "forgot_email": (3, 60 * 60),
    "forgot_ip": (10, 60 * 60),
    "chat_burst": (int(os.getenv("CHAT_PER_MINUTE_LIMIT", "6")), 60),
}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune(q: deque[float], window: int, now: float) -> None:
    while q and q[0] <= now - window:
        q.popleft()


def check(name: str, key: str, message: str) -> None:
    """Raise 429 if `key` has already used up limit `name` (does not record a hit)."""
    limit, window = LIMITS[name]
    now = time.time()
    with _lock:
        q = _hits[f"{name}:{key}"]
        _prune(q, window, now)
        if len(q) >= limit:
            retry = int(q[0] + window - now) + 1
            raise HTTPException(
                status_code=429,
                detail=f"{message} Try again in {_wait_text(retry)}.",
                headers={"Retry-After": str(retry)},
            )


def _wait_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = -(-seconds // 60)  # round up
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def hit(name: str, key: str) -> None:
    now = time.time()
    with _lock:
        q = _hits[f"{name}:{key}"]
        _prune(q, LIMITS[name][1], now)
        q.append(now)


def check_and_hit(name: str, key: str, message: str) -> None:
    check(name, key, message)
    hit(name, key)


def clear(name: str, key: str) -> None:
    with _lock:
        _hits.pop(f"{name}:{key}", None)


def reset_all() -> None:
    """For tests."""
    with _lock:
        _hits.clear()
