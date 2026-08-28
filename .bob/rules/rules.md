# ReBOB Project Rules

This repo uses ReBOB for passive session memory.

- Every prompt, tool use, and stop event is logged to `.rebob/sessions/<session_id>.jsonl`.
- The `hook.py` lifecycle script handles all three hook types: `prompt`, `tool`, `stop`.
- On each new prompt, a brief memory summary is injected via stdout (placeholder until backend is wired).
- Do not delete `.rebob/sessions/` — it is the session archive.
- Use `/mem` to query captured session state (stub for now).
