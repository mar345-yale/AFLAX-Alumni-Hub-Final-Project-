"""SQLite access for the AFLAX Alumni portal.

One database file (data/aflax.db) holds members, AFSCs, the game schedule, tailgates,
sessions, chat history and usage, and a small geocoding cache.

Schema changes are versioned migrations (see MIGRATIONS), tracked with SQLite's
`PRAGMA user_version`, so an existing database upgrades in place on startup instead of
being wiped with `seed.py --reset`.

Set AFLAX_DATA_DIR to point at a different data folder (the test suite does this).
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("AFLAX_DATA_DIR") or BACKEND_DIR / "data")
UPLOAD_DIR = DATA_DIR / "uploads"
OUTBOX_DIR = DATA_DIR / "outbox"
REFERENCE_DIR = BACKEND_DIR / "reference"
DB_PATH = DATA_DIR / "aflax.db"

# Version 0: the original schema. Created with IF NOT EXISTS so it is safe to re-run.
BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    email             TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash     TEXT,              -- NULL for seeded test profiles (they cannot log in)
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    grad_year         INTEGER NOT NULL,
    status            TEXT NOT NULL,     -- Cadet | Active Duty | Guard/Reserve | Civilian
    rank              TEXT,
    afsc              TEXT,
    aircraft          TEXT,
    job               TEXT,
    base              TEXT,
    city              TEXT,
    phone             TEXT,
    photo_path        TEXT,
    willing_to_mentor INTEGER NOT NULL DEFAULT 1,
    role              TEXT NOT NULL DEFAULT 'member',   -- member | admin
    approval          TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    location_label    TEXT,
    lat               REAL,
    lng               REAL,
    source            TEXT NOT NULL DEFAULT 'signup',   -- signup | seed
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS afscs (
    code        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,   -- Rated | Nonrated
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_date   TEXT NOT NULL,   -- YYYY-MM-DD
    time_label  TEXT NOT NULL DEFAULT '',
    home_away   TEXT NOT NULL,   -- Home | Away | Neutral
    opponent    TEXT NOT NULL,
    location    TEXT NOT NULL,
    venue       TEXT NOT NULL DEFAULT '',
    tournament  TEXT NOT NULL DEFAULT '',
    result      TEXT NOT NULL DEFAULT '',
    lat         REAL,
    lng         REAL
);

CREATE TABLE IF NOT EXISTS tailgates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    location    TEXT NOT NULL,
    start_time  TEXT NOT NULL DEFAULT '',
    details     TEXT NOT NULL DEFAULT '',
    host        TEXT NOT NULL DEFAULT '',
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,   -- user | assistant
    content     TEXT NOT NULL,
    mentor_ids  TEXT NOT NULL DEFAULT '[]',
    intro       TEXT,            -- JSON intro-email draft, if the agent wrote one
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS geocache (
    query TEXT PRIMARY KEY,
    label TEXT,
    lat   REAL,
    lng   REAL
);
"""

# Each entry upgrades the schema by one version. Append new migrations; never edit old ones.
MIGRATIONS: list[str] = [
    # 1: revocable sessions, password resets, tailgate RSVPs, phone privacy,
    #    chat token-usage log, and the agent's running conversation memo.
    """
    ALTER TABLE users ADD COLUMN show_phone INTEGER NOT NULL DEFAULT 1;

    CREATE TABLE sessions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash  TEXT NOT NULL UNIQUE,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at  TEXT NOT NULL,
        revoked_at  TEXT
    );
    CREATE INDEX idx_sessions_user ON sessions(user_id);

    CREATE TABLE password_resets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash  TEXT NOT NULL UNIQUE,
        expires_at  TEXT NOT NULL,
        used_at     TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE tailgate_rsvps (
        tailgate_id INTEGER NOT NULL REFERENCES tailgates(id) ON DELETE CASCADE,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (tailgate_id, user_id)
    );

    CREATE TABLE chat_usage (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at        TEXT NOT NULL DEFAULT (datetime('now')),
        model             TEXT NOT NULL,
        status            TEXT NOT NULL,     -- ok | error
        requests          INTEGER NOT NULL DEFAULT 0,
        tool_calls        INTEGER NOT NULL DEFAULT 0,
        input_tokens      INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens     INTEGER NOT NULL DEFAULT 0,
        reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
        duration_ms       INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_chat_usage_user_time ON chat_usage(user_id, created_at);

    CREATE TABLE chat_memos (
        user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        memo        TEXT NOT NULL,
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 2: audit trail of which tools the agent called (name, arguments, result preview).
    """
    ALTER TABLE chat_usage ADD COLUMN tool_trace TEXT NOT NULL DEFAULT '[]';
    """,
]


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, and always close it."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def schema_version() -> int:
    with connect() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def init_schema() -> None:
    """Create the base schema if needed, then apply any pending migrations in order."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(BASE_SCHEMA)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            # executescript commits on its own, so each migration and its version bump run
            # together inside one explicit transaction.
            conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
