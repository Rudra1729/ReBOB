# ReBOB — Memory for IBM Bob

ReBOB gives [IBM Bob](https://www.ibm.com/products/watson) persistent memory across conversations.
It captures, indexes, and retrieves context so Bob can remember what matters.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -e .                # from a source checkout
# or: pip install git+https://github.com/<org>/ReBOB.git
```

## Set up a project

From inside the project you want Bob to remember things about:

```bash
rebob init
```

This writes `.env` (watsonx credentials), `.bob/mcp.json`, `.bob/settings.json`, and the `/mem`
command/rules templates. Non-interactive (for scripting or CI):

```bash
rebob init --non-interactive --api-key <key> --project-id <id>
```

Then verify everything resolved correctly:

```bash
rebob doctor
```

`rebob doctor` prints every path ReBOB resolved (project root, data directory, `.env`, etc.) —
if something looks wrong, that's the first place to look. `rebob doctor --fix` rewrites stale
Bob config (e.g. after moving the project or reinstalling the venv).

`rebob path` prints the same resolved paths as JSON, useful for scripting.

## How path resolution works

ReBOB never hardcodes `.rebob/` relative to the package install location — that broke under
`pip install` (data was written inside `site-packages/`). Instead, in priority order:

1. `REBOB_HOME` env var, if set (used verbatim as the data directory)
2. `REBOB_PROJECT_ROOT` env var, if set (data dir becomes `$REBOB_PROJECT_ROOT/.rebob`)
3. Walk upward from the current directory looking for an existing `.rebob/`, then `.bob/`,
   then `pyproject.toml`, then `.git/` — first match wins
4. Fall back to the current directory

`rebob init` sets `REBOB_HOME` explicitly in the MCP server's `env` block, so Bob finds the
right data directory regardless of what working directory it happens to launch the server with.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Transport

Default is `stdio` — Bob spawns a fresh process per tool call, zero setup required. If you hit
timeouts on cold start (heavy imports, slow disk), switch to a persistent HTTP server:

```bash
rebob init --transport sse --port 8000
rebob serve --transport sse --port 8000    # keep this running
```
