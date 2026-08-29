"""Tests for rebob.core.extract."""

import json
from unittest.mock import patch

import pytest

from rebob.core.extract import (
    SALIENCE_THRESHOLD,
    extract,
    validate_records,
    _parse_json_array,
)


SAMPLE_LLM_RESPONSE = json.dumps([
    {
        "memory_type": "env_setup",
        "content": "Run make setup before make start.",
        "rationale": "make start failed until setup was run.",
        "confidence": 0.9,
        "file_paths": ["Makefile"],
        "keywords": ["make", "setup"],
        "volatility": "durable",
    },
    {
        "memory_type": "gotcha",
        "content": "Low confidence claim.",
        "rationale": "uncertain",
        "confidence": 0.2,
    },
    {
        "memory_type": "invalid_type",
        "content": "Bad type.",
        "rationale": "test",
        "confidence": 0.9,
    },
])


class TestValidateRecords:
    def test_keeps_valid_record(self):
        raw = [json.loads(SAMPLE_LLM_RESPONSE)[0]]
        result = validate_records(raw)
        assert len(result) == 1
        assert result[0]["memory_type"] == "env_setup"

    def test_drops_low_confidence(self):
        raw = json.loads(SAMPLE_LLM_RESPONSE)
        result = validate_records(raw)
        assert len(result) == 1
        assert result[0]["content"] == "Run make setup before make start."

    def test_drops_invalid_memory_type(self):
        raw = [json.loads(SAMPLE_LLM_RESPONSE)[2]]
        result = validate_records(raw)
        assert result == []


class TestParseJsonArray:
    def test_parses_plain_json(self):
        assert len(_parse_json_array(SAMPLE_LLM_RESPONSE)) == 3

    def test_parses_markdown_fenced_json(self):
        fenced = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        assert len(_parse_json_array(fenced)) == 3

    def test_returns_empty_on_garbage(self):
        assert _parse_json_array("not json at all") == []


class TestExtract:
    def test_returns_empty_when_salience_below_threshold(self):
        transcript = [{"hook": "prompt", "prompt": "hello"}]
        assert extract(transcript, salience=SALIENCE_THRESHOLD - 0.1) == []

    def test_extracts_with_mocked_watsonx(self):
        transcript = [
            {"hook": "prompt", "prompt": "start the app"},
            {"hook": "tool", "tool_name": "run_command", "tool_response": "make setup first"},
        ]
        with patch("rebob.core.watsonx.generate", return_value=SAMPLE_LLM_RESPONSE):
            result = extract(transcript, salience=0.8)
        assert len(result) == 1
        assert result[0]["memory_type"] == "env_setup"

    def test_returns_empty_on_malformed_llm_output(self):
        transcript = [{"hook": "prompt", "prompt": "hello"}]
        with patch("rebob.core.watsonx.generate", return_value="Sorry, I cannot do that."):
            assert extract(transcript, salience=0.8) == []

    def test_returns_empty_on_empty_transcript(self):
        with patch("rebob.core.watsonx.generate") as mock_gen:
            assert extract([], salience=0.8) == []
            mock_gen.assert_not_called()
