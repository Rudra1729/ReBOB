# ReBOB Project Rules

This repo uses ReBOB for passive session memory.

- Every prompt, tool use, and stop event is logged to `.rebob/sessions/<session_id>.jsonl`.
- The `hook.py` lifecycle script handles all three hook types: `prompt`, `tool`, `stop`.
- On each new prompt, a memory brief is injected via the UserPromptSubmit hook stdout.
- Do not delete `.rebob/sessions/` — it is the session archive.
- Use `/mem` to explicitly capture or query session memory.
