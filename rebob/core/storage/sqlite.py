"""SQLite storage backend with embeddings table (replaces vectors.npy)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from rebob import paths

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
  embedding_id      TEXT,
  org_id            TEXT,
  visibility        TEXT DEFAULT 'project',
  keywords          TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
  USING fts5(content, rationale, keywords, content=memory);

CREATE TABLE IF NOT EXISTS embeddings (
  id     TEXT PRIMARY KEY,
  vector BLOB NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SqliteBackend:
    """Local SQLite backend — default for single-user / offline mode."""

    def db_path(self):
        return paths.db_path()

    def _connect(self) -> sqlite3.Connection:
        paths.rebob_home().mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(paths.db_path())
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def init_db(self) -> None:
        paths.rebob_home().mkdir(parents=True, exist_ok=True)
        con = self._connect()
        con.executescript(_FULL_SCHEMA)
        self._ensure_embedding_id_column(con)
        self._ensure_tenancy_columns(con)
        con.commit()
        self._migrate_legacy_vectors(con)
        con.commit()
        con.close()

    def _ensure_embedding_id_column(self, con: sqlite3.Connection) -> None:
        cols = {row[1] for row in con.execute("PRAGMA table_info(memory)")}
        if "embedding_id" not in cols:
            con.execute("ALTER TABLE memory ADD COLUMN embedding_id TEXT")

    def _ensure_tenancy_columns(self, con: sqlite3.Connection) -> None:
        cols = {row[1] for row in con.execute("PRAGMA table_info(memory)")}
        if "org_id" not in cols:
            con.execute("ALTER TABLE memory ADD COLUMN org_id TEXT")
        if "visibility" not in cols:
            con.execute("ALTER TABLE memory ADD COLUMN visibility TEXT DEFAULT 'project'")

    def _migrate_legacy_vectors(self, con: sqlite3.Connection) -> None:
        """Migrate vectors.npy + vector_row indices to the embeddings table."""
        count = con.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        if count > 0:
            return

        npy_path = paths.vectors_path()
        if not npy_path.exists():
            return

        try:
            arr = np.load(str(npy_path))
        except Exception:
            return
        if arr.ndim != 2 or arr.shape[0] == 0:
            return

        rows = con.execute(
            "SELECT id, vector_row FROM memory WHERE vector_row IS NOT NULL"
        ).fetchall()
        row_map = {r["vector_row"]: r["id"] for r in rows if r["vector_row"] is not None}

        for idx in range(arr.shape[0]):
            emb_id = str(uuid.uuid4())
            vec = np.array(arr[idx], dtype=np.float32)
            con.execute(
                "INSERT INTO embeddings (id, vector) VALUES (?, ?)",
                (emb_id, vec.tobytes()),
            )
            if idx in row_map:
                con.execute(
                    "UPDATE memory SET embedding_id = ? WHERE id = ?",
                    (emb_id, row_map[idx]),
                )

    def insert_memory(self, record: dict) -> str:
        row = dict(record)
        if not row.get("id"):
            row["id"] = "mem_" + secrets.token_hex(4)
        if not row.get("claim_key"):
            from rebob.core.resolve import normalize_claim_key

            row["claim_key"] = normalize_claim_key(row.get("content", "")) or row["id"]
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

        for field in ("file_paths", "symbols", "languages", "keywords", "redaction_applied"):
            if isinstance(row.get(field), (list, dict)):
                row[field] = json.dumps(row[field])

        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        con = self._connect()
        con.execute(
            f"INSERT INTO memory ({columns}) VALUES ({placeholders})",
            list(row.values()),
        )
        con.execute(
            "INSERT INTO memory_fts(rowid, content, rationale, keywords) "
            "SELECT rowid, content, rationale, keywords FROM memory WHERE id = ?",
            (row["id"],),
        )
        con.commit()
        con.close()
        return row["id"]

    def update_memory(self, id: str, fields: dict) -> None:
        if not fields:
            return
        fields = dict(fields)
        fields["updated_at"] = _now()
        for field in ("file_paths", "symbols", "languages", "keywords", "redaction_applied"):
            if isinstance(fields.get(field), (list, dict)):
                fields[field] = json.dumps(fields[field])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [id]
        con = self._connect()
        con.execute(f"UPDATE memory SET {set_clause} WHERE id = ?", values)
        con.commit()
        con.close()

    def get_memory(self, id: str) -> Optional[dict]:
        con = self._connect()
        row = con.execute("SELECT * FROM memory WHERE id = ?", (id,)).fetchone()
        con.close()
        return dict(row) if row else None

    def get_by_claim_key(self, claim_key: str, status: str = "active") -> list:
        con = self._connect()
        rows = con.execute(
            "SELECT * FROM memory WHERE claim_key = ? AND status = ?",
            (claim_key, status),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def count_by_status(self) -> dict:
        con = self._connect()
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

    def store_embedding(
        self, vector: list[float], embedding_id: Optional[str] = None
    ) -> str:
        emb_id = embedding_id or str(uuid.uuid4())
        vec = np.array(vector, dtype=np.float32)
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO embeddings (id, vector) VALUES (?, ?)",
            (emb_id, vec.tobytes()),
        )
        con.commit()
        con.close()
        return emb_id

    def get_embeddings(self, ids: list[str]) -> dict[str, np.ndarray]:
        if not ids:
            return {}
        con = self._connect()
        placeholders = ", ".join("?" for _ in ids)
        rows = con.execute(
            f"SELECT id, vector FROM embeddings WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        con.close()
        result: dict[str, np.ndarray] = {}
        for row in rows:
            result[row["id"]] = np.frombuffer(row["vector"], dtype=np.float32)
        return result

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    def vector_search(
        self,
        query_vec: np.ndarray,
        limit: int = 30,
        memory_ids: Optional[list[str]] = None,
    ) -> list[str]:
        con = self._connect()
        if memory_ids:
            placeholders = ", ".join("?" for _ in memory_ids)
            rows = con.execute(
                f"""
                SELECT m.id, m.embedding_id
                FROM memory m
                WHERE m.status = 'active'
                  AND m.anchor_valid = 1
                  AND m.embedding_id IS NOT NULL
                  AND m.id IN ({placeholders})
                """,
                memory_ids,
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT m.id, m.embedding_id
                FROM memory m
                WHERE m.status = 'active'
                  AND m.anchor_valid = 1
                  AND m.embedding_id IS NOT NULL
                """
            ).fetchall()
        con.close()

        if not rows:
            return []

        emb_ids = [r["embedding_id"] for r in rows]
        id_by_emb = {r["embedding_id"]: r["id"] for r in rows}
        embeddings = self.get_embeddings(emb_ids)

        scored = []
        for emb_id, mem_id in id_by_emb.items():
            vec = embeddings.get(emb_id)
            if vec is None:
                continue
            sim = self._cosine(query_vec, vec)
            scored.append((mem_id, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in scored[:limit]]

    def list_active_memories(self) -> list:
        con = self._connect()
        rows = con.execute(
            "SELECT * FROM memory WHERE status = 'active' AND anchor_valid = 1"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def fts_search(self, query: str, limit: int = 30) -> list:
        tokens = query.strip().split()
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in tokens)
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT m.* FROM memory_fts f
                JOIN memory m ON m.rowid = f.rowid
                WHERE memory_fts MATCH ?
                  AND m.status = 'active'
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except Exception:
            rows = []
        con.close()
        return [dict(r) for r in rows]

    def increment_retrieval(self, ids: list) -> None:
        if not ids:
            return
        now = _now()
        con = self._connect()
        con.executemany(
            "UPDATE memory SET retrieval_count = retrieval_count + 1, last_used_at = ? WHERE id = ?",
            [(now, mid) for mid in ids],
        )
        con.commit()
        con.close()

    def update_feedback(self, id: str, verdict: str) -> None:
        con = self._connect()
        if verdict == "useful":
            con.execute(
                "UPDATE memory SET positive_signals = positive_signals + 1, "
                "usefulness = CAST(positive_signals + 1 AS REAL) / (positive_signals + negative_signals + 2) "
                "WHERE id = ?",
                (id,),
            )
        elif verdict == "wrong":
            con.execute(
                "UPDATE memory SET negative_signals = negative_signals + 1, "
                "usefulness = CAST(positive_signals AS REAL) / (positive_signals + negative_signals + 2) "
                "WHERE id = ?",
                (id,),
            )
        con.commit()
        con.close()

    # Legacy compat — returns embedding_id as str (was int row index)
    def append_vector(self, embedding: list) -> str:
        return self.store_embedding(embedding)

    def load_vectors(self) -> tuple:
        """Legacy: load all embeddings as a 2-D array. Prefer get_embeddings()."""
        con = self._connect()
        rows = con.execute("SELECT vector FROM embeddings ORDER BY rowid").fetchall()
        con.close()
        if not rows:
            npy_path = paths.vectors_path()
            if npy_path.exists():
                try:
                    arr = np.load(str(npy_path))
                    if arr.ndim == 2 and arr.shape[0] > 0:
                        return arr, True
                except Exception:
                    pass
            return None, False
        vecs = [np.frombuffer(r["vector"], dtype=np.float32) for r in rows]
        return np.vstack(vecs), True
