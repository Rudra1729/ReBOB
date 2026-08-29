"""Tests for rebob.core.redact — must pass before real sessions hit watsonx."""

import json

import pytest

from rebob.core.redact import redact, redact_transcript

# Nasty vectors (fake secrets — not real credentials)
FAKE_API_KEY = "IBM_CLOUD_API_KEY=abc123longfakekeyvalue12345678901234567890"
FAKE_BEARER = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
FAKE_EMAIL = "contact admin@example.com for access"
FAKE_IP = "Connect to server at 192.168.1.100 port 8080"
FAKE_ENV = "SECRET=supersecretvalue1234567890"
HIGH_ENTROPY = "kJ8#mP2$xQ9!vL4@nR7&wT5%yU3^zA6*bC1"


class TestRedact:
    def test_api_key_not_in_output(self):
        cleaned, patterns = redact(FAKE_API_KEY)
        assert "abc123longfakekeyvalue" not in cleaned
        assert "IBM_CLOUD_API_KEY" in cleaned or "[REDACTED" in cleaned
        assert len(patterns) >= 1

    def test_bearer_token_redacted(self):
        cleaned, patterns = redact(FAKE_BEARER)
        assert "eyJhbGci" not in cleaned
        assert "[REDACTED_BEARER]" in cleaned
        assert "bearer_token" in patterns

    def test_email_redacted(self):
        cleaned, patterns = redact(FAKE_EMAIL)
        assert "admin@example.com" not in cleaned
        assert "[REDACTED_EMAIL]" in cleaned
        assert "email" in patterns

    def test_ipv4_redacted(self):
        cleaned, patterns = redact(FAKE_IP)
        assert "192.168.1.100" not in cleaned
        assert "[REDACTED_IP]" in cleaned
        assert "ipv4" in patterns

    def test_env_secret_redacted(self):
        cleaned, patterns = redact(FAKE_ENV)
        assert "supersecretvalue" not in cleaned
        assert "env_secret" in patterns

    def test_high_entropy_redacted(self):
        cleaned, patterns = redact(f"password field: {HIGH_ENTROPY}")
        assert HIGH_ENTROPY not in cleaned
        assert "high_entropy" in patterns

    def test_normal_code_preserved(self):
        text = "Run `make setup` before `make start` in the Makefile."
        cleaned, patterns = redact(text)
        assert cleaned == text
        assert patterns == []

    def test_empty_string(self):
        cleaned, patterns = redact("")
        assert cleaned == ""
        assert patterns == []


class TestRedactTranscript:
    def test_redacts_prompt_and_tool_response(self):
        transcript = [
            {"hook": "prompt", "prompt": FAKE_EMAIL},
            {"hook": "tool", "tool_response": FAKE_API_KEY, "tool_input": {"path": "ok.py"}},
        ]
        result = redact_transcript(transcript)
        assert "admin@example.com" not in result[0]["prompt"]
        assert "abc123longfakekeyvalue" not in result[1]["tool_response"]

    def test_redacts_tool_input_strings(self):
        transcript = [
            {
                "hook": "tool",
                "tool_input": {"token": FAKE_BEARER},
            }
        ]
        result = redact_transcript(transcript)
        assert "eyJhbGci" not in json.dumps(result[0]["tool_input"])

    def test_does_not_mutate_original(self):
        original = [{"hook": "prompt", "prompt": FAKE_EMAIL}]
        redact_transcript(original)
        assert "admin@example.com" in original[0]["prompt"]
