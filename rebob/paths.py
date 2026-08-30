"""
rebob/paths.py — Single path authority for ReBOB.

Every file in the codebase that needs a data path (.rebob/, .env, .bob/)
must go through this module. Nothing else may build one of these paths
directly with `Path(".rebob")` or `Path(__file__).parent...`.

Resolution order for the project root (first match wins):
  1. REBOB_HOME        — if set, used verbatim AS the data directory itself.
  2. REBOB_PROJECT_ROOT — data dir becomes $REBOB_PROJECT_ROOT/.rebob.
  3. Upward marker search from cwd: an existing .rebob/, then .bob/,
     then pyproject.toml, then .git/.
  4. Fallback: cwd.

No subprocess calls (no `git rev-parse`) — a pure filesystem walk, so it
works without git installed and costs no process-spawn latency.

The resolved root is cached per-process. Call reset_cache() in tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_MARKERS = (".rebob", ".bob", "pyproject.toml", ".git")

_cache: dict = {"home": None}


def reset_cache() -> None:
    """Clear the cached resolved home directory. Test-only."""
    _cache["home"] = None


def _walk_up_for_marker(start: Path) -> Optional[Path]:
    """Search start and its parents for the first directory containing
    any of _MARKERS, preferring the nearest match.

    Stops at (and does not search above) the user's home directory. Without
    this bound, a stray .rebob/ that a fallback resolution once created
    directly in $HOME (see _resolve_home's cwd fallback) would silently
    "capture" every unrelated project walked from underneath it — the
    marker search would find $HOME/.rebob before ever reaching the real
    project root. Returns None if no marker is found within that bound.
    """
    try:
        home = Path.home().resolve()
    except Exception:
        home = None

    current = start.resolve()
    while True:
        # Home itself is excluded from the search (not just its ancestors) —
        # a marker sitting directly in $HOME is exactly the false-positive
        # this bound exists to prevent.
        if home is not None and current == home:
            return None
        for marker in _MARKERS:
            if (current / marker).exists():
                return current
        if current.parent == current:
            return None
        current = current.parent


def _resolve_home() -> Path:
    env_home = os.environ.get("REBOB_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    env_root = os.environ.get("REBOB_PROJECT_ROOT")
    if env_root:
        return (Path(env_root).expanduser().resolve() / ".rebob")

    found_root = _walk_up_for_marker(Path.cwd())
    if found_root is not None:
        return found_root / ".rebob"

    return (Path.cwd().resolve() / ".rebob")


def rebob_home() -> Path:
    """Return the ReBOB data directory (where rebob.db, sessions/, etc. live).

    Cached per-process after first call; set REBOB_HOME or REBOB_PROJECT_ROOT
    before the first call to override, or use reset_cache() in tests.
    """
    if _cache["home"] is None:
        _cache["home"] = _resolve_home()
    return _cache["home"]


def project_root() -> Path:
    """Return the project root directory (parent of .rebob/)."""
    return rebob_home().parent


def db_path() -> Path:
    return rebob_home() / "rebob.db"


def vectors_path() -> Path:
    return rebob_home() / "vectors.npy"


def sessions_dir() -> Path:
    return rebob_home() / "sessions"


def pending_dir() -> Path:
    return rebob_home() / "pending"


def injected_dir() -> Path:
    return rebob_home() / "injected"


def captures_dir() -> Path:
    return rebob_home() / "captures"


def embed_cache_dir() -> Path:
    return rebob_home() / "embed_cache"


def hook_log_path() -> Path:
    return rebob_home() / "hook.log"


def env_file() -> Path:
    return project_root() / ".env"


def bob_dir() -> Path:
    return project_root() / ".bob"


def describe() -> dict:
    """Return every resolved path as strings. Powers `rebob doctor` / `rebob path`."""
    return {
        "project_root": str(project_root()),
        "rebob_home": str(rebob_home()),
        "db_path": str(db_path()),
        "vectors_path": str(vectors_path()),
        "sessions_dir": str(sessions_dir()),
        "pending_dir": str(pending_dir()),
        "injected_dir": str(injected_dir()),
        "captures_dir": str(captures_dir()),
        "embed_cache_dir": str(embed_cache_dir()),
        "env_file": str(env_file()),
        "bob_dir": str(bob_dir()),
        "resolved_from": (
            "REBOB_HOME" if os.environ.get("REBOB_HOME")
            else "REBOB_PROJECT_ROOT" if os.environ.get("REBOB_PROJECT_ROOT")
            else "marker_search" if _walk_up_for_marker(Path.cwd()) is not None
            else "cwd_fallback"
        ),
    }
