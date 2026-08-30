"""Dual-backend store tests (SQLite always; Postgres when DATABASE_URL set)."""

import os
import uuid

import pytest

from rebob.core import store
from rebob.core.storage import reset_backend


def _postgres_available() -> bool:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://rebob:rebob@localhost:5433/rebob",
    )
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


POSTGRES_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://rebob:rebob@localhost:5433/rebob",
)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(
    not _postgres_available(), reason="Postgres not available"
))])
def any_backend(request, tmp_path, monkeypatch):
    """Run store tests against sqlite and optionally postgres."""
    reset_backend()
    if request.param == "sqlite":
        rebob_dir = tmp_path / ".rebob"
        monkeypatch.setenv("REBOB_HOME", str(rebob_dir))
        monkeypatch.setenv("REBOB_BACKEND", "sqlite")
    else:
        org_id = str(uuid.uuid4())
        monkeypatch.setenv("REBOB_BACKEND", "postgres")
        monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
        monkeypatch.setenv("REBOB_ORG_ID", org_id)
        from rebob.core.storage import get_backend

        pg = get_backend()
        pg.set_org_id(org_id)
        pg.init_db()
        with pg._get_pool().connection() as conn:
            conn.execute(
                "INSERT INTO organizations (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (org_id, f"test-{org_id[:8]}"),
            )
            conn.commit()
        pg.truncate_all()

    from rebob import paths

    paths.reset_cache()
    store.init_db()
    yield request.param
    reset_backend()
    paths.reset_cache()
    if request.param == "postgres":
        from rebob.core.storage import get_backend

        get_backend().close()


def test_insert_and_fetch_memory(any_backend):
    mem_id = store.insert_memory({
        "claim_key": "setup flow",
        "memory_type": "env_setup",
        "content": "Run make setup first.",
        "rationale": "test",
        "scope": "repo",
        "status": "active",
    })
    row = store.get_memory(mem_id)
    assert row["content"] == "Run make setup first."


def test_store_embedding_and_search(any_backend):
    emb_id = store.store_embedding([1.0, 0.0, 0.0])
    mem_id = store.insert_memory({
        "claim_key": "dense",
        "memory_type": "gotcha",
        "content": "Dense target memory.",
        "rationale": "test",
        "scope": "repo",
        "status": "active",
        "embedding_id": emb_id,
    })
    import numpy as np

    hits = store.vector_search(np.array([1.0, 0.0, 0.0], dtype=np.float32), limit=5)
    assert mem_id in hits


def test_fts_search_finds_content(any_backend):
    store.insert_memory({
        "claim_key": "auth",
        "memory_type": "gotcha",
        "content": "Authentication uses bearer tokens exclusively.",
        "rationale": "security note",
        "scope": "repo",
        "status": "active",
        "keywords": "auth bearer",
    })
    rows = store.fts_search("authentication bearer", limit=5)
    assert len(rows) >= 1
