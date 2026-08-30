# ReBOB — Persistent Memory for IBM Bob

ReBOB gives [IBM Bob](https://www.ibm.com/products/watsonx) memory that survives a task boundary.

Bob is stateless across tasks, compaction is lossy, and completed chats can be deleted. ReBOB records what happened (hooks), distills it into typed memories (watsonx), and injects a small brief on the next prompt (MCP + `UserPromptSubmit` stdout).

You can run it **fully local** (`pip install rebob`) or point any project at a **hosted MCP server** (Cloud Run + Postgres).

---

## Which mode should I use?

| | **Local** | **Hosted** |
|---|---|---|
| Install | `pip install rebob` | `pip install "rebob[hosted]"` |
| Init | `rebob init` | `rebob init --server <url> --api-token <token>` |
| Storage | SQLite under `.rebob/` in the project | Cloud SQL (Postgres + pgvector) |
| MCP | Bob spawns `python -m rebob.server` (stdio) | Bob connects to `https://…/mcp` over HTTP |
| watsonx keys | `.env` on the laptop | `rebob register-watsonx` (encrypted on the server) |
| Best for | One machine, one repo | Many laptops / repos sharing one org |

```mermaid
flowchart LR
  subgraph local [Local mode]
    BobL[IBM Bob] -->|stdio MCP| Proc[rebob.server process]
    Proc --> SQLite[(SQLite + .npy)]
    Proc --> WxL[watsonx APIs]
  end

  subgraph hosted [Hosted mode]
    BobH[IBM Bob] -->|HTTPS /mcp| CR[Cloud Run]
    CR --> PG[(Cloud SQL Postgres)]
    CR --> WxH[watsonx APIs]
  end
```

---

## Architecture

ReBOB is three cooperating pieces:

1. **Lifecycle hooks** — Bob runs `python -m rebob.hook {prompt|tool|stop}` on events. Fail-open: a broken hook must never block the prompt.
2. **MCP server** — tools: `mem_search`, `mem_capture`, `mem_stats`, `mem_why`, `mem_feedback`.
3. **Memory pipeline** — redact → extract (Granite JSON) → resolve/dedup → embed → store → retrieve (FTS + vectors + rerank) → budgeted markdown brief.

```mermaid
flowchart TB
  subgraph bob [IBM Bob IDE]
    Prompt[UserPromptSubmit]
    Tool[PostToolUse]
    Stop[Stop]
    Slash["/mem slash command"]
    MCP[MCP client]
  end

  subgraph rebob [ReBOB]
    Hook[rebob.hook]
    Capture[mem_capture]
    Search[mem_search]
    Store[(SQLite or Postgres)]
    Pipeline[redact → extract → resolve → embed]
  end

  Prompt -->|stdin JSON + stdout brief| Hook
  Tool --> Hook
  Stop --> Hook
  Hook -->|local: jsonl / hosted: POST /events| Store
  Slash --> Capture
  MCP --> Search
  MCP --> Capture
  Capture --> Pipeline --> Store
  Search --> Store
  Search -->|markdown brief| MCP
```

### Capture and retrieval

```mermaid
sequenceDiagram
  participant User
  participant Bob
  participant Hook as rebob.hook
  participant Server as MCP / HTTP
  participant DB as Store
  participant WX as watsonx

  User->>Bob: prompt
  Bob->>Hook: UserPromptSubmit JSON
  Hook->>Server: record event
  Hook->>Server: search(prompt)
  Server->>DB: FTS + vector candidates
  Server->>WX: embed / rerank
  Server-->>Hook: brief markdown
  Hook-->>Bob: stdout injected into context
  Bob-->>User: answer with memory

  User->>Bob: /mem
  Bob->>Server: mem_capture(summary, session_id)
  Server->>WX: distill transcript / notes
  Server->>DB: insert memories + embeddings
  Server-->>Bob: added / updated / rejected
```

### Hosted tenancy

On Postgres, requests carry `Authorization: Bearer rebob_…`. The token maps to an **org**. Row Level Security (`FORCE ROW LEVEL SECURITY`) keeps org A from reading org B. watsonx keys are stored **per org**, encrypted with `REBOB_ENCRYPTION_KEY`.

```mermaid
flowchart LR
  Client[Bob / CLI] -->|Bearer token| Auth[AuthMiddleware]
  Auth --> Ctx[RequestContext org_id]
  Ctx --> RLS[Postgres RLS]
  RLS --> Mem[(memory / embeddings / sessions)]
```

### Storage backends

| Concern | SQLite (local) | Postgres (hosted) |
|---|---|---|
| Metadata | `memory` table | same schema + `org_id` |
| Keyword search | FTS5 | `tsvector` / `plainto_tsquery` |
| Vectors | `.npy` files | `pgvector` |
| Sessions | jsonl under `.rebob/sessions/` | `sessions` table |

### MCP tools

| Tool | Purpose |
|---|---|
| `mem_search` | Retrieve a budgeted markdown brief |
| `mem_capture` | Distill the current session / summary into memories |
| `mem_stats` | Counts |
| `mem_why` | Provenance for one memory id |
| `mem_feedback` | Mark a memory useful / wrong |

`/mem` is a Bob slash command (`/.bob/commands/mem.md`) that **must** call `mem_capture` with a real `summary` (5–10 sentences). Hosted capture often has no hook transcript; the summary is what gets saved.

### Path resolution (local data)

ReBOB never writes `.rebob/` inside `site-packages`. Priority:

1. `REBOB_HOME`
2. `REBOB_PROJECT_ROOT` → `$REBOB_PROJECT_ROOT/.rebob`
3. Walk up from cwd: `.rebob/` → `.bob/` → `pyproject.toml` → `.git/`
4. Current directory

`rebob init` sets `REBOB_HOME` in the local MCP `env` block so Bob’s spawn cwd cannot hide the data dir.

---

## Prerequisites

- Python **3.10+**
- [IBM Bob](https://www.ibm.com/products/watsonx) 2.x
- A [watsonx.ai](https://dataplatform.cloud.ibm.com/wx) project: `IBM_CLOUD_API_KEY`, `WATSONX_PROJECT_ID`
- Default models: `ibm/granite-4-h-small` (LLM), `ibm/granite-embedding-278m-multilingual` (embeddings)

---

## Option A — Local: `pip install rebob`

Memory stays on this laptop, in this project’s `.rebob/` directory. No Cloud Run, no token.

### 1. Create a project folder (any repo)

```bash
mkdir my-app && cd my-app
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### 2. Install

```bash
pip install -U rebob
rebob version
```

From a git checkout instead:

```bash
pip install -e ".[dev]"
```

### 3. Initialize Bob config

```bash
rebob init
```

You will be prompted for watsonx credentials. That writes:

- `.env` — watsonx keys (gitignored)
- `.bob/mcp.json` — stdio MCP: `python -m rebob.server`
- `.bob/settings.json` — prompt / tool / stop hooks
- `.bob/commands/mem.md`, rules, skill templates

Non-interactive:

```bash
rebob init --non-interactive --api-key KEY --project-id PROJECT_ID
```

### 4. Check

```bash
rebob doctor
```

### 5. Use in Bob

1. Open **this folder** in IBM Bob.
2. **Settings → MCP** → enable tools for new tasks. `rebob` should show **Connected**.
3. Start a **new** task, work as usual, then type **`/mem`** to save.

Local MCP looks like this (paths will match your machine):

```json
{
  "mcpServers": {
    "rebob": {
      "command": "/path/to/.venv/bin/python3",
      "args": ["-m", "rebob.server"],
      "cwd": "/path/to/project",
      "env": { "REBOB_HOME": "/path/to/project/.rebob" }
    }
  }
}
```

If MCP stays **Disconnected**, run the same command Bob runs and read the traceback:

```bash
python3 -m rebob.server
```

Optional persistent HTTP locally (if stdio cold-start is slow):

```bash
rebob init --transport http --port 8000
rebob serve --transport http --port 8000
```

---

## Option B — Hosted: globally deployed MCP server

The laptop is a thin client. Memory lives on **Cloud Run + Cloud SQL**. Any repo on any machine can share an org.

**Public demo endpoint (this project):**

| | URL |
|---|---|
| Service | `https://rebob-y5wwgqymmq-uc.a.run.app` |
| MCP | `https://rebob-y5wwgqymmq-uc.a.run.app/mcp` |
| Ready check | `https://rebob-y5wwgqymmq-uc.a.run.app/readyz` |

Use **`/readyz`**, not `/healthz` (Cloud Run may 404 `/healthz`).

You also need a **user API token** (`rebob_…`) issued by an admin. That is **not** the Mac login password and **not** a placeholder like `rebob_YOUR_TOKEN`.

```mermaid
flowchart TB
  Admin[Admin issues token] --> You[You receive URL + token]
  You --> Pip["pip install rebob[hosted]"]
  Pip --> Init["rebob init --server --api-token"]
  Init --> Wx[rebob register-watsonx]
  Wx --> Bob[Open folder in Bob → enable MCP]
```

### 1. Install the hosted extra

```bash
cd /path/to/any-project
python3 -m venv .venv
source .venv/bin/activate

pip install -U "rebob[hosted]"
rebob version
```

### 2. Point this folder at the server

Replace `rebob_…` with the **real** token you were given (do not paste the words `YOUR_TOKEN`):

```bash
rebob init \
  --server https://rebob-y5wwgqymmq-uc.a.run.app \
  --api-token rebob_…
```

This writes `.bob/mcp.json` with an HTTP MCP entry:

```json
{
  "mcpServers": {
    "rebob": {
      "url": "https://rebob-y5wwgqymmq-uc.a.run.app/mcp",
      "headers": {
        "Authorization": "Bearer rebob_…"
      }
    }
  }
}
```

Hooks get `REBOB_SERVER_URL` and `REBOB_API_TOKEN` so events POST to `/events` instead of local jsonl.

### 3. Optional: `rebob login`

```bash
rebob login \
  --token rebob_… \
  --server-url https://rebob-y5wwgqymmq-uc.a.run.app
```

This stores the token in the **OS keychain** (macOS Keychain service name `rebob`: `api_token` + `server_url`). The password prompt is your **Mac user password**, not a ReBOB password. If Keychain fails, click **Deny** and skip login — `init --api-token` is enough for Bob.

### 4. Register **your** watsonx keys on the server

Hosted `init` does not write watsonx into a local `.env` for the server. Create `.env` (or export vars) and register:

```bash
cat > .env <<'EOF'
IBM_CLOUD_API_KEY=...
WATSONX_PROJECT_ID=...
WATSONX_URL=https://us-south.ml.cloud.ibm.com
EOF

set -a && source .env && set +a
export REBOB_API_TOKEN=rebob_…
export REBOB_SERVER_URL=https://rebob-y5wwgqymmq-uc.a.run.app
rebob register-watsonx
```

Expect: `watsonx credentials registered with server.`

### 5. Check and open Bob

```bash
curl -s https://rebob-y5wwgqymmq-uc.a.run.app/readyz
rebob doctor
```

Open the folder in Bob → **Settings → MCP** → enable `rebob` → **new task**. Status should be **Connected**. Use **`/mem`** to capture.

### What an admin sends you

| Give | Do not give |
|---|---|
| Cloud Run URL | `REBOB_ADMIN_TOKEN` |
| Your `rebob_…` user token | Database password / `DATABASE_URL` |
| These install steps | GCP / Fernet encryption key |

Running `rebob init` **without** `--server` later will **overwrite** hosted MCP with local stdio. To stay on the cloud, always pass `--server` and the real token.

---

## Admin: issue a token (server operators)

Needs Postgres access (Cloud SQL Auth Proxy) and `REBOB_ADMIN_TOKEN`:

```bash
export REBOB_BACKEND=postgres
export DATABASE_URL=postgresql://USER:PASS@127.0.0.1:5432/rebob
export REBOB_ADMIN_TOKEN=...

rebob admin issue-token --org my-team --author you@example.com
```

Send the printed `rebob_…` token once, over a private channel.

---

## CLI cheat sheet

| Command | Role |
|---|---|
| `rebob init` | Local Bob config + `.env` |
| `rebob init --server URL --api-token TOKEN` | Hosted Bob config |
| `rebob login --token TOKEN --server-url URL` | Keychain / credential file |
| `rebob register-watsonx` | Upload BYO watsonx to hosted server |
| `rebob doctor` / `rebob doctor --fix` | Diagnose / rewrite stale MCP paths |
| `rebob serve --transport http --port 8000` | Run MCP yourself |
| `rebob admin issue-token` | Mint user tokens (hosted) |
| `rebob path` / `rebob version` | Debug |
| `rebob privacy --show` | Inspect redacted payload |

---

## Security

- Redaction runs **before** storage (regex + entropy).
- Do **not** commit `.env`, `.bob/mcp.json`, or `.bob/settings.json` (tokens and absolute paths). `rebob init` gitignores them.
- Hosted tokens are org-scoped Bearer secrets. Treat them like passwords.
- Hooks are fail-open. Set `REBOB_DEBUG=1` to write `hook.log` under the data dir.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| MCP **Disconnected**, tools empty, `mcp.json` has `"url"` | Placeholder token (`rebob_YOUR_TOKEN`) or invalid Bearer → 401 |
| MCP **Disconnected**, `mcp.json` has `"command"` | Local stdio process crashed. Run `python3 -m rebob.server` |
| Thought you were on cloud but config is stdio | Ran `rebob init` without `--server` |
| Keychain popup | `rebob login` / CLI reading token. Mac password, or **Deny** and use `--api-token` / env |
| `/healthz` HTML 404 | Use `/readyz` |
| First MCP call slow / “session not available” | Cloud Run scale-to-zero cold start; retry |
| `/mem` saves 0 memories | Pass a real `summary`; hosted often has no session transcript |

---

## Tests (contributors)

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Postgres tests run when `DATABASE_URL` is set (optional). Publish to PyPI via `.github/workflows/publish.yml` after bumping `version` in `pyproject.toml` and `rebob/__init__.py` (PyPI never overwrites an existing version filename).

---

## Deploy your own hosted server

See [`deploy/README.md`](deploy/README.md) (IBM Code Engine) or run the container:

- Image: `Dockerfile` — `python -m rebob.server --transport http --port 8080`
- Env: `REBOB_BACKEND=postgres`, `DATABASE_URL`, `REBOB_ENCRYPTION_KEY`, `REBOB_ADMIN_TOKEN`
- Postgres needs `CREATE EXTENSION vector;`
- Attach Cloud SQL (or equivalent) to the service

Local Postgres for development:

```bash
docker compose up -d
export REBOB_BACKEND=postgres
export DATABASE_URL=postgresql://rebob:rebob@localhost:5433/rebob
rebob serve --transport http --port 8000
```

---

## License

See the repository license file.
