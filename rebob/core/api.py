"""
rebob/core/api.py — Phase 2 implementations shared by contract, server, and hook.

mem_search / search   → Phase 3 stubs (retrieval pipeline not yet built)
mem_capture           → triggers real write-path pipeline via worker
mem_stats             → live counts from SQLite
mem_why / mem_feedback → Phase 3 stubs
record                → appends event to .rebob/sessions/<id>.jsonl
"""

import json
import sys
import threading
from pathlib import Path

_REBOB_DIR = Path(__file__).resolve().parent.parent.parent / ".rebob"
_CAPTURES_DIR = _REBOB_DIR / "captures"
_SESSIONS_DIR = _REBOB_DIR / "sessions"

_MEMORY_BRIEF_STUB = (
    "## ReBOB Memory Brief\n\n"
    "- [mem_001] Galaxium uses SQLite for article storage.\n"
    "- [mem_002] Run `make setup` before `make start`.\n"
)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

def mem_search(
    query: str,
    k: int = 8,
    budget_tokens: int = 600,
    session_id: str = "",
) -> str:
    """Phase 3 stub — returns a placeholder brief until retrieval is implemented."""
    return _MEMORY_BRIEF_STUB


def mem_capture(
    session_id: str = "",
    label: str = "",
    summary: str = "",
) -> dict:
    """Distil a session into memory records via the real write-path pipeline.

    If session_id is empty, uses the most recently modified .jsonl in .rebob/sessions/.
    """
    from rebob.core.worker import process_session

    sid = session_id
    if not sid:
        sessions_dir = _SESSIONS_DIR
        if sessions_dir.exists():
            jsonl_files = sorted(
                sessions_dir.glob("*.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if jsonl_files:
                sid = jsonl_files[0].stem

    if not sid:
        return {"added": 0, "updated": 0, "rejected": 0, "ids": [], "error": "no session found"}

    return process_session(sid, explicit=True, label=label, summary=summary)


def mem_stats() -> dict:
    """Return live aggregate counts from the memory store."""
    from rebob.core.store import count_by_status, init_db
    init_db()
    return count_by_status()


def mem_why(id: str) -> dict:
    """Phase 3 stub — chain walker not yet implemented."""
    return {"id": id, "content": "stub — not implemented yet", "provenance": []}


def mem_feedback(id: str, verdict: str) -> dict:
    """Phase 3 stub — feedback recording not yet implemented."""
    return {"ok": True, "id": id, "verdict": verdict}


# ---------------------------------------------------------------------------
# Hook-facing helpers
# ---------------------------------------------------------------------------

def search(query: str, session_id: str = "") -> str:
    """Phase 3 stub — returns placeholder brief for hook injection."""
    return _MEMORY_BRIEF_STUB


# msvcrt.locking() is a cross-process lock; two threads in this same process
# each locking the same byte via separate handles trips the Windows CRT's
# self-conflict detection (OSError: Resource deadlock avoided) instead of
# blocking. This in-process lock serializes same-process callers before they
# ever reach the OS-level lock below, which still covers the real production
# case of separate hook.py subprocesses writing concurrently.
_write_lock = threading.Lock()


def _append_line_locked(f, line: str) -> None:
    """Append one line with an exclusive lock (parallel hook subprocesses)."""
    with _write_lock:
        _append_line_locked_os(f, line)


def _append_line_locked_os(f, line: str) -> None:
    if sys.platform == "win32":
        import msvcrt

        # Lock a fixed byte (offset 0) purely as a mutual-exclusion token.
        # Locking the "current end of file" instead would race: two writers
        # can compute the same stale EOF before either has written, then
        # both target that same now-wrong offset. Append mode ("a") already
        # guarantees each write() lands at the true end of file regardless
        # of seek position, so the lock only needs to serialize writers,
        # not protect a specific byte range.
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        try:
            f.write(line)
            f.flush()
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def record(event: dict) -> None:
    """Persist a lifecycle event emitted by the hook."""
    session_id = event.get("session_id", "unknown")
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _SESSIONS_DIR / f"{session_id}.jsonl"
    line = json.dumps(event) + "\n"
    with path.open("a", encoding="utf-8") as f:
        _append_line_locked(f, line)
