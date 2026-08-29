import json
import sys

try:
    from rebob.contract import record, search

    hook_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw = sys.stdin.read()
    event = json.loads(raw) if raw.strip() else {}
    session_id = event.get("session_id", "unknown")

    record({"hook": hook_type, **event})

    if hook_type == "prompt":
        prompt = event.get("prompt", "")
        print(search(prompt, session_id=session_id))
except Exception:
    pass

sys.exit(0)
