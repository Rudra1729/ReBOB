"""
rebob/config.py — Centralized environment loading and settings validation.

Replaces the four separate bare `load_dotenv()` calls that used to live in
extract.py, resolve.py, watsonx.py, and worker.py. Bare `load_dotenv()`
walks upward from cwd, which is wrong once cwd is decoupled from the
project root (see rebob.paths). This module loads the .env file at the
path rebob.paths resolves, exactly once per process.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from rebob import paths

_loaded = False

_REQUIRED_KEYS = ("WATSONX_URL", "WATSONX_PROJECT_ID", "IBM_CLOUD_API_KEY")
_DEFAULT_LLM_MODEL = "ibm/granite-4-h-small"
_DEFAULT_EMBED_MODEL = "ibm/granite-embedding-278m-multilingual"


def load_env(*, force: bool = False) -> None:
    """Load the project's .env file exactly once per process.

    Idempotent — safe to call from every module that needs config. Does not
    override variables already set in the real environment (override=False),
    so explicit env vars (e.g. from an MCP server's `env` block) always win.
    """
    global _loaded
    if _loaded and not force:
        return
    load_dotenv(dotenv_path=paths.env_file(), override=False)
    _loaded = True


def get_settings() -> dict:
    """Read required watsonx env vars; raise a clear error if any are missing.

    Returns a dict keyed by the raw env var names (WATSONX_URL, etc.) plus
    lowercase 'llm_model' / 'embed_model' convenience keys — this shape is
    the frozen contract relied on by rebob.core.watsonx.
    """
    load_env()
    cfg = {k: os.getenv(k) for k in _REQUIRED_KEYS}
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in your credentials."
        )
    cfg["llm_model"] = os.getenv("WATSONX_LLM_MODEL", _DEFAULT_LLM_MODEL)
    cfg["embed_model"] = os.getenv("WATSONX_EMBEDDING_MODEL", _DEFAULT_EMBED_MODEL)
    return cfg
