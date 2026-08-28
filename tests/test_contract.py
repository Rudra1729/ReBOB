"""Smoke tests that contract.py delegates to api implementations."""

from rebob import contract


def test_mem_search_returns_non_empty_brief():
    assert contract.mem_search("q")


def test_mem_capture_returns_counts_dict():
    result = contract.mem_capture(session_id="s", label="l", summary="s")
    assert "added" in result and "ids" in result


def test_mem_stats_returns_counts():
    assert contract.mem_stats()["total"] == 0


def test_mem_why_returns_stub_content():
    assert contract.mem_why("id-1")["content"]


def test_mem_feedback_returns_ok():
    assert contract.mem_feedback("id-1", "useful")["ok"] is True


def test_search_returns_non_empty_brief():
    assert contract.search("q", session_id="s")


def test_record_writes_session_file(rebob_tmp_home, sample_event):
    contract.record(sample_event)
    assert (rebob_tmp_home / "sessions" / "sess-1.jsonl").exists()
