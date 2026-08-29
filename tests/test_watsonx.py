"""Tests for rebob.core.watsonx — unit tests only (no network)."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from rebob.core import watsonx


@pytest.fixture(autouse=True)
def reset_token_cache():
    watsonx._token_cache["token"] = None
    watsonx._token_cache["fetched_at"] = 0.0
    yield
    watsonx._token_cache["token"] = None
    watsonx._token_cache["fetched_at"] = 0.0


class TestGetToken:
    def test_returns_cached_token_when_fresh(self, monkeypatch):
        watsonx._token_cache["token"] = "cached-token"
        watsonx._token_cache["fetched_at"] = time.time()

        with patch.object(watsonx, "_load_config") as mock_cfg:
            assert watsonx.get_token() == "cached-token"
            mock_cfg.assert_not_called()

    def test_refreshes_when_cache_expired(self, monkeypatch):
        watsonx._token_cache["token"] = "stale-token"
        watsonx._token_cache["fetched_at"] = time.time() - (56 * 60)

        mock_client = MagicMock()
        mock_client.token = "fresh-token"

        with patch.object(watsonx, "_load_config", return_value={
            "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
            "IBM_CLOUD_API_KEY": "fake-key",
            "WATSONX_PROJECT_ID": "fake-project",
            "llm_model": "ibm/granite-4-h-small",
            "embed_model": "ibm/granite-embedding-278m-multilingual",
        }), patch("ibm_watsonx_ai.APIClient", return_value=mock_client):
            assert watsonx.get_token() == "fresh-token"


class TestEmbed:
    def test_returns_cached_embedding(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watsonx, "_load_config", lambda: {
            "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
            "IBM_CLOUD_API_KEY": "fake-key",
            "WATSONX_PROJECT_ID": "fake-project",
            "llm_model": "ibm/granite-4-h-small",
            "embed_model": "ibm/granite-embedding-278m-multilingual",
        })
        cache_dir = tmp_path / "embed_cache"
        cache_dir.mkdir()
        monkeypatch.setattr(watsonx, "_cache_dir", lambda: cache_dir)

        text = "hello world"
        cache_file = watsonx._cache_path(text)
        cache_file.write_text(
            json.dumps({"embedding": [0.1, 0.2, 0.3], "model": "ibm/granite-embedding-278m-multilingual"}),
            encoding="utf-8",
        )

        with patch("ibm_watsonx_ai.foundation_models.Embeddings") as mock_emb:
            result = watsonx.embed(text)
            assert result == [0.1, 0.2, 0.3]
            mock_emb.assert_not_called()


class TestLoadConfig:
    def test_raises_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("IBM_CLOUD_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
        monkeypatch.delenv("WATSONX_URL", raising=False)
        with pytest.raises(EnvironmentError, match="Missing required environment variables"):
            watsonx._load_config()
