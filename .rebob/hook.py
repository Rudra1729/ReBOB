import json
import sys
from pathlib import Path

# Repo root on sys.path so we can import rebob.contract
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

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
