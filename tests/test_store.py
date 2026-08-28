"""Tests for rebob.core.store."""

import sqlite3

from rebob.core.store import db_path, init_db


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
