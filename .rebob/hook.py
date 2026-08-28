import sys
import json
import os

try:
    hook_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw = sys.stdin.read()
    event = json.loads(raw) if raw.strip() else {}
    session_id = event.get("session_id", "unknown")

    sessions_dir = os.path.join(os.path.dirname(__file__), "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    log_path = os.path.join(sessions_dir, f"{session_id}.jsonl")
    record = {"hook": hook_type, **event}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    if hook_type == "prompt":
        print("\n[ReBOB memory]")
        print("(no memories yet — this is a placeholder brief)")
except Exception:
    pass

sys.exit(0)
