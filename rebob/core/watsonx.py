"""
rebob/core/watsonx.py — watsonx.ai client: IAM token, embeddings, generation.

IAM tokens expire in 60 min; we refresh at 55 min.
Embedding results are cached by SHA-256 content hash under <rebob_home>/embed_cache/.
Never logs API keys or tokens.
"""

import hashlib
import json
import os
import time
from pathlib import Path

from rebob import config, paths

config.load_env()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Read required env vars; raise a clear error if any are missing."""
    return config.get_settings()


# ---------------------------------------------------------------------------
# IAM token cache
# ---------------------------------------------------------------------------

_token_cache: dict = {"token": None, "fetched_at": 0.0}
_TOKEN_TTL = 55 * 60  # refresh before 60-min expiry


def get_token() -> str:
    """Return a valid IAM bearer token, refreshing if older than 55 minutes."""
    now = time.time()
    if _token_cache["token"] and (now - _token_cache["fetched_at"]) < _TOKEN_TTL:
        return _token_cache["token"]

    cfg = _load_config()
    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai import APIClient

    credentials = Credentials(
        url=cfg["WATSONX_URL"],
        api_key=cfg["IBM_CLOUD_API_KEY"],
    )
    client = APIClient(credentials=credentials, project_id=cfg["WATSONX_PROJECT_ID"])
    # The SDK manages its own token internally; we extract it for caching.
    token = client.token

    _token_cache["token"] = token
    _token_cache["fetched_at"] = time.time()
    return token


# ---------------------------------------------------------------------------
# Embedding cache helpers
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    d = paths.embed_cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(text: str) -> Path:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed(text: str) -> list:
    """Return a float embedding for *text*, using a local cache to avoid repeat calls."""
    cache_file = _cache_path(text)
    cfg = _load_config()

    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("model") == cfg["embed_model"]:
            return cached["embedding"]

    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai.foundation_models import Embeddings

    credentials = Credentials(
        url=cfg["WATSONX_URL"],
        api_key=cfg["IBM_CLOUD_API_KEY"],
    )
    embedder = Embeddings(
        model_id=cfg["embed_model"],
        credentials=credentials,
        project_id=cfg["WATSONX_PROJECT_ID"],
    )
    result = embedder.embed_documents([text])
    # SDK returns list of lists
    embedding = result[0] if isinstance(result[0], list) else list(result[0])

    cache_file.write_text(
        json.dumps({"embedding": embedding, "model": cfg["embed_model"]}),
        encoding="utf-8",
    )
    return embedding


def generate(prompt: str, *, max_tokens: int = 2048, temperature: float = 0.1) -> str:
    """Generate text with Granite via watsonx.ai. Returns the generated string."""
    cfg = _load_config()

    from ibm_watsonx_ai import Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as Params

    credentials = Credentials(
        url=cfg["WATSONX_URL"],
        api_key=cfg["IBM_CLOUD_API_KEY"],
    )
    model = ModelInference(
        model_id=cfg["llm_model"],
        credentials=credentials,
        project_id=cfg["WATSONX_PROJECT_ID"],
        params={
            Params.MAX_NEW_TOKENS: max_tokens,
            Params.TEMPERATURE: temperature,
            Params.DECODING_METHOD: "greedy",
        },
    )
    response = model.generate_text(prompt=prompt)
    return response if isinstance(response, str) else str(response)


def rerank(query: str, documents: list, *, top_n: int = 20) -> list:
    """Return indices of *documents* sorted by relevance (best first).

    Uses the watsonx Text Rerank API.  On any failure (network, timeout, missing
    creds) returns the identity ordering [0, 1, 2, ...] so callers are
    unaffected.  Never raises.
    """
    if not documents:
        return []

    identity = list(range(len(documents)))
    try:
        cfg = _load_config()
        rerank_model = os.getenv(
            "WATSONX_RERANK_MODEL",
            "ibm/slate-125m-english-rtrvr-v2",
        )

        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models.rerank import Rerank

        credentials = Credentials(
            url=cfg["WATSONX_URL"],
            api_key=cfg["IBM_CLOUD_API_KEY"],
        )
        reranker = Rerank(
            model_id=rerank_model,
            credentials=credentials,
            project_id=cfg["WATSONX_PROJECT_ID"],
            params={"return_options": {"top_n": min(top_n, len(documents))}},
        )
        response = reranker.generate(query=query, inputs=documents)
        # SDK returns {"results": [{"index": int, "score": float}, ...]}
        results = response.get("results", [])
        if not results:
            return identity
        return [r["index"] for r in results]

    except Exception:
        return identity
