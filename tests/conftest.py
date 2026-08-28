"""Shared pytest fixtures for ReBOB tests."""

import pytest

from rebob.core import api, store


@pytest.fixture
def rebob_tmp_home(tmp_path, monkeypatch):
    """Isolate .rebob paths under a temporary directory."""
    rebob_dir = tmp_path / ".rebob"
    monkeypatch.setattr(store, "_DB_DIR", rebob_dir)
    monkeypatch.setattr(store, "_DB_PATH", rebob_dir / "rebob.db")
    monkeypatch.setattr(api, "_REBOB_DIR", rebob_dir)
    monkeypatch.setattr(api, "_CAPTURES_DIR", rebob_dir / "captures")
    monkeypatch.setattr(api, "_SESSIONS_DIR", rebob_dir / "sessions")
    return rebob_dir


@pytest.fixture
def initialized_db(rebob_tmp_home):
    """Initialise the SQLite schema in the temporary .rebob directory."""
    store.init_db()
    return rebob_tmp_home


@pytest.fixture
def sample_event():
    """A minimal lifecycle event for record() tests."""
    return {"type": "prompt", "session_id": "sess-1", "prompt": "hello"}
