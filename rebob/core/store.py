"""
rebob/core/store.py — Facade over StorageBackend.

All callers import from here; the actual backend is selected via
REBOB_BACKEND=sqlite|postgres (default: sqlite).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from rebob.core.storage import get_backend, init_db as _init_db


def db_path():
    return get_backend().db_path()


def init_db() -> None:
    _init_db()


def insert_memory(record: dict) -> str:
    return get_backend().insert_memory(record)


def update_memory(id: str, fields: dict) -> None:
    get_backend().update_memory(id, fields)


def get_memory(id: str) -> Optional[dict]:
    return get_backend().get_memory(id)


def get_by_claim_key(claim_key: str, status: str = "active") -> list:
    return get_backend().get_by_claim_key(claim_key, status)


def count_by_status() -> dict:
    return get_backend().count_by_status()


def store_embedding(vector: list[float], embedding_id: Optional[str] = None) -> str:
    return get_backend().store_embedding(vector, embedding_id)


def get_embeddings(ids: list[str]) -> dict[str, np.ndarray]:
    return get_backend().get_embeddings(ids)


def vector_search(
    query_vec: np.ndarray,
    limit: int = 30,
    memory_ids: Optional[list[str]] = None,
) -> list[str]:
    return get_backend().vector_search(query_vec, limit=limit, memory_ids=memory_ids)


def append_vector(embedding: list) -> str:
    """Legacy alias — returns embedding_id (UUID string)."""
    return get_backend().store_embedding(embedding)


def load_vectors() -> tuple:
    """Legacy — returns (array, exists_flag). Prefer get_embeddings()."""
    backend = get_backend()
    if hasattr(backend, "load_vectors"):
        return backend.load_vectors()
    return None, False


def list_active_memories() -> list:
    return get_backend().list_active_memories()


def fts_search(query: str, limit: int = 30) -> list:
    return get_backend().fts_search(query, limit=limit)


def increment_retrieval(ids: list) -> None:
    get_backend().increment_retrieval(ids)


def update_feedback(id: str, verdict: str) -> None:
    get_backend().update_feedback(id, verdict)
