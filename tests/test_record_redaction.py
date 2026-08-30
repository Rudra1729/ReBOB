"""End-to-end tests: secrets never persist through record()."""

import json

from rebob.core import api


class TestRecordRedaction:
    def test_secret_never_in_jsonl(self, rebob_tmp_home):
        secret = "IBM_CLOUD_API_KEY=sk-secret-value-that-must-not-persist-12345"
        event = {
            "hook": "tool",
            "session_id": "redact-test",
            "tool_name": "run_command",
            "tool_response": f"output with {secret} embedded",
        }
        api.record(event)

        path = rebob_tmp_home / "sessions" / "redact-test.jsonl"
        content = path.read_text(encoding="utf-8")
        assert "sk-secret-value-that-must-not-persist" not in content
        assert "IBM_CLOUD_API_KEY=" not in content or "[REDACTED" in content

        parsed = json.loads(content.strip())
        assert secret not in parsed.get("tool_response", "")

    def test_unknown_fields_dropped(self, rebob_tmp_home):
        event = {
            "hook": "tool",
            "session_id": "allowlist-test",
            "tool_response": "ok",
            "internal_debug_blob": "should not persist",
            "user_home_path": "/Users/secret/home",
        }
        api.record(event)

        path = rebob_tmp_home / "sessions" / "allowlist-test.jsonl"
        parsed = json.loads(path.read_text(encoding="utf-8").strip())
        assert "internal_debug_blob" not in parsed
        assert "user_home_path" not in parsed
        assert parsed["tool_response"] == "ok"
