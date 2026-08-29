"""
rebob/core/assemble.py — session JSONL to ordered transcript.

Owned by Person B. First stage of the write-path pipeline:
assemble -> redact -> salience -> extract -> resolve -> embed -> store.
"""

import json
from pathlib import Path


def assemble(session_id: str, jsonl_path: Path) -> list[dict]:
    """Read a session's JSONL event log and return an ordered transcript.

    Each entry is ``{"turn": int, "type": str, "session_id": str, ...}``,
    where ``type`` comes from the hook that recorded the event
    (``prompt`` / ``tool`` / ``stop``) and the remaining keys are whatever
    the original event carried — e.g. ``prompt`` for prompt events,
    ``tool`` / ``input`` / ``output`` for tool events.

    Missing files and malformed lines are skipped rather than raised,
    matching the hook's own never-crash contract.
    """
    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        return []

    transcript = []
    turn = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        turn += 1
        entry = {
            "turn": turn,
            "type": event.get("hook", "unknown"),
            "session_id": session_id,
        }
        entry.update({k: v for k, v in event.items() if k not in ("hook", "session_id")})
        transcript.append(entry)

    return transcript
