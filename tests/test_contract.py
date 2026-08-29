"""Smoke tests that contract.py delegates to api implementations."""

from rebob import contract


def test_mem_search_returns_string(rebob_tmp_home):
    result = contract.mem_search("q")
    assert isinstance(result, str)


def test_mem_capture_returns_counts_dict(rebob_tmp_home):
    result = contract.mem_capture(session_id="s", label="l", summary="s")
    assert "added" in result and "ids" in result


def test_mem_stats_returns_counts(initialized_db):
    assert contract.mem_stats()["total"] == 0


def test_mem_why_missing_id_returns_not_found(initialized_db):
    result = contract.mem_why("id-1")
    assert result["id"] == "id-1"
    assert result.get("error") == "not found"
    assert result["content"] is None


def test_mem_feedback_returns_ok(initialized_db):
    assert contract.mem_feedback("id-1", "useful")["ok"] is True


def test_search_returns_string(rebob_tmp_home):
    result = contract.search("q", session_id="s")
    assert isinstance(result, str)


def test_record_writes_session_file(rebob_tmp_home, sample_event):
    contract.record(sample_event)
    assert (rebob_tmp_home / "sessions" / "sess-1.jsonl").exists()
