"""Tests for rebob.core.assemble."""

import json

from rebob.core.assemble import assemble


def write_jsonl(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestAssemble:
    def test_missing_file_returns_empty_list(self, tmp_path):
        assert assemble("sess-1", tmp_path / "nope.jsonl") == []

    def test_empty_file_returns_empty_list(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        path.write_text("", encoding="utf-8")
        assert assemble("sess-1", path) == []

    def test_orders_events_and_numbers_turns(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [
            json.dumps({"hook": "prompt", "session_id": "sess-1", "prompt": "hello"}),
            json.dumps({"hook": "tool", "session_id": "sess-1", "tool": "edit_file", "output": "ok"}),
            json.dumps({"hook": "stop", "session_id": "sess-1"}),
        ])
        transcript = assemble("sess-1", path)
        assert [e["turn"] for e in transcript] == [1, 2, 3]
        assert [e["type"] for e in transcript] == ["prompt", "tool", "stop"]

    def test_prompt_entry_carries_prompt_text(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [json.dumps({"hook": "prompt", "session_id": "sess-1", "prompt": "hello there"})])
        entry = assemble("sess-1", path)[0]
        assert entry["prompt"] == "hello there"

    def test_tool_entry_carries_tool_input_output(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [json.dumps({
            "hook": "tool", "session_id": "sess-1",
            "tool": "run_tests", "input": {"cmd": "pytest"}, "output": "2 passed",
        })])
        entry = assemble("sess-1", path)[0]
        assert entry["tool"] == "run_tests"
        assert entry["input"] == {"cmd": "pytest"}
        assert entry["output"] == "2 passed"

    def test_session_id_param_overrides_file_content(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [json.dumps({"hook": "stop", "session_id": "some-other-session"})])
        entry = assemble("sess-1", path)[0]
        assert entry["session_id"] == "sess-1"

    def test_missing_session_id_in_event_still_tagged(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [json.dumps({"hook": "tool", "tool": "x"})])
        entry = assemble("sess-1", path)[0]
        assert entry["session_id"] == "sess-1"

    def test_missing_hook_key_defaults_to_unknown_type(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [json.dumps({"session_id": "sess-1", "foo": "bar"})])
        entry = assemble("sess-1", path)[0]
        assert entry["type"] == "unknown"
        assert entry["foo"] == "bar"

    def test_malformed_json_line_is_skipped_not_raised(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [
            json.dumps({"hook": "prompt", "session_id": "sess-1", "prompt": "one"}),
            "not valid json {{{",
            json.dumps({"hook": "stop", "session_id": "sess-1"}),
        ])
        transcript = assemble("sess-1", path)
        assert [e["type"] for e in transcript] == ["prompt", "stop"]
        assert [e["turn"] for e in transcript] == [1, 2]

    def test_non_dict_json_line_is_skipped(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [
            json.dumps([1, 2, 3]),
            json.dumps({"hook": "prompt", "session_id": "sess-1", "prompt": "hi"}),
        ])
        transcript = assemble("sess-1", path)
        assert len(transcript) == 1
        assert transcript[0]["prompt"] == "hi"

    def test_blank_lines_are_skipped(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [
            json.dumps({"hook": "prompt", "session_id": "sess-1", "prompt": "hi"}),
            "",
            "   ",
            json.dumps({"hook": "stop", "session_id": "sess-1"}),
        ])
        transcript = assemble("sess-1", path)
        assert [e["turn"] for e in transcript] == [1, 2]

    def test_accepts_str_path(self, tmp_path):
        path = tmp_path / "sess.jsonl"
        write_jsonl(path, [json.dumps({"hook": "stop", "session_id": "sess-1"})])
        transcript = assemble("sess-1", str(path))
        assert len(transcript) == 1
