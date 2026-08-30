"""Postgres storage backend with pgvector and tsvector."""

from __future__ import annotations

import json
import os
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import numpy as np

_DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS organizations (
  id                  UUID PRIMARY KEY,
  name                TEXT NOT NULL,
  watsonx_api_key_enc TEXT,
  watsonx_project_id  TEXT,
  watsonx_url         TEXT DEFAULT 'https://us-south.ml.cloud.ibm.com',
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_tokens (
  id          UUID PRIMARY KEY,
  org_id      UUID NOT NULL REFERENCES organizations(id),
  author_id   TEXT NOT NULL DEFAULT '',
  token_hash  TEXT NOT NULL UNIQUE,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  revoked_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     UUID NOT NULL,
  session_id TEXT NOT NULL,
  events     JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_org_session ON sessions(org_id, session_id);

CREATE TABLE IF NOT EXISTS memory (
  id                TEXT PRIMARY KEY,
  org_id            UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
  claim_key         TEXT NOT NULL,
  version           INTEGER DEFAULT 1,
  supersedes        TEXT,
  status            TEXT NOT NULL,
  created_at        TIMESTAMPTZ,
  updated_at        TIMESTAMPTZ,

  memory_type       TEXT NOT NULL,
  content           TEXT NOT NULL,
  rationale         TEXT,
  counter_example   TEXT,
  snippet           TEXT,

  scope             TEXT NOT NULL,
  visibility        TEXT DEFAULT 'project',
  repo_url          TEXT,
  branch            TEXT,
  author_id         TEXT,
  file_paths        TEXT,
  symbols           TEXT,
  languages         TEXT,
  commit_sha        TEXT,
  anchor_valid      BOOLEAN DEFAULT TRUE,

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
  last_used_at      TIMESTAMPTZ,

  sensitivity       TEXT DEFAULT 'internal',
  redaction_applied TEXT,
  pinned            BOOLEAN DEFAULT FALSE,

  vector_row        INTEGER,
  embedding_id      UUID,
  keywords          TEXT,
  search_vector     tsvector
);

CREATE TABLE IF NOT EXISTS embeddings (
  id     UUID PRIMARY KEY,
  org_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
  vector vector NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_org ON memory(org_id);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory(status);
CREATE INDEX IF NOT EXISTS idx_memory_claim_key ON memory(claim_key);
CREATE INDEX IF NOT EXISTS idx_memory_search ON memory USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_embeddings_org ON embeddings(org_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PostgresBackend:
    """Hosted Postgres backend with pgvector + tsvector."""

    def __init__(self) -> None:
        self._pool = None
        self._org_id = os.environ.get("REBOB_ORG_ID", _DEFAULT_ORG_ID)

    def db_path(self):
        return os.environ.get("DATABASE_URL", "")

    def _database_url(self) -> str:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise EnvironmentError(
                "DATABASE_URL is required when REBOB_BACKEND=postgres"
            )
        return url

    def _get_pool(self):
        if self._pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            self._pool = ConnectionPool(
                self._database_url(),
                min_size=1,
                max_size=5,
                kwargs={"row_factory": dict_row, "autocommit": False},
            )
        return self._pool

    @contextmanager
    def _connection(self):
        pool = self._get_pool()
        with pool.connection() as conn:
            conn.execute(f"SET LOCAL rebob.org_id = '{self._org_id}'")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def set_org_id(self, org_id: str) -> None:
        self._org_id = org_id

    def init_db(self) -> None:
        from psycopg.rows import dict_row

        pool = self._get_pool()
        with pool.connection() as conn:
            conn.row_factory = dict_row
            conn.execute(_SCHEMA_SQL)
            conn.execute(
                """
                INSERT INTO organizations (id, name)
                VALUES (%s, 'default')
                ON CONFLICT (id) DO NOTHING
                """,
                (_DEFAULT_ORG_ID,),
            )
            self._ensure_search_vector_trigger(conn)
            self._ensure_vector_index(conn)
            self._setup_rls(conn)
            conn.commit()

    def _ensure_search_vector_trigger(self, conn) -> None:
        conn.execute(
            """
            CREATE OR REPLACE FUNCTION memory_search_vector_update() RETURNS trigger AS $$
            BEGIN
              NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.content, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.rationale, '')), 'B') ||
                setweight(to_tsvector('english', coalesce(NEW.keywords, '')), 'C');
              RETURN NEW;
            END
            $$ LANGUAGE plpgsql;
            """
        )
        conn.execute("DROP TRIGGER IF EXISTS memory_search_vector_trigger ON memory")
        conn.execute(
            """
            CREATE TRIGGER memory_search_vector_trigger
              BEFORE INSERT OR UPDATE ON memory
              FOR EACH ROW EXECUTE FUNCTION memory_search_vector_update()
            """
        )

    def _ensure_vector_index(self, conn) -> None:
        # HNSW can fail (e.g. unbounded `vector` typmod on Cloud SQL). Swallow
        # that without aborting the surrounding init transaction.
        try:
            conn.execute("SAVEPOINT vector_idx")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_embeddings_vector
                  ON embeddings USING hnsw (vector vector_cosine_ops)
                """
            )
            conn.execute("RELEASE SAVEPOINT vector_idx")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT vector_idx")

    def _setup_rls(self, conn) -> None:
        for table in ("memory", "embeddings", "sessions"):
            conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            conn.execute(
                f"""
                CREATE POLICY tenant_isolation ON {table}
                  USING (org_id = current_setting('rebob.org_id', true)::uuid)
                """
            )

    def _json_encode_fields(self, row: dict) -> dict:
        row = dict(row)
        for field in ("file_paths", "symbols", "languages", "keywords", "redaction_applied"):
            if isinstance(row.get(field), (list, dict)):
                row[field] = json.dumps(row[field])
        # SQLite historically used 0/1; Postgres BOOLEAN rejects smallint.
        for field in ("anchor_valid", "pinned"):
            if field in row and row[field] is not None:
                row[field] = bool(row[field])
        return row

    def insert_memory(self, record: dict) -> str:
        row = self._json_encode_fields(record)
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
        row.setdefault("visibility", "project")
        row.setdefault("org_id", self._org_id)
        row.setdefault("evidence_count", 1)
        row.setdefault("version", 1)
        row.setdefault("anchor_valid", True)
        row.setdefault("usefulness", 0.5)
        row.setdefault("retrieval_count", 0)
        row.setdefault("used_count", 0)
        row.setdefault("positive_signals", 0)
        row.setdefault("negative_signals", 0)
        row.setdefault("sensitivity", "internal")
        row.setdefault("pinned", False)
        row.setdefault("verification", "asserted")

        columns = list(row.keys())
        placeholders = ", ".join(f"%({c})s" for c in columns)
        col_list = ", ".join(columns)

        with self._connection() as conn:
            conn.execute(
                f"INSERT INTO memory ({col_list}) VALUES ({placeholders})",
                row,
            )
        return row["id"]

    def update_memory(self, id: str, fields: dict) -> None:
        if not fields:
            return
        fields = self._json_encode_fields(fields)
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = %({k})s" for k in fields)
        fields["id"] = id
        with self._connection() as conn:
            conn.execute(
                f"UPDATE memory SET {set_clause} WHERE id = %(id)s",
                fields,
            )

    def get_memory(self, id: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM memory WHERE id = %s", (id,)
            ).fetchone()
        return dict(row) if row else None

    def get_by_claim_key(self, claim_key: str, status: str = "active") -> list:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM memory WHERE claim_key = %s AND status = %s",
                (claim_key, status),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_by_status(self) -> dict:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM memory GROUP BY status"
            ).fetchall()
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
        vec_str = "[" + ",".join(str(float(v)) for v in vector) + "]"
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO embeddings (id, org_id, vector)
                VALUES (%s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE SET vector = EXCLUDED.vector
                """,
                (emb_id, self._org_id, vec_str),
            )
        return emb_id

    def get_embeddings(self, ids: list[str]) -> dict[str, np.ndarray]:
        if not ids:
            return {}
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id::text, vector::text AS vector FROM embeddings WHERE id::text = ANY(%s)",
                (ids,),
            ).fetchall()
        result: dict[str, np.ndarray] = {}
        for row in rows:
            text = row["vector"]
            if text.startswith("[") and text.endswith("]"):
                inner = text[1:-1].strip()
                vals = [float(x) for x in inner.split(",")] if inner else []
                result[row["id"]] = np.array(vals, dtype=np.float32)
        return result

    def vector_search(
        self,
        query_vec: np.ndarray,
        limit: int = 30,
        memory_ids: Optional[list[str]] = None,
    ) -> list[str]:
        vec_str = "[" + ",".join(str(float(v)) for v in query_vec) + "]"
        with self._connection() as conn:
            if memory_ids:
                rows = conn.execute(
                    """
                    SELECT m.id
                    FROM memory m
                    JOIN embeddings e ON e.id = m.embedding_id
                    WHERE m.status = 'active'
                      AND m.anchor_valid = TRUE
                      AND m.embedding_id IS NOT NULL
                      AND m.id = ANY(%s)
                    ORDER BY e.vector <=> %s::vector
                    LIMIT %s
                    """,
                    (memory_ids, vec_str, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT m.id
                    FROM memory m
                    JOIN embeddings e ON e.id = m.embedding_id
                    WHERE m.status = 'active'
                      AND m.anchor_valid = TRUE
                      AND m.embedding_id IS NOT NULL
                    ORDER BY e.vector <=> %s::vector
                    LIMIT %s
                    """,
                    (vec_str, limit),
                ).fetchall()
        return [r["id"] for r in rows]

    def _visibility_params(self) -> dict:
        from rebob.core.context import get_context
        from rebob.core.tenancy import normalize_repo_url

        ctx = get_context()
        return {
            "repo_url": normalize_repo_url(ctx.repo_url if ctx else ""),
            "author_id": (ctx.author_id if ctx else "") or "",
        }

    def list_active_memories(self) -> list:
        from rebob.core.tenancy import visibility_clause

        params = self._visibility_params()
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory m
                WHERE m.status = 'active' AND m.anchor_valid = TRUE
                  AND {visibility_clause('m')}
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def fts_search(self, query: str, limit: int = 30) -> list:
        from rebob.core.tenancy import visibility_clause

        tokens = query.strip().split()
        if not tokens:
            return []
        ts_query = " | ".join(tokens)
        params = {**self._visibility_params(), "ts_query": ts_query, "limit": limit}
        with self._connection() as conn:
            try:
                rows = conn.execute(
                    f"""
                    SELECT m.*
                    FROM memory m
                    WHERE m.search_vector @@ to_tsquery('english', %(ts_query)s)
                      AND m.status = 'active'
                      AND {visibility_clause('m')}
                    ORDER BY ts_rank(m.search_vector, to_tsquery('english', %(ts_query)s)) DESC
                    LIMIT %(limit)s
                    """,
                    params,
                ).fetchall()
            except Exception:
                rows = []
        return [dict(r) for r in rows]

    def increment_retrieval(self, ids: list) -> None:
        if not ids:
            return
        now = _now()
        with self._connection() as conn:
            for mid in ids:
                conn.execute(
                    """
                    UPDATE memory
                    SET retrieval_count = retrieval_count + 1, last_used_at = %s
                    WHERE id = %s
                    """,
                    (now, mid),
                )

    def update_feedback(self, id: str, verdict: str) -> None:
        with self._connection() as conn:
            if verdict == "useful":
                conn.execute(
                    """
                    UPDATE memory SET positive_signals = positive_signals + 1,
                      usefulness = CAST(positive_signals + 1 AS REAL)
                        / (positive_signals + negative_signals + 2)
                    WHERE id = %s
                    """,
                    (id,),
                )
            elif verdict == "wrong":
                conn.execute(
                    """
                    UPDATE memory SET negative_signals = negative_signals + 1,
                      usefulness = CAST(positive_signals AS REAL)
                        / (positive_signals + negative_signals + 2)
                    WHERE id = %s
                    """,
                    (id,),
                )

    def append_session_event(self, session_id: str, event: dict) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (org_id, session_id, events)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (org_id, session_id) DO UPDATE
                  SET events = sessions.events || EXCLUDED.events,
                      updated_at = NOW()
                """,
                (self._org_id, session_id, json.dumps([event])),
            )

    def get_session_events(self, session_id: str) -> list[dict]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT events FROM sessions WHERE org_id = %s AND session_id = %s",
                (self._org_id, session_id),
            ).fetchone()
        if not row:
            return []
        events = row["events"]
        if isinstance(events, str):
            return json.loads(events)
        return list(events)

    def latest_session_id(self) -> str:
        """Most recently updated session that has at least one event."""
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT session_id
                FROM sessions
                WHERE org_id = %s AND jsonb_array_length(events) > 0
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (self._org_id,),
            ).fetchone()
        return (row["session_id"] if row else "") or ""

    def truncate_all(self) -> None:
        """Test helper — wipe tenant data."""
        with self._connection() as conn:
            conn.execute("TRUNCATE memory, embeddings, sessions RESTART IDENTITY CASCADE")

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
