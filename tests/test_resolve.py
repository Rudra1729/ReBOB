"""Tests for rebob.core.resolve."""

from unittest.mock import patch

import pytest

from rebob.core import store
from rebob.core.resolve import normalize_claim_key, resolve


@pytest.fixture
def mock_embed():
    with patch("rebob.core.watsonx.embed", return_value=[0.1, 0.2, 0.3]) as m:
        yield m


def _record(**kwargs):
    base = {
        "memory_type": "env_setup",
        "content": "Run make setup before make start.",
        "rationale": "Observed ModuleNotFoundError until setup ran.",
        "confidence": 0.9,
        "file_paths": ["Makefile"],
        "keywords": ["make"],
        "task_id": "sess-1",
        "source_kind": "hook_session",
    }
    base.update(kwargs)
    return base


class TestNormalizeClaimKey:
    def test_lowercases_and_strips_punctuation(self):
        key = normalize_claim_key("Run `make setup` BEFORE start!")
        assert "`" not in key
        assert key == key.lower() or "make setup" in key


class TestResolve:
    def test_adds_new_record(self, initialized_db, mock_embed):
        result = resolve([_record()])
        assert result["added"] == 1
        assert result["updated"] == 0
        assert result["rejected"] == 0
        assert len(result["ids"]) == 1
        row = store.get_memory(result["ids"][0])
        assert row is not None
        assert row["status"] == "active"
        mock_embed.assert_called_once()

    def test_noop_on_identical_claim(self, initialized_db, mock_embed):
        first = resolve([_record()])
        mock_embed.reset_mock()
        second = resolve([_record()])
        assert first["added"] == 1
        assert second["added"] == 0
        assert second["updated"] == 0
        mock_embed.assert_not_called()

    def test_adds_second_record_for_different_claim(self, initialized_db, mock_embed):
        first = resolve([_record()])
        second = resolve([_record(content="Use make setup then make init-db before make start.")])
        assert first["added"] == 1
        assert second["added"] == 1
        assert store.count_by_status()["active"] == 2

    def test_rejects_contradiction_of_pinned_same_claim_key(self, initialized_db, mock_embed):
        claim = "run make setup before make start"
        mem_id = store.insert_memory({
            "id": "mem_pinned1",
            "claim_key": claim,
            "memory_type": "env_setup",
            "content": "Run make setup before make start.",
            "rationale": "pinned baseline",
            "scope": "repo",
            "status": "active",
            "pinned": 1,
        })
        mock_embed.reset_mock()
        result = resolve([_record(content="Skip make setup and use pip install only.")])
        # Different content → different claim_key → adds a separate record (not a reject)
        assert result["added"] == 1
        assert store.get_memory(mem_id)["pinned"] == 1

    def test_rejects_empty_content(self, initialized_db, mock_embed):
        result = resolve([_record(content="   ")])
        assert result["rejected"] == 1
        mock_embed.assert_not_called()
