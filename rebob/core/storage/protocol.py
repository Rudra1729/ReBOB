"""StorageBackend protocol — abstract interface for ReBOB persistence."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class StorageBackend(Protocol):
    """Persistence layer covering memory rows, embeddings, and search."""

    def init_db(self) -> None: ...

    def insert_memory(self, record: dict) -> str: ...

    def update_memory(self, id: str, fields: dict) -> None: ...

    def get_memory(self, id: str) -> Optional[dict]: ...

    def get_by_claim_key(self, claim_key: str, status: str = "active") -> list: ...

    def count_by_status(self) -> dict: ...

    def list_active_memories(self) -> list: ...

    def fts_search(self, query: str, limit: int = 30) -> list: ...

    def store_embedding(
        self, vector: list[float], embedding_id: Optional[str] = None
    ) -> str: ...

    def get_embeddings(self, ids: list[str]) -> dict[str, np.ndarray]: ...

    def vector_search(
        self,
        query_vec: np.ndarray,
        limit: int = 30,
        memory_ids: Optional[list[str]] = None,
    ) -> list[str]: ...

    def increment_retrieval(self, ids: list) -> None: ...

    def update_feedback(self, id: str, verdict: str) -> None: ...

    def db_path(self): ...
