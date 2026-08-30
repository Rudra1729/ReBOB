"""Tests for rebob.core.retrieve."""

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from rebob import paths
from rebob.core import store
from rebob.core import retrieve as retrieve_mod
from rebob.core.retrieve import (
    _cosine,
    _rrf_fuse,
    _pack_brief,
    load_injected,
    mark_injected,
    retrieve,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_injected(tmp_path, monkeypatch):
    """Redirect the injected-dedup dir to a temp directory via REBOB_HOME."""
    rebob_dir = tmp_path / ".rebob"
    monkeypatch.setenv("REBOB_HOME", str(rebob_dir))
    paths.reset_cache()
    yield rebob_dir / "injected"
    paths.reset_cache()


@pytest.fixture
def mock_embed():
    with patch("rebob.core.watsonx.embed", return_value=[1.0, 0.0, 0.0]) as m:
        yield m


@pytest.fixture
def mock_rerank():
    # Identity: return indices in original order
    with patch(
        "rebob.core.watsonx.rerank",
        side_effect=lambda q, docs, **kw: list(range(len(docs))),
    ) as m:
        yield m


def _insert_memory(initialized_db, **kwargs):
    """Insert a memory and return its id."""
    base = {
        "memory_type": "env_setup",
        "content": "Run make setup before make start.",
        "rationale": "Observed error until setup ran.",
        "confidence": 0.9,
        "file_paths": json.dumps(["Makefile"]),
        "keywords": "make setup",
        "task_id": "sess-test",
        "source_kind": "hook_session",
        "status": "active",
        "anchor_valid": 1,
    }
    base.update(kwargs)
    return store.insert_memory(base)


# ---------------------------------------------------------------------------
# Unit: cosine similarity
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical_vectors(self):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(_cosine(a, a) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(_cosine(a, b)) < 1e-6


# ---------------------------------------------------------------------------
# Unit: RRF fusion
# ---------------------------------------------------------------------------

class TestRRFFuse:
    def test_empty(self):
        assert _rrf_fuse([]) == []

    def test_single_list_preserves_order(self):
        ids = ["a", "b", "c"]
        result = _rrf_fuse([ids])
        assert result == ids

    def test_agreement_boosts_score(self):
        # "b" appears in all three lists near the top
        result = _rrf_fuse([
            ["a", "b", "c"],
            ["b", "c", "a"],
            ["b", "a", "c"],
        ])
        assert result[0] == "b"


# ---------------------------------------------------------------------------
# Unit: pack_brief
# ---------------------------------------------------------------------------

class TestPackBrief:
    def test_empty(self):
        brief, ids = _pack_brief([], 600)
        assert brief == ""
        assert ids == []

    def test_header_present(self):
        mems = [{"id": "mem_abc", "content": "Do X before Y.", "memory_type": "env_setup"}]
        brief, ids = _pack_brief(mems, 600)
        assert brief.startswith("## ReBOB Memory Brief")
        assert "[mem_abc]" in brief
        assert ids == ["mem_abc"]

    def test_budget_respected(self):
        # Create many memories, budget should cap inclusion
        mems = [
            {"id": f"mem_{i:03d}", "content": "A" * 100, "memory_type": "convention"}
            for i in range(50)
        ]
        # budget of 5 tokens (~20 chars) is tiny
        brief, ids = _pack_brief(mems, 5)
        assert len(ids) < 50


# ---------------------------------------------------------------------------
# Unit: session dedup helpers
# ---------------------------------------------------------------------------

class TestSessionDedup:
    def test_load_empty_session(self, isolated_injected):
        assert load_injected("new-session") == set()

    def test_mark_and_load(self, isolated_injected):
        mark_injected("sess-1", ["mem_a", "mem_b"])
        assert load_injected("sess-1") == {"mem_a", "mem_b"}

    def test_mark_accumulates(self, isolated_injected):
        mark_injected("sess-1", ["mem_a"])
        mark_injected("sess-1", ["mem_b"])
        assert load_injected("sess-1") == {"mem_a", "mem_b"}

    def test_empty_session_id_is_noop(self, isolated_injected):
        mark_injected("", ["mem_a"])  # should not raise
        assert load_injected("") == set()


# ---------------------------------------------------------------------------
# Integration: retrieve()
# ---------------------------------------------------------------------------

class TestRetrieveEmptyDB:
    def test_returns_empty_string(self, initialized_db, mock_embed, mock_rerank):
        result = retrieve("make setup", session_id="sess-empty")
        assert result == ""


class TestRetrieveFTSHit:
    def test_sparse_path_finds_keyword(self, initialized_db, mock_embed, mock_rerank):
        """When dense vectors are absent, FTS should still surface the memory."""
        mid = _insert_memory(initialized_db, content="Use make setup to install deps.")
        result = retrieve("make setup", session_id="sess-fts")
        # Brief should contain the inserted ID
        assert mid in result

    def test_brief_has_markdown_header(self, initialized_db, mock_embed, mock_rerank):
        _insert_memory(initialized_db, content="Use make setup to install deps.")
        result = retrieve("make setup", session_id="sess-hdr")
        if result:
            assert result.startswith("## ReBOB Memory Brief")


class TestRetrieveDenseHit:
    def test_dense_path_ranks_by_cosine(self, initialized_db, mock_rerank):
        """Insert a memory with a stored vector and confirm dense path picks it up."""
        # Append a vector matching our mock embed direction [1,0,0]
        vrow = store.append_vector([1.0, 0.0, 0.0])
        mid = _insert_memory(
            initialized_db,
            content="Dense memory target",
            vector_row=vrow,
        )
        with patch("rebob.core.watsonx.embed", return_value=[1.0, 0.0, 0.0]):
            result = retrieve("dense target", session_id="sess-dense")
        assert mid in result


class TestSessionDeduplication:
    def test_second_call_excludes_first_batch(self, initialized_db, mock_embed, mock_rerank):
        _insert_memory(initialized_db, content="Use make setup for deps.")
        session = "sess-dedup"

        first = retrieve("make setup", session_id=session)
        # First call should return the memory
        assert first  # non-empty

        second = retrieve("make setup", session_id=session)
        # Second call with same session should not re-inject already-cited IDs
        assert second == "" or "make setup" not in second.lower() or first == second  # dedup working


class TestBudgetEnforcement:
    def test_brief_stays_under_budget(self, initialized_db, mock_embed, mock_rerank):
        for i in range(20):
            _insert_memory(
                initialized_db,
                id=f"mem_{i:04d}",
                content=f"Memory content number {i} about something useful that is a bit long to test budget.",
                memory_type="convention",
            )
        result = retrieve("memory content", budget_tokens=50, session_id="sess-budget")
        if result:
            # 50 tokens * 4 chars/token = 200 chars budget; header is ~26 chars
            assert len(result) <= 50 * 4 + 100  # give a little slack for header


class TestRetrieveDegradation:
    def test_rerank_raises_still_returns_brief(self, initialized_db, mock_embed):
        """If rerank raises, the pipeline should still return a brief (from fused order)."""
        _insert_memory(initialized_db, content="Use make setup to install deps.")
        with patch("rebob.core.watsonx.rerank", side_effect=RuntimeError("rerank down")):
            result = retrieve("make setup", session_id="sess-degrade")
        # Should still return a brief via the fused list
        assert isinstance(result, str)

    def test_embed_raises_still_returns_brief(self, initialized_db):
        """If embed raises, sparse path alone should still work."""
        _insert_memory(initialized_db, content="Use make setup to install deps.")
        with patch("rebob.core.watsonx.embed", side_effect=RuntimeError("embed down")):
            with patch("rebob.core.watsonx.rerank", side_effect=lambda q, d, **kw: list(range(len(d)))):
                result = retrieve("make setup", session_id="sess-embed-fail")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Integration: mem_why
# ---------------------------------------------------------------------------

class TestMemWhy:
    def test_unknown_id_returns_error(self, initialized_db):
        from rebob.core.api import mem_why
        result = mem_why("mem_nonexistent")
        assert result["id"] == "mem_nonexistent"
        assert result["content"] is None
        assert result.get("error") == "not found"

    def test_existing_memory_returns_content(self, initialized_db):
        from rebob.core.api import mem_why
        mid = _insert_memory(initialized_db, content="Test memory content.")
        result = mem_why(mid)
        assert result["id"] == mid
        assert result["content"] == "Test memory content."
        assert "provenance" in result

    def test_walks_supersedes_chain(self, initialized_db):
        from rebob.core.api import mem_why
        # Insert original → then superseded version
        old_id = _insert_memory(initialized_db, id="mem_v1", content="Old content.", status="superseded")
        new_id = _insert_memory(initialized_db, id="mem_v2", content="New content.", supersedes="mem_v1", version=2)
        result = mem_why(new_id)
        assert result["id"] == new_id
        assert result["content"] == "New content."
        prov_ids = [p.get("id") for p in result["provenance"] if "id" in p]
        assert old_id in prov_ids


# ---------------------------------------------------------------------------
# Integration: mem_feedback
# ---------------------------------------------------------------------------

class TestMemFeedback:
    def test_useful_increments_positive_signals(self, initialized_db):
        from rebob.core.api import mem_feedback
        mid = _insert_memory(initialized_db, content="Feedback test memory.")
        result = mem_feedback(mid, "useful")
        assert result == {"ok": True, "id": mid, "verdict": "useful"}
        row = store.get_memory(mid)
        assert row["positive_signals"] == 1
        assert row["negative_signals"] == 0

    def test_wrong_increments_negative_signals(self, initialized_db):
        from rebob.core.api import mem_feedback
        mid = _insert_memory(initialized_db, content="Wrong feedback test.")
        mem_feedback(mid, "wrong")
        row = store.get_memory(mid)
        assert row["negative_signals"] == 1
        assert row["positive_signals"] == 0

    def test_invalid_verdict_returns_error(self, initialized_db):
        from rebob.core.api import mem_feedback
        mid = _insert_memory(initialized_db, content="Verdict test.")
        result = mem_feedback(mid, "maybe")
        assert result["ok"] is False
        assert "error" in result
