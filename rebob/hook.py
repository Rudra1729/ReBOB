"""
rebob/hook.py — Bob lifecycle hook (prompt / tool / stop).

Invoked by Bob as:  <python> -m rebob.hook <prompt|tool|stop>
Reads a JSON event from stdin, records it, and (for "prompt") prints a
memory brief to stdout for injection into the user's prompt.

This must NEVER exit non-zero and must NEVER raise past this module —
a broken hook must not block the user's prompt. Set REBOB_DEBUG=1 to
write tracebacks to <rebob_home>/hook.log instead of swallowing them
silently.
"""

from __future__ import annotations

import json
import os
import sys


def _log_debug_error() -> None:
    if os.environ.get("REBOB_DEBUG") != "1":
        return
    try:
        import traceback

        from rebob import paths

        paths.rebob_home().mkdir(parents=True, exist_ok=True)
        with paths.hook_log_path().open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
            f.write("\n" + ("-" * 60) + "\n")
    except Exception:
        pass


def main(argv: list[str]) -> int:
    try:
        from rebob.contract import record, search

        hook_type = argv[1] if len(argv) > 1 else "unknown"
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        session_id = event.get("session_id", "unknown")

        record({"hook": hook_type, **event})

        if hook_type == "prompt":
            prompt = event.get("prompt", "")
            brief = search(prompt, session_id=session_id)
            if brief:
                sys.stdout.write(brief)
    except Exception:
        _log_debug_error()

    return 0


if __name__ == "__main__":
    # Force UTF-8 output regardless of the host console's codepage (cp1252
    # on Windows) — a stray emoji or box-drawing character in a memory
    # brief must not raise UnicodeEncodeError and break the prompt.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv))
