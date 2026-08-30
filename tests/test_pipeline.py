"""Integration-style tests for the write path (watsonx mocked)."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from rebob.core import store
from rebob.core.worker import process_session

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_JSONL = FIXTURES / "sample_session.jsonl"

MOCK_EXTRACT_RESPONSE = [
    {
        "memory_type": "env_setup",
        "content": "Run make setup before make start on Galaxium.",
        "rationale": "make start failed with ModuleNotFoundError until make setup ran.",
        "confidence": 0.92,
        "file_paths": ["Makefile"],
        "keywords": ["make", "setup", "galaxium"],
        "volatility": "durable",
    },
    {
        "memory_type": "failure_mode",
        "content": "Skipping make setup leaves the venv incomplete.",
        "rationale": "Observed in run_command output during session.",
        "confidence": 0.85,
        "keywords": ["venv"],
        "volatility": "durable",
    },
]


@pytest.fixture
def session_jsonl(rebob_tmp_home):
    sessions_dir = rebob_tmp_home / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    dest = sessions_dir / "fixture-session-001.jsonl"
    dest.write_text(SAMPLE_JSONL.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


class TestPipeline:
    def test_process_session_not_found(self, rebob_tmp_home):
        result = process_session("missing-session")
        assert result.get("error") == "session not found"

    def test_full_pipeline_with_mocked_extract(self, session_jsonl, initialized_db):
        llm_json = json.dumps(MOCK_EXTRACT_RESPONSE)
        with patch("rebob.core.watsonx.generate", return_value=llm_json), patch(
            "rebob.core.watsonx.embed", return_value=[0.1] * 8
        ):
            result = process_session("fixture-session-001", explicit=True)

        assert result["added"] >= 1
        assert len(result["ids"]) >= 1
        stats = store.count_by_status()
        assert stats["active"] >= 1

    def test_no_secrets_in_stored_content(self, session_jsonl, initialized_db):
        secret_line = (
            '{"hook":"tool","tool_response":"key=abc123longfakekeyvalue12345678901234567890",'
            '"tool_name":"run_command"}'
        )
        path = session_jsonl
        path.write_text(path.read_text(encoding="utf-8") + "\n" + secret_line, encoding="utf-8")

        llm_json = json.dumps([{
            "memory_type": "gotcha",
            "content": "Never log raw command output containing secrets.",
            "rationale": "Session had tool output with a key-like string.",
            "confidence": 0.9,
            "keywords": ["security"],
            "volatility": "durable",
        }])
        with patch("rebob.core.watsonx.generate", return_value=llm_json), patch(
            "rebob.core.watsonx.embed", return_value=[0.2] * 8
        ):
            process_session("fixture-session-001", explicit=True)

        con = sqlite3.connect(store.db_path())
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT content, rationale FROM memory").fetchall()
        con.close()
        for row in rows:
            assert "abc123longfakekeyvalue" not in (row["content"] or "")
            assert "abc123longfakekeyvalue" not in (row["rationale"] or "")
