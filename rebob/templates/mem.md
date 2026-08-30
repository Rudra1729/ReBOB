---
name: mem
description: Explicitly capture the current session into ReBOB memory via mem_capture
metadata:
  user-invocable: true
  disable-model-invocation: true
---

Call the `mem_capture` MCP tool now to distil this session into ReBOB memory.

- Always pass `summary`: 5–10 sentences of the concrete facts, decisions, and gotchas from THIS conversation (not the words "save this"). Hosted ReBOB often has no hook transcript; `summary` is what gets saved.
- If the user typed extra words after `/mem` (e.g. `/mem auth bug fix`), pass that text as `label`.
- Pass `session_id` when you know this Bob task's session id. Otherwise omit it.
- After the call returns, report the result plainly: how many memories were added/updated/rejected, and their IDs. If `added` + `updated` is 0, say so directly rather than implying something was saved.
