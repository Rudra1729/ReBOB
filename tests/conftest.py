"""Shared pytest fixtures for ReBOB tests."""

import pytest

from rebob import paths
from rebob.core import store
from rebob.core.storage import reset_backend


@pytest.fixture
def rebob_tmp_home(tmp_path, monkeypatch):
    """Isolate .rebob paths under a temporary directory.

    Sets REBOB_HOME so every module that resolves paths via rebob.paths
    (store, api, retrieve, watsonx) lands in the same temp directory —
    no more per-module monkeypatching of separate path constants.
    """
    rebob_dir = tmp_path / ".rebob"
    monkeypatch.setenv("REBOB_HOME", str(rebob_dir))
    monkeypatch.setenv("REBOB_BACKEND", "sqlite")
    paths.reset_cache()
    reset_backend()
    yield rebob_dir
    paths.reset_cache()
    reset_backend()


@pytest.fixture(params=["sqlite"])
def backend_name(request):
    """Parametrize backend tests — postgres added in Phase 3."""
    return request.param


@pytest.fixture
def initialized_db(rebob_tmp_home):
    """Initialise the SQLite schema in the temporary .rebob directory."""
    store.init_db()
    return rebob_tmp_home


@pytest.fixture
def sample_event():
    """A minimal lifecycle event for record() tests."""
    return {"type": "prompt", "session_id": "sess-1", "prompt": "hello"}
