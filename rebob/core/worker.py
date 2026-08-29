"""
rebob/core/worker.py — Orchestrator for the full write path.

process_session(session_id, *, explicit, label, summary) -> dict
process_pending() -> list[dict]

Person B owns assemble.py and salience.py.
This file imports them when available; falls back to minimal stubs otherwise.
Person B must NOT edit this file.

CLI usage:
    python -m rebob.core.worker --session-id <id>
    python -m rebob.core.worker --pending
"""

import json
from pathlib import Path

from dotenv import load_dotenv

from dotenv import load_dotenv

load_dotenv()


def _sessions_dir() -> Path:
    from rebob.core.store import _DB_DIR
    return _DB_DIR / "sessions"


def _pending_dir() -> Path:
    from rebob.core.store import _DB_DIR
    return _DB_DIR / "pending"


# ---------------------------------------------------------------------------
# Fallbacks for modules Person B owns (used until those modules are merged)
# ---------------------------------------------------------------------------

def _assemble_fallback(session_id: str, jsonl_path: Path) -> list[dict]:
    """Minimal fallback: read JSONL lines as-is."""
    events = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def _score_fallback(transcript: list[dict], explicit: bool = False) -> float:
    """Minimal fallback salience score."""
    return 1.0 if explicit else 0.5


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def process_session(
    session_id: str,
    *,
    explicit: bool = False,
    label: str = "",
    summary: str = "",
) -> dict:
    """Run the full write path for one session.

    explicit=True forces salience=1.0 (used by /mem mem_capture).
    """
    jsonl_path = _sessions_dir() / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        return {"added": 0, "updated": 0, "rejected": 0, "ids": [], "error": "session not found"}

    # 1. ASSEMBLE
    try:
        from rebob.core.assemble import assemble  # type: ignore[import]
        transcript = assemble(session_id, jsonl_path)
    except ImportError:
        transcript = _assemble_fallback(session_id, jsonl_path)

    # 2. REDACT
    from rebob.core.redact import redact_transcript
    transcript = redact_transcript(transcript)

    # 3. SALIENCE
    if explicit:
        salience = 1.0
    else:
        try:
            from rebob.core.salience import score  # type: ignore[import]
            salience = score(transcript, explicit=False)
        except ImportError:
            salience = _score_fallback(transcript, explicit=False)

    # 4 + 5. EXTRACT (includes validate inside extract)
    from rebob.core.extract import extract
    raw_records = extract(transcript, salience)

    # Attach session context
    for r in raw_records:
        r.setdefault("task_id", session_id)
        r.setdefault("source_kind", "explicit_mem" if explicit else "hook_session")

    # 6. RESOLVE (embed + store inside)
    from rebob.core.resolve import resolve
    return resolve(raw_records)


# ---------------------------------------------------------------------------
# Pending marker sweep
# ---------------------------------------------------------------------------

def process_pending() -> list[dict]:
    """Process all .rebob/pending/<session_id>.marker files."""
    pending_dir = _pending_dir()
    results = []
    if not pending_dir.exists():
        return results
    for marker in pending_dir.glob("*.marker"):
        session_id = marker.stem
        result = process_session(session_id)
        results.append({"session_id": session_id, **result})
        marker.unlink()
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ReBOB write-path worker")
    parser.add_argument("--session-id", help="Process a specific session by ID")
    parser.add_argument(
        "--pending", action="store_true", help="Process all pending marker files"
    )
    args = parser.parse_args()

    if args.pending:
        print(process_pending())
    elif args.session_id:
        print(process_session(args.session_id))
    else:
        parser.print_help()
