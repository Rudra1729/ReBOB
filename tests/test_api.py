"""Tests for rebob.core.api."""

import json

import pytest

from rebob.core import api


class TestMemSearch:
    def test_returns_markdown_header(self, rebob_tmp_home):
        result = api.mem_search("auth flow")
        assert result.startswith("## ReBOB Memory Brief")

    def test_contains_mem_001_and_mem_002(self, rebob_tmp_home):
        result = api.mem_search("anything")
        assert "mem_001" in result
        assert "mem_002" in result

    def test_ignores_query_for_stub(self, rebob_tmp_home):
        assert api.mem_search("query-a") == api.mem_search("query-b")


class TestMemCapture:
    def test_returns_error_when_no_session(self, rebob_tmp_home):
        result = api.mem_capture()
        assert result["added"] == 0
        assert result.get("error") == "no session found"

    def test_delegates_to_worker(self, rebob_tmp_home, monkeypatch):
        sessions_dir = rebob_tmp_home / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "s1.jsonl").write_text(
            '{"hook":"prompt","session_id":"s1","prompt":"hi"}\n',
            encoding="utf-8",
        )
        expected = {"added": 2, "updated": 0, "rejected": 0, "ids": ["mem_a", "mem_b"]}
        monkeypatch.setattr(
            "rebob.core.worker.process_session",
            lambda sid, **kw: expected if sid == "s1" else {},
        )
        result = api.mem_capture(session_id="s1", label="test", summary="note")
        assert result == expected

    def test_uses_latest_session_when_id_empty(self, rebob_tmp_home, monkeypatch):
        sessions_dir = rebob_tmp_home / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "older.jsonl").write_text('{"hook":"prompt"}\n', encoding="utf-8")
        (sessions_dir / "newer.jsonl").write_text('{"hook":"prompt"}\n', encoding="utf-8")
        captured = {}

        def fake_process(sid, **kw):
            captured["session_id"] = sid
            return {"added": 1, "updated": 0, "rejected": 0, "ids": ["mem_x"]}

        monkeypatch.setattr("rebob.core.worker.process_session", fake_process)
        api.mem_capture()
        assert captured["session_id"] == "newer"


class TestMemStats:
    def test_returns_expected_keys(self, rebob_tmp_home):
        result = api.mem_stats()
        assert set(result.keys()) == {"total", "active", "superseded", "rejected"}

    def test_returns_all_zeros(self, rebob_tmp_home):
        result = api.mem_stats()
        assert all(result[k] == 0 for k in result)


class TestMemWhy:
    def test_returns_correct_id(self, rebob_tmp_home):
        result = api.mem_why("mem_abc")
        assert result["id"] == "mem_abc"

    def test_returns_stub_content(self, rebob_tmp_home):
        result = api.mem_why("mem_abc")
        assert result["content"] == "stub — not implemented yet"

    def test_returns_empty_provenance(self, rebob_tmp_home):
        result = api.mem_why("mem_abc")
        assert result["provenance"] == []


class TestMemFeedback:
    @pytest.mark.parametrize("verdict", ["useful", "wrong"])
    def test_returns_ok_with_verdict(self, rebob_tmp_home, verdict):
        result = api.mem_feedback("mem_001", verdict)
        assert result == {"ok": True, "id": "mem_001", "verdict": verdict}


class TestSearch:
    def test_returns_same_brief_as_mem_search(self, rebob_tmp_home):
        assert api.search("hello", session_id="sess-1") == api.mem_search("hello")


class TestRecord:
    def test_appends_jsonl_line(self, rebob_tmp_home, sample_event):
        api.record(sample_event)
        path = rebob_tmp_home / "sessions" / "sess-1.jsonl"
        assert path.exists()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == sample_event

    def test_appends_multiple_events(self, rebob_tmp_home, sample_event):
        api.record(sample_event)
        api.record({**sample_event, "prompt": "world"})
        path = rebob_tmp_home / "sessions" / "sess-1.jsonl"
        assert len(path.read_text().strip().splitlines()) == 2

    def test_uses_unknown_session_when_missing(self, rebob_tmp_home):
        api.record({"type": "tool", "tool": "read"})
        path = rebob_tmp_home / "sessions" / "unknown.jsonl"
        assert path.exists()
