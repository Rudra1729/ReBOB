"""
rebob/core/api.py — Phase 1 implementations shared by contract, server, and hook.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

_REBOB_DIR = Path(__file__).resolve().parent.parent.parent / ".rebob"
_CAPTURES_DIR = _REBOB_DIR / "captures"
_SESSIONS_DIR = _REBOB_DIR / "sessions"

_MEMORY_BRIEF = (
    "## ReBOB Memory Brief\n\n"
    "- [mem_001] Galaxium uses SQLite for article storage.\n"
    "- [mem_002] Run `make setup` before `make start`.\n"
)


def mem_search(
    query: str,
    k: int = 8,
    budget_tokens: int = 600,
    session_id: str = "",
) -> str:
    """Return a markdown memory brief of up to *k* entries within *budget_tokens*."""
    return _MEMORY_BRIEF


def mem_capture(
    session_id: str = "",
    label: str = "",
    summary: str = "",
) -> dict:
    """Distil a session into memory records (stub: writes a capture file)."""
    _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "session_id": session_id,
        "label": label,
        "summary": summary,
        "ts": ts,
    }
    (_CAPTURES_DIR / f"{ts}.json").write_text(json.dumps(payload, indent=2))
    return {"added": 0, "updated": 0, "rejected": 0, "ids": []}


def mem_stats() -> dict:
    """Return aggregate counts from the memory store."""
    return {"total": 0, "active": 0, "superseded": 0, "rejected": 0}


def mem_why(id: str) -> dict:
    """Explain why a memory entry exists and where it came from."""
    return {"id": id, "content": "stub — not implemented yet", "provenance": []}


def mem_feedback(id: str, verdict: str) -> dict:
    """Record whether a recalled memory was useful or wrong."""
    return {"ok": True, "id": id, "verdict": verdict}


def search(query: str, session_id: str = "") -> str:
    """Return a memory brief for injection into a prompt."""
    return _MEMORY_BRIEF


def record(event: dict) -> None:
    """Persist a lifecycle event emitted by the hook."""
    session_id = event.get("session_id", "unknown")
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _SESSIONS_DIR / f"{session_id}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
