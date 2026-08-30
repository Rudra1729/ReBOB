"""rebob privacy — show what would be transmitted for a session."""

from __future__ import annotations

import json

from rebob import paths
from rebob.core.events import sanitize_session_events


def run_privacy(*, session_id: str = "") -> None:
    """Print allowlisted, redacted events for a session (trust UX)."""
    sessions_dir = paths.sessions_dir()
    if not sessions_dir.exists():
        print("No sessions directory found.")
        return

    if session_id:
        paths_to_show = [sessions_dir / f"{session_id}.jsonl"]
        if not paths_to_show[0].exists():
            print(f"Session not found: {session_id}")
            return
    else:
        paths_to_show = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not paths_to_show:
            print("No recorded sessions.")
            return
        paths_to_show = paths_to_show[:1]
        session_id = paths_to_show[0].stem
        print(f"Showing most recent session: {session_id}\n")

    raw_events = []
    for path in paths_to_show:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                raw_events.append(json.loads(line))

    sanitized = sanitize_session_events(raw_events)
    print(json.dumps(sanitized, indent=2))
