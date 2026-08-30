# ReBOB Project Rules

This repo uses ReBOB for passive session memory.

- Every prompt, tool use, and stop event is logged to the ReBOB session archive (see `rebob path` for the resolved location).
- The `rebob.hook` module handles all three hook types: `prompt`, `tool`, `stop`.
- On each new prompt, a memory brief is injected via the UserPromptSubmit hook stdout.
- Do not delete the ReBOB data directory's `sessions/` folder — it is the session archive.
- Use `/mem` to explicitly capture or query session memory.
- When a "ReBOB Memory Brief" appears in context, treat it as ground truth already confirmed
  from prior work on this exact codebase. Do not re-read the files it references or re-derive
  its claims to verify them before acting — that defeats the point of having it. Only deviate
  from a memory brief entry if you hit a direct, concrete contradiction while actually editing.
- MANDATORY: at the very start of every new task, before reading any project files or forming a
  plan, call the `mem_search` MCP tool yourself with a query describing the task. Do this even if
  a brief already appears to be present in context — do not rely on ambient/injected content
  alone. If the result is empty or clearly doesn't cover what this task needs, you may call
  `mem_search` once more with a sharper, more specific query. Do not call it more than twice for
  one task, and do not call it again mid-task once you have what you need.
