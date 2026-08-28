"""
rebob/core/store.py — SQLite initialisation for ReBOB.

Call init_db() once on startup.  Safe to call multiple times (idempotent).
DB lives at .rebob/rebob.db — that directory is gitignored.
"""

import sqlite3
from pathlib import Path

_DB_DIR = Path(".rebob")
_DB_PATH = _DB_DIR / "rebob.db"


def db_path() -> Path:
    """Return the path to the SQLite database file."""
    return _DB_PATH


def init_db() -> None:
    """Create .rebob/ and initialise the SQLite schema if not already present."""
    _DB_DIR.mkdir(exist_ok=True)

    con = sqlite3.connect(_DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")

    con.executescript("""
        CREATE TABLE IF NOT EXISTS memory (
            id          TEXT PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'active',
            kind        TEXT NOT NULL DEFAULT 'fact',
            scope       TEXT NOT NULL DEFAULT 'project',
            content     TEXT NOT NULL,
            rationale   TEXT NOT NULL DEFAULT '',
            keywords    TEXT NOT NULL DEFAULT '',
            session_id  TEXT NOT NULL DEFAULT '',
            label       TEXT NOT NULL DEFAULT '',
            score       REAL NOT NULL DEFAULT 0.0,
            created_at  TEXT NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at  TEXT NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content, rationale, keywords, content=memory);
    """)

    con.commit()
    con.close()
