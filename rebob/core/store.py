"""
rebob/core/store.py — SQLite store + numpy vector append for ReBOB.

Call init_db() once on startup.  Safe to call multiple times (idempotent).
DB lives at .rebob/rebob.db  — that directory is gitignored.
Delete .rebob/rebob.db to reset the dev DB.

Vectors live at .rebob/vectors.npy as a float32 array of shape (N, dim).
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

_DB_DIR = Path(".rebob")
_DB_PATH = _DB_DIR / "rebob.db"

_FULL_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
  id                TEXT PRIMARY KEY,
  claim_key         TEXT NOT NULL,
  version           INTEGER DEFAULT 1,
  supersedes        TEXT,
  status            TEXT NOT NULL,
  created_at        TIMESTAMP,
  updated_at        TIMESTAMP,

  memory_type       TEXT NOT NULL,
  content           TEXT NOT NULL,
  rationale         TEXT,
  counter_example   TEXT,
  snippet           TEXT,

  scope             TEXT NOT NULL,
  repo_url          TEXT,
  branch            TEXT,
  author_id         TEXT,
  file_paths        TEXT,
  symbols           TEXT,
  languages         TEXT,
  commit_sha        TEXT,
  anchor_valid      BOOLEAN DEFAULT 1,

  source_kind       TEXT,
  task_id           TEXT,
  bob_mode          TEXT,
  extractor_model   TEXT,
  raw_hash          TEXT,

  confidence        REAL,
  evidence_count    INTEGER DEFAULT 1,
  volatility        TEXT,
  verification      TEXT,

  retrieval_count   INTEGER DEFAULT 0,
  used_count        INTEGER DEFAULT 0,
  positive_signals  INTEGER DEFAULT 0,
  negative_signals  INTEGER DEFAULT 0,
  usefulness        REAL DEFAULT 0.5,
  last_used_at      TIMESTAMP,

  sensitivity       TEXT DEFAULT 'internal',
  redaction_applied TEXT,
  pinned            BOOLEAN DEFAULT 0,

  vector_row        INTEGER,
  keywords          TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
  USING fts5(content, rationale, keywords, content=memory);
"""


def db_path() -> Path:
    """Return the path to the SQLite database file."""
    return _DB_PATH


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    """Create .rebob/ and initialise the SQLite schema if not already present."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    con = _connect()
    con.executescript(_FULL_SCHEMA)
    con.commit()
    con.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_memory(record: dict) -> str:
    """Insert a memory row. Generates id like mem_<8 hex chars> if not present.

    Returns the inserted id.
    """
    import secrets
    row = dict(record)
    if not row.get("id"):
        row["id"] = "mem_" + secrets.token_hex(4)
    now = _now()
    row.setdefault("created_at", now)
    row.setdefault("updated_at", now)
    row.setdefault("status", "active")
    row.setdefault("scope", "repo")
    row.setdefault("evidence_count", 1)
    row.setdefault("version", 1)
    row.setdefault("anchor_valid", 1)
    row.setdefault("usefulness", 0.5)
    row.setdefault("retrieval_count", 0)
    row.setdefault("used_count", 0)
    row.setdefault("positive_signals", 0)
    row.setdefault("negative_signals", 0)
    row.setdefault("sensitivity", "internal")
    row.setdefault("pinned", 0)
    row.setdefault("verification", "asserted")

    # JSON-encode list fields if they came in as lists
    for field in ("file_paths", "symbols", "languages", "keywords", "redaction_applied"):
        if isinstance(row.get(field), (list, dict)):
            row[field] = json.dumps(row[field])

    columns = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    con = _connect()
    con.execute(
        f"INSERT INTO memory ({columns}) VALUES ({placeholders})",
        list(row.values()),
    )
    # Keep FTS in sync
    con.execute(
        "INSERT INTO memory_fts(rowid, content, rationale, keywords) "
        "SELECT rowid, content, rationale, keywords FROM memory WHERE id = ?",
        (row["id"],),
    )
    con.commit()
    con.close()
    return row["id"]


def update_memory(id: str, fields: dict) -> None:
    """Update specific fields of an existing memory row."""
    if not fields:
        return
    fields = dict(fields)
    fields["updated_at"] = _now()
    for field in ("file_paths", "symbols", "languages", "keywords", "redaction_applied"):
        if isinstance(fields.get(field), (list, dict)):
            fields[field] = json.dumps(fields[field])
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [id]
    con = _connect()
    con.execute(f"UPDATE memory SET {set_clause} WHERE id = ?", values)
    con.commit()
    con.close()


def get_memory(id: str) -> Optional[dict]:
    """Return a memory row as dict, or None if not found."""
    con = _connect()
    row = con.execute("SELECT * FROM memory WHERE id = ?", (id,)).fetchone()
    con.close()
    return dict(row) if row else None


def get_by_claim_key(claim_key: str, status: str = "active") -> list:
    """Return all memory rows matching claim_key and status."""
    con = _connect()
    rows = con.execute(
        "SELECT * FROM memory WHERE claim_key = ? AND status = ?",
        (claim_key, status),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def count_by_status() -> dict:
    """Return {"total", "active", "superseded", "rejected"}."""
    con = _connect()
    rows = con.execute(
        "SELECT status, COUNT(*) as n FROM memory GROUP BY status"
    ).fetchall()
    con.close()
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "active": counts.get("active", 0),
        "superseded": counts.get("superseded", 0),
        "rejected": counts.get("rejected", 0),
    }


def append_vector(embedding: list) -> int:
    """Append one float32 row to .rebob/vectors.npy. Returns 0-based row index."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    vec = np.array(embedding, dtype=np.float32)
    dim = vec.shape[0]
    npy_path = _DB_DIR / "vectors.npy"

    if npy_path.exists():
        existing = np.load(str(npy_path))
        updated = np.vstack([existing, vec.reshape(1, dim)])
    else:
        updated = vec.reshape(1, dim)

    np.save(str(npy_path), updated)
    return int(updated.shape[0]) - 1
