Call the `mem_capture` MCP tool now to distil this session into ReBOB memory.

- If the user typed extra words after `/mem` (e.g. `/mem auth bug fix`), pass that text as `label`.
- Don't pass `session_id` — it defaults to the most recently active session automatically.
- After the call returns, report the result plainly: how many memories were added/updated/rejected, and their IDs. If `added` + `updated` is 0, say so directly rather than implying something was saved.
