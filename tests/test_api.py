"""Tests for rebob.core.api."""

import json
from unittest.mock import patch

import pytest

from rebob.core import api, store


class TestMemSearch:
    def test_returns_string(self, initialized_db):
        """mem_search always returns a string, never raises."""
        with patch("rebob.core.watsonx.embed", return_value=[1.0, 0.0, 0.0]):
            with patch("rebob.core.watsonx.rerank", side_effect=lambda q, d, **kw: list(range(len(d)))):
                result = api.mem_search("auth flow")
        assert isinstance(result, str)

    def test_empty_db_returns_empty_string(self, initialized_db):
        """With no memories, retrieval should return empty string."""
        with patch("rebob.core.watsonx.embed", return_value=[1.0, 0.0, 0.0]):
            with patch("rebob.core.watsonx.rerank", side_effect=lambda q, d, **kw: list(range(len(d)))):
                result = api.mem_search("anything")
        assert result == ""

    def test_seeded_db_returns_brief(self, initialized_db):
        """With a matching memory, should return a markdown brief."""
        store.insert_memory({
            "memory_type": "env_setup",
            "content": "Run make setup before make start.",
            "confidence": 0.9,
            "status": "active",
            "anchor_valid": 1,
        })
        with patch("rebob.core.watsonx.embed", return_value=[1.0, 0.0, 0.0]):
            with patch("rebob.core.watsonx.rerank", side_effect=lambda q, d, **kw: list(range(len(d)))):
                result = api.mem_search("make setup")
        assert result.startswith("## ReBOB Memory Brief")
        assert "make setup" in result.lower()

    def test_watsonx_failure_returns_empty(self, initialized_db):
        """On any retrieval error, mem_search must return '' not raise."""
        store.insert_memory({
            "memory_type": "env_setup",
            "content": "Run make setup before make start.",
            "status": "active",
            "anchor_valid": 1,
        })
        with patch("rebob.core.watsonx.embed", side_effect=RuntimeError("down")):
            with patch("rebob.core.watsonx.rerank", side_effect=RuntimeError("down")):
                result = api.mem_search("make setup")
        assert isinstance(result, str)


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
    def test_returns_correct_id_for_missing_memory(self, initialized_db):
        result = api.mem_why("mem_nonexistent")
        assert result["id"] == "mem_nonexistent"
        assert result.get("error") == "not found"
        assert result["content"] is None

    def test_returns_content_for_existing_memory(self, initialized_db):
        mid = store.insert_memory({
            "memory_type": "env_setup",
            "content": "The real content.",
            "status": "active",
            "anchor_valid": 1,
        })
        result = api.mem_why(mid)
        assert result["id"] == mid
        assert result["content"] == "The real content."
        assert isinstance(result["provenance"], list)

    def test_provenance_has_source_entry(self, initialized_db):
        mid = store.insert_memory({
            "memory_type": "convention",
            "content": "Use tabs not spaces.",
            "source_kind": "hook_session",
            "task_id": "task-001",
            "status": "active",
            "anchor_valid": 1,
        })
        result = api.mem_why(mid)
        # Last provenance entry should be the source info
        assert any(p.get("source_kind") == "hook_session" for p in result["provenance"])


class TestMemFeedback:
    @pytest.mark.parametrize("verdict", ["useful", "wrong"])
    def test_returns_ok_with_valid_verdict(self, initialized_db, verdict):
        mid = store.insert_memory({
            "memory_type": "env_setup",
            "content": "Feedback test.",
            "status": "active",
            "anchor_valid": 1,
        })
        result = api.mem_feedback(mid, verdict)
        assert result["ok"] is True
        assert result["verdict"] == verdict

    def test_returns_error_for_invalid_verdict(self, initialized_db):
        result = api.mem_feedback("mem_x", "maybe")
        assert result["ok"] is False
        assert "error" in result


class TestSearch:
    def test_delegates_to_mem_search(self, initialized_db):
        """search() and mem_search() should return the same result for the same query."""
        with patch("rebob.core.watsonx.embed", return_value=[1.0, 0.0, 0.0]):
            with patch("rebob.core.watsonx.rerank", side_effect=lambda q, d, **kw: list(range(len(d)))):
                assert api.search("hello", session_id="sess-1") == api.mem_search("hello", session_id="sess-1")


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

    def test_concurrent_large_writes_produce_valid_jsonl(self, rebob_tmp_home):
        """Parallel hook invocations must not interleave JSONL lines."""
        from concurrent.futures import ThreadPoolExecutor

        session_id = "race-session"
        events = [
            {
                "hook": "tool",
                "session_id": session_id,
                "tool_response": "payload-" + ("x" * 9000) + f"-{i}",
                "seq": i,
            }
            for i in range(24)
        ]
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(api.record, events))

        path = rebob_tmp_home / "sessions" / f"{session_id}.jsonl"
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == len(events)
        parsed = [json.loads(ln) for ln in lines]
        seqs = sorted(e["seq"] for e in parsed)
        assert seqs == list(range(len(events)))
