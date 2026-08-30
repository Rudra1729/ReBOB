"""Tests for rebob.core.store."""

import sqlite3

import numpy as np

from rebob.core.store import (
    append_vector,
    count_by_status,
    db_path,
    get_by_claim_key,
    get_memory,
    init_db,
    insert_memory,
    update_memory,
)


def test_db_path_returns_rebob_db(rebob_tmp_home):
    assert db_path() == rebob_tmp_home / "rebob.db"


def test_init_db_creates_directory(rebob_tmp_home):
    init_db()
    assert rebob_tmp_home.is_dir()


def test_init_db_creates_memory_table(initialized_db):
    con = sqlite3.connect(initialized_db / "rebob.db")
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    con.close()
    assert "memory" in tables


def test_init_db_creates_fts_table(initialized_db):
    con = sqlite3.connect(initialized_db / "rebob.db")
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    con.close()
    assert "memory_fts" in tables


def test_init_db_is_idempotent(initialized_db):
    init_db()
    init_db()


def test_insert_memory_generates_id(initialized_db):
    mem_id = insert_memory({
        "claim_key": "make setup",
        "memory_type": "env_setup",
        "content": "Run make setup first.",
        "rationale": "test",
        "scope": "repo",
        "status": "active",
    })
    assert mem_id.startswith("mem_")
    row = get_memory(mem_id)
    assert row["content"] == "Run make setup first."


def test_get_by_claim_key(initialized_db):
    insert_memory({
        "claim_key": "auth flow",
        "memory_type": "gotcha",
        "content": "Auth uses JWT.",
        "rationale": "test",
        "scope": "repo",
        "status": "active",
    })
    rows = get_by_claim_key("auth flow")
    assert len(rows) == 1


def test_update_memory(initialized_db):
    mem_id = insert_memory({
        "claim_key": "x",
        "memory_type": "gotcha",
        "content": "old",
        "rationale": "test",
        "scope": "repo",
        "status": "active",
    })
    update_memory(mem_id, {"status": "superseded"})
    row = get_memory(mem_id)
    assert row["status"] == "superseded"


def test_count_by_status(initialized_db):
    insert_memory({
        "claim_key": "a",
        "memory_type": "gotcha",
        "content": "one",
        "rationale": "test",
        "scope": "repo",
        "status": "active",
    })
    insert_memory({
        "claim_key": "b",
        "memory_type": "gotcha",
        "content": "two",
        "rationale": "test",
        "scope": "repo",
        "status": "rejected",
    })
    counts = count_by_status()
    assert counts["total"] == 2
    assert counts["active"] == 1
    assert counts["rejected"] == 1


def test_store_embedding_persists_vectors(initialized_db):
    from rebob.core.store import get_embeddings, store_embedding

    emb0 = store_embedding([1.0, 2.0, 3.0])
    emb1 = store_embedding([4.0, 5.0, 6.0])
    assert emb0 != emb1
    vecs = get_embeddings([emb0, emb1])
    assert vecs[emb0].shape == (3,)
    assert vecs[emb1].shape == (3,)


def test_append_vector_alias(initialized_db):
    emb_id = append_vector([1.0, 0.0, 0.0])
    assert isinstance(emb_id, str)
    assert len(emb_id) == 36  # UUID format
