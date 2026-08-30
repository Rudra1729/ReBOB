# ReBOB — Persistent Memory for IBM Bob 2.0

**Architecture v4** — revised Aug 27 after reading the official Bob IDE documentation
**Type:** Lifecycle-hook recorder + MCP server + memory pipeline, all local
**Workflow bucket:** Onboarding (primary), Application maintenance (secondary)
**Window:** 10:00 ET Aug 28 → 10:00 ET Aug 30

---

## 0. What changed in v4

Reading `bob.ibm.com/docs/ide` replaced guesswork with documented features. Four findings, two of which rebuilt the design.

| Finding | Effect |
|---|---|
| **Lifecycle hooks exist.** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`. Stdout of the first two is **injected into the model's context**. `PostToolUse` receives tool name, input, and output. | Capture and retrieval both stop depending on Bob choosing to cooperate. We record passively and inject deterministically. |
| **Custom slash commands work in the IDE.** "Type '/' … built-in commands (like /review, /init) and custom commands." | The skill fallback is unnecessary. `/mem` is real. |
| **Bob deletes completed tasks after 14 days.** Configurable in Settings → Chat → Task retention. Stored **locally**, never synced. | Sharpens the problem statement: the raw material is on a deletion timer. |
| Subagent spawns require user approval | Confirms extraction should run on watsonx, outside Bob, with no approval prompts. |

**Superseded from v3:** the `/mem`-only capture path (Bob summarising itself, one Bobcoin per save) and the rules-file retrieval path (Bob deciding to call `mem_search`). Both survive as secondary paths; neither is load-bearing.

---

## 1. The problem, in IBM's own words

**Enablement deck:** LLMs are stateless · long conversations cost more · **compaction is lossful** · best performance under **~50%** of the 270k window · "when is a good time to start a new conversation?"

**IBM i track Q&A:**
> "Within a task it will remember. Go off and create a new task and it is not stored, **because of security**."

**Z track Q&A:**
> "It captures the current state description only. Bob reverse-engineers and documents strictly what the code currently does."

**IDE documentation:**
> Bob automatically deletes completed tasks after 14 days… the task and its conversation history are permanently removed and cannot be recovered.

**Problem statement (opens the 500-word deliverable):**
> Bob's cost and quality both degrade as context fills, so the recommended workflow is to discard context often. Compaction is lossy. Nothing crosses the task boundary. And the raw history is deleted after fourteen days. The only durable option is a hand-written AGENTS.md that describes what the code *is* and taxes every prompt forever. Every task re-derives what the last one already paid for, and in two weeks even the evidence is gone.

**Solution statement:**
> ReBOB records Bob sessions through Bob's own lifecycle hooks, distills them into typed, code-anchored memory records, and injects a small budgeted brief into the context of prompts that need it. Because IBM's stated reason for not persisting is security, the security model came first: redaction before storage, local-only, full provenance on every claim.

---

## 2. Guides and Sensors

The enablement deck's Concept 3: **Guides** (feedforward) steer before the agent acts; **Sensors** (feedback) observe after. Bob has both and no wire between them across sessions.

The hooks make this literal:

| Hook | Role |
|---|---|
| `PostToolUse` | **Sensor.** Every file write, command, and test result, with its output. |
| `UserPromptSubmit` | **Guide.** Stdout lands in the model's context alongside the prompt. |

> **ReBOB is the wire from Sensors to Guides — and Bob supplied both ends.**

That is the single strongest line in the video: we didn't work around Bob, we used the extension points Bob documents.

---

## 3. Where we differ from what IBM ships

| IBM capability | Stops at |
|---|---|
| IBM i RAG (docs, Redbooks) | Knows the platform, not your project |
| Z metadata scan / data dictionary | Current-state description |
| **AGENTS.md via `/init`** | Always-loaded, hand-maintained, unbounded |
| RPGUnit workflows | Re-read existing tests each run — re-derivation |
| zContext (roadmap) | Static, prebuilt |
| Task history | **Deleted after 14 days** |

> IBM's artifacts document what the code *is*. ReBOB captures what was *tried*, what *failed*, and why a decision went the way it did — which exists only in the session, and only for two weeks.

The guide's example appendix leads with "Smart developer onboarding assistant," so expect many repo explainers. State plainly: **ReBOB is not a code explainer. It stops Bob re-explaining the same thing every Monday.**

---

## 4. Stack

| Layer | Choice | Why |
|---|---|---|
| Recorder | **Bob lifecycle hooks** → `python .rebob/hook.py` | Documented, free, no Bobcoins |
| Server | Python + FastMCP, **stdio** | Bob is a full MCP client |
| Metadata + keyword search | **SQLite** + FTS5 | Zero infra |
| Vectors | numpy float32 + cosine, `.npy` | <5k rows is sub-millisecond. No Qdrant, no Docker, no Windows pain. |
| Embeddings | watsonx.ai Embeddings API | Dallas, `https://us-south.ml.cloud.ibm.com` |
| Rerank | watsonx.ai Text rerank API | Fits retrieval stage 4 exactly |
| Extraction | watsonx.ai Granite instruct, strict JSON | Off Bobcoins, outside Bob |
| Redaction | regex + entropy, pure Python | No dependency |

**Not used:** watsonx Orchestrate, NLU, STT, TTS (irrelevant or a time sink). Cloudant is a roadmap line for team sync.

**Cloud facts:** IAM tokens expire in 60 min — refresh at 55. Banned models: `llama-3-405b-instruct`, `mistral-medium-2505`, `mistral-small-3-1-24b-instruct-2503`. Cloud accounts do not support deployment; run local. $80 credits, hourly-lagged alerts, suspension at 100%.

---

## 5. Capture — the passive recorder

### Hook configuration

Workspace scope, `.bob/settings.json`, committed with the repo:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command",
                    "command": "python .rebob/hook.py prompt",
                    "timeout": 8 }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command",
                    "command": "python .rebob/hook.py tool",
                    "timeout": 5 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command",
                    "command": "python .rebob/hook.py stop",
                    "timeout": 5 }] }
    ]
  }
}
```

### What each hook gives us

| Hook | Payload | Use |
|---|---|---|
| `UserPromptSubmit` | `session_id`, `prompt` | What you asked. Also the retrieval trigger (§6). |
| `PostToolUse` | `session_id`, `tool`, `input`, `output` | Every file write, command, and its **output** — test results, stack traces, error text |
| `Stop` | `session_id` | Session ended → enqueue for extraction |

Appended as JSONL to `.rebob/sessions/<session_id>.jsonl`. From these three streams you can reconstruct: what was wanted, what was tried, what failed, what worked. Without ever asking Bob to describe itself, and without a single Bobcoin.

### Hard rules for the hook script

These are not style preferences. Get one wrong and you break the demo.

1. **Always `sys.exit(0)`.** `UserPromptSubmit` blocks the prompt on exit code 2. Wrap everything in try/except and exit 0 no matter what. A crashed hook must never stop the user typing.
2. **`Stop` enqueues, never processes.** Hook timeout defaults to 10s and extraction takes longer. Write a marker file; a separate worker picks it up.
3. **Absolute paths.** Hooks run from the task working directory; Windows runs them via `cmd /c`. Invoke `python` with a resolved path.
4. **Print nothing from `PostToolUse` or `Stop`.** Their stdout is ignored, but silence keeps logs clean.
5. **Hooks run with full user permissions, unsandboxed.** Keep the script small, readable, and dependency-free.

### Three capture paths, in order

| Path | Trigger | Status |
|---|---|---|
| **Passive** | Hooks, always on | **P0.** The default. Nothing to remember. |
| **Explicit** | `/mem` slash command → `mem_capture` via MCP | **P0.** "This one mattered" — promotes a recorded session immediately at full salience. |
| **Retroactive** | Tasks panel → re-open an old task → `/mem` | **P0.** Covers sessions from before ReBOB was installed. Bounded by Bob's 14-day retention. |

The retroactive path is where the 14-day deletion becomes a selling point: **install ReBOB and your last two weeks are still recoverable. Wait a month and they aren't.**

---

## 6. Retrieval — deterministic injection

The `UserPromptSubmit` hook is the retrieval path. Its stdout is written into the model's context alongside your prompt, so memory arrives whether or not Bob thinks to ask.

```
you type a prompt
  → UserPromptSubmit hook fires with the prompt text
  → 1. EXPAND    prompt + open files + branch
  → 2a. DENSE    watsonx embed → cosine over .npy       ┐
  → 2b. SPARSE   FTS5 BM25                              ├ parallel, top 30 each
  → 2c. STRUCT   memories anchored to files in scope    ┘
  → 3. FUSE      reciprocal rank fusion
  → 4. RERANK    watsonx Text rerank on top 20
  → 5. FILTER    status=active, anchor_valid, scope, NOT ALREADY INJECTED
  → 6. SCORE     rerank·0.5 + usefulness·0.2 + recency·0.15 + confidence·0.15
  → 7. PACK      to 600 tokens, cited IDs
  → 8. PRINT     → injected into context
  → 9. LOG       retrieval + injected IDs
```

### The accumulation trap

Injected text **stays in the conversation**. Twenty prompts × 600 tokens = 12,000 tokens, which recreates the exact problem we exist to solve.

**Mitigation, and it is mandatory:** keep `.rebob/injected/<session_id>.json` holding every memory ID already sent this session. Filter them out at stage 5. First prompt of a session may get 600 tokens; the tenth usually gets nothing. Instrument this — "tokens injected per session" is a metric we report.

### The latency budget

This hook sits in front of every prompt you type. Budget 8 seconds, and degrade rather than hang:

- Cache every embedding by content hash — most queries never call watsonx.
- If watsonx is slow, skip rerank and return the fused list.
- If watsonx is unreachable, run FTS5 + cosine locally and carry on.
- Never block. Never exit non-zero.

### Secondary paths

- **`SessionStart` hook** → a project orientation brief on the first turn of a new task. This is the onboarding demo, in one line of config.
- **MCP `mem_search`** → `/recall auth flow` when you want to ask deliberately.
- **`.bob/rules/rules.md`** → reduced to ≤15 lines. Kept only so the before/after against AGENTS.md is honest.

---

## 7. Memory record

P0 populates ●. The rest are defined now so the schema never needs migrating.

```sql
CREATE TABLE memory (
  id                TEXT PRIMARY KEY,          -- ●
  claim_key         TEXT NOT NULL,             -- ● normalized subject+predicate = dedup cluster
  version           INTEGER DEFAULT 1,         -- ●
  supersedes        TEXT,                      -- ●
  status            TEXT NOT NULL,             -- ● active|superseded|rejected|quarantined
  created_at        TIMESTAMP,                 -- ●
  updated_at        TIMESTAMP,

  memory_type       TEXT NOT NULL,             -- ●
  content           TEXT NOT NULL,             -- ● ONE atomic claim
  rationale         TEXT,                      -- ● how we learned it
  counter_example   TEXT,                      -- ● "tried X, failed because Y"
  snippet           TEXT,

  scope             TEXT NOT NULL,             -- ● repo|user|global
  repo_url          TEXT,                      -- ●
  branch            TEXT,
  author_id         TEXT,                      -- ●

  file_paths        JSON,                      -- ● from PostToolUse inputs
  symbols           JSON,                      -- ●
  languages         JSON,
  commit_sha        TEXT,                      -- ●
  anchor_valid      BOOLEAN DEFAULT 1,         -- ●

  source_kind       TEXT,                      -- ● hook_session|explicit_mem|retroactive|agents_md_import
  task_id           TEXT,                      -- ● = hook session_id
  bob_mode          TEXT,
  extractor_model   TEXT,                      -- ●
  raw_hash          TEXT,                      -- ●

  confidence        REAL,                      -- ●
  evidence_count    INTEGER DEFAULT 1,         -- ●
  volatility        TEXT,                      -- ● durable|seasonal|volatile
  verification      TEXT,                      -- asserted|verified_by_test|verified_by_human

  retrieval_count   INTEGER DEFAULT 0,         -- ●
  used_count        INTEGER DEFAULT 0,         -- ●
  positive_signals  INTEGER DEFAULT 0,         -- ● from PostToolUse: tests passed after injection
  negative_signals  INTEGER DEFAULT 0,         -- ● from PostToolUse: rollback after injection
  usefulness        REAL DEFAULT 0.5,          -- ●
  last_used_at      TIMESTAMP,

  sensitivity       TEXT DEFAULT 'internal',   -- ●
  redaction_applied JSON,                      -- ●
  pinned            BOOLEAN DEFAULT 0,         -- ●

  vector_row        INTEGER,                   -- ● index into vectors.npy
  keywords          JSON                       -- ●
);

CREATE VIRTUAL TABLE memory_fts USING fts5(content, rationale, keywords, content=memory);
```

`positive_signals` and `negative_signals` are now cheap to populate, because `PostToolUse` shows us the test command and its output. That closes the feedback loop with real evidence rather than self-report.

### `memory_type`

| Type | Example | Fixes |
|---|---|---|
| `convention` | snake_case in DB, camelCase in API | Style churn |
| `decision` | "front-end calc chosen; back-end rejected, migration cost" | Re-proposing rejected options |
| `constraint` | "route must be registered in `api/v1/__init__.py`" | Broken output |
| `failure_mode` | "`pip install` breaks the venv, use `make setup`" | Dead ends |
| `gotcha` | "returns 200 with empty body when not found" | Wrong error handling |
| `env_setup` | "make setup → make init-db → make start" | Repo crawl on onboarding |
| `api_contract` | "ISO-8601 UTC with Z, never offsets" | Format-mismatch bugs |
| `domain_term` | "Reservation is pre-payment, Booking is post-payment" | Wrong business logic |
| `task_recipe` | "feed filter → these 3 files" | 20-file crawl → 3 reads |
| `security_note` | "this was a SQLi sink, now parameterized — do not regress" | Silent regressions |

`decision`, `failure_mode`, and `counter_example` are the differentiation expressed as schema.

---

## 8. Write path

```
Stop hook fires → marker written → worker picks it up
  → 1. ASSEMBLE  session JSONL → prompts, tool calls, outputs, timeline
  → 2. REDACT    regex + entropy, before anything is embedded or stored
  → 3. SALIENCE  free heuristics: error→resolution, tests red→green,
                 rollbacks, files touched, turn count
                 (explicit /mem = score 1.0, always extract)
  → 4. EXTRACT   watsonx Granite, strict JSON, one atomic claim per record
  → 5. VALIDATE  drop malformed, drop confidence < 0.4
  → 6. NORMALIZE → claim_key
  → 7. RESOLVE   ADD | UPDATE | SUPERSEDE | NOOP | REJECT-against-pinned
  → 8. EMBED     watsonx → append row to vectors.npy
  → 9. STORE     SQLite + FTS5
```

Nothing is hard-deleted. `mem_why(id)` walks the version chain back to the session that produced it.

**Redaction is not polish.** IBM's stated reason Bob doesn't persist across tasks is security, and the guide says exposed IBM Cloud credentials get the account suspended immediately. The recorder sees raw command output. Redact at the boundary or don't ship.

Add `.rebob/` to `.bobignore` and `.gitignore` so Bob never reads its own store back into context and the DB never reaches GitHub.

---

## 9. Frozen tool contract

Freeze at hour 1. Person B builds against a mock. **Do not change these signatures.**

```python
mem_search(query: str, k: int = 8, budget_tokens: int = 600,
           session_id: str = "") -> str      # markdown brief; session_id enables dedup
mem_capture(session_id: str = "", label: str = "",
            summary: str = "") -> dict       # {"added","updated","rejected","ids"}
mem_stats() -> dict
mem_why(id: str) -> dict
mem_feedback(id: str, verdict: str) -> dict  # useful | wrong
```

Five tools. Auto-approve `mem_search` in Bob's MCP permissions.

The hook script calls the same retrieval and capture code **in-process**, not through MCP — no server round trip in the prompt path.

---

## 10. The AGENTS.md punchline

`/init` is IBM's own answer to persistent context, and it is always-loaded. The demo:

1. Show AGENTS.md costing ~2,700 tokens on **every** prompt.
2. Capture it as `source_kind=agents_md_import` — typed, scoped records.
3. Replace the file with a ≤15-line stub.
4. Same task, same knowledge, ~600 tokens, injected only into the prompts that need it, and only once per session.

---

## 11. Explicitly not building

Team/SSE mode · graph edges beyond `supersedes` · Memory Curator mode · watsonx Orchestrate · Z data dictionary seeding · Db2 seeding · stale-memory reaper · Bob Shell integration · web UI · **`PreToolUse` blocking**.

That last one deserves a sentence, because it's the best roadmap slide we have: `PreToolUse` can block a tool call by exiting 2, so a pinned `security_note` could physically prevent a regression. Memory with teeth. **Do not demo it live** — a blocked tool call on camera looks like a crash. Say it at 2:55 and stop.

One deep hole: **record → extract → store → retrieve → inject → measure, plus retroactive capture.**

---

## 12. Residual risks

| Risk | Mitigation |
|---|---|
| Hook script crashes and blocks prompts | try/except everything, always exit 0. Test with a deliberately broken DB before you trust it. |
| Injection accumulates and bloats context | Session-scoped dedup file. Instrument tokens-injected-per-session and put it on the chart. |
| Hook latency on every prompt | 8s timeout, embedding cache, skip rerank under pressure, local-only fallback. |
| Windows path issues (`cmd /c`) | Absolute paths, `python` on PATH verified at hour 0. Both machines. |
| Extraction returns junk | Fixed schema, few-shot, validator, confidence floor. **Show a rejected memory in the demo** — it proves judgement. |
| Recorder captures a secret | Redact before storage; unit-test redaction before pointing it at a real session. |
| Originality rule | First commit after 10:00 ET Aug 28 from the IBM template. Git history is the proof. |
| "Isn't this another onboarding assistant?" | §3. Rehearse the one-liner. |
