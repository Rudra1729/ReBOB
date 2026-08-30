"""Storage backend factory and module-level facade."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rebob.core.storage.protocol import StorageBackend

_backend_instance: StorageBackend | None = None


def _backend_name() -> str:
    return os.environ.get("REBOB_BACKEND", "sqlite").lower()


@lru_cache(maxsize=1)
def get_backend() -> StorageBackend:
    """Return the configured storage backend (singleton per process)."""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    name = _backend_name()
    if name == "postgres":
        from rebob.core.storage.postgres import PostgresBackend

        _backend_instance = PostgresBackend()
    else:
        from rebob.core.storage.sqlite import SqliteBackend

        _backend_instance = SqliteBackend()
    return _backend_instance


def reset_backend() -> None:
    """Clear cached backend — test-only."""
    global _backend_instance
    _backend_instance = None
    get_backend.cache_clear()


def init_db() -> None:
    get_backend().init_db()
