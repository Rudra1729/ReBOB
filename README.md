# ReBOB — Memory for IBM Bob

ReBOB gives [IBM Bob](https://www.ibm.com/products/watson) persistent memory across conversations.
It captures, indexes, and retrieves context so Bob can remember what matters.

## Quick start — add ReBOB to a project

```bash
cd /path/to/your/project                     # the project you want memory for
python -m venv .venv                         # isolate the `rebob` CLI in this project
.venv\Scripts\activate                       # Windows (use `source .venv/bin/activate` on macOS/Linux)
pip install -e /path/to/this/ReBOB/repo      # installs the `rebob` CLI into .venv
rebob init                                   # prompts for watsonx credentials, writes .env/.bob/.rebob
rebob doctor                                 # confirms everything's wired up correctly
```

A venv's `Scripts`/`bin` folder is put on PATH automatically when activated, so `rebob` resolves
correctly regardless of how the system Python is set up. Without a venv, `pip install` may put the
`rebob` command somewhere not on your PATH, and running `rebob` will fail with
"not recognized as the name of a cmdlet" (Windows) or "command not found" (macOS/Linux).

Then open that project in Bob IDE — Settings → MCP → enable **"MCP tools for new tasks"** — and
start a task. Every prompt/tool-use/stop event is now recorded, and the memory brief for a prompt
is injected automatically. Run `/mem` in a task to explicitly capture that session into memory.

`rebob init` is safe to re-run — it asks before overwriting anything that already exists.

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```
