"""Tests for rebob.core.worker path resolution and session processing."""

from rebob.core import store
from rebob.core.worker import _pending_dir, _sessions_dir, process_session


class TestWorkerPaths:
    def test_sessions_dir_without_db_dir_override(self, tmp_path, monkeypatch):
        """Production installs leave store._DB_DIR as None — paths must still resolve."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(store, "_DB_DIR", None)
        monkeypatch.setattr(store, "_DB_PATH", None)

        expected = (tmp_path / ".rebob" / "sessions").resolve()
        assert _sessions_dir() == expected
        assert _pending_dir() == (tmp_path / ".rebob" / "pending").resolve()

    def test_process_session_finds_jsonl_without_db_dir_override(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(store, "_DB_DIR", None)
        monkeypatch.setattr(store, "_DB_PATH", None)

        sessions = tmp_path / ".rebob" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "sess-1.jsonl").write_text(
            '{"hook":"prompt","session_id":"sess-1","prompt":"hello"}\n',
            encoding="utf-8",
        )

        monkeypatch.setattr("rebob.core.extract.extract", lambda *a, **k: [])
        monkeypatch.setattr(
            "rebob.core.resolve.resolve",
            lambda records: {"added": 0, "updated": 0, "rejected": 0, "ids": []},
        )

        result = process_session("sess-1", explicit=True)
        assert "error" not in result
        assert result["added"] == 0
