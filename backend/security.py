"""Passwords, sessions, password-reset tokens, and signed photo links.

- Passwords: PBKDF2-HMAC-SHA256, stored as `pbkdf2_sha256$salt$hash`. The plain password
  never touches disk, an API response, or the agent.
- Sessions: an opaque random token goes to the browser; only its SHA-256 hash is stored.
  Because sessions live in the database, logging out revokes that session and changing a
  password revokes every other session immediately.
- Password resets: single-use random tokens (hashed at rest) that expire after an hour.
- Photo links: profile pictures are served only through short-lived HMAC-signed URLs that
  appear in logged-in API responses, so an outsider can't browse uploads.
"""

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from db import DATA_DIR, connect

PBKDF2_ALGO = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16
SESSION_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=1)
PHOTO_LINK_TTL_SECONDS = 12 * 60 * 60


def _load_secret() -> str:
    env = os.getenv("AUTH_SECRET")
    if env:
        return env
    path = DATA_DIR / ".auth_secret"
    if path.exists():
        return path.read_text().strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    path.write_text(value)
    return value


_SECRET = _load_secret()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sql_time(dt: datetime) -> str:
    """Same format as SQLite's datetime('now'), so string comparison works in queries."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------ passwords

def hash_password(password: str) -> str:
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS
    ).hex()
    return f"{PBKDF2_ALGO}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != PBKDF2_ALGO:
        return False
    computed = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS
    ).hex()
    # Constant-time compare so timing can't leak the hash.
    return hmac.compare_digest(computed, digest)


# ------------------------------------------------------------ sessions

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, _sql_time(_now() + SESSION_TTL)),
        )
    return token


def resolve_session(token: str) -> int | None:
    """User id for a live (not revoked, not expired) session token, else None."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM sessions
            WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
            """,
            (_hash_token(token), _sql_time(_now())),
        ).fetchone()
    return row["user_id"] if row else None


def revoke_session(token: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE sessions SET revoked_at = datetime('now') WHERE token_hash = ? AND revoked_at IS NULL",
            (_hash_token(token),),
        )


def revoke_all_sessions(user_id: int, keep_token: str | None = None) -> None:
    """End every session for a member, optionally keeping the one making the request."""
    keep = _hash_token(keep_token) if keep_token else ""
    with connect() as conn:
        conn.execute(
            """
            UPDATE sessions SET revoked_at = datetime('now')
            WHERE user_id = ? AND revoked_at IS NULL AND token_hash != ?
            """,
            (user_id, keep),
        )


# ------------------------------------------------------------ password resets

def create_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        # Only the newest link works.
        conn.execute(
            "UPDATE password_resets SET used_at = datetime('now') WHERE user_id = ? AND used_at IS NULL",
            (user_id,),
        )
        conn.execute(
            "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, _hash_token(token), _sql_time(_now() + RESET_TTL)),
        )
    return token


def consume_reset_token(token: str) -> int | None:
    """Mark a reset token used and return its user id, or None if invalid/expired/used."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, user_id FROM password_resets
            WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
            """,
            (_hash_token(token), _sql_time(_now())),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE password_resets SET used_at = datetime('now') WHERE id = ?", (row["id"],))
    return row["user_id"]


# ------------------------------------------------------------ signed photo links

def _photo_sig(name: str, expires: int) -> str:
    return hmac.new(_SECRET.encode(), f"photo:{name}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_photo_url(name: str | None) -> str | None:
    if not name:
        return None
    # Round expiry to the hour so URLs stay stable (browser-cacheable) within that hour.
    expires = (int(time.time()) // 3600 + 1) * 3600 + PHOTO_LINK_TTL_SECONDS
    return f"/api/photos/{name}?exp={expires}&sig={_photo_sig(name, expires)}"


def verify_photo_link(name: str, expires: int, sig: str) -> bool:
    if expires < time.time():
        return False
    return hmac.compare_digest(sig, _photo_sig(name, expires))
