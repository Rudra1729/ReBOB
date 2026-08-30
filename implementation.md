# ReBOB as a Hosted Service — Implementation Plan

**For:** Rudra
**Status:** proposal, not started
**Prereq:** PR #10 (`reimplement`) merged — the path-authority + packaging work this builds on

---

## 1. What we're building

Today ReBOB is a **local, single-user tool**: `pip install rebob && rebob init` gives you a private
`.rebob/` directory holding a SQLite DB and a flat `vectors.npy`, and Bob talks to a stdio MCP
server that this machine spawns per call.

The goal is a **hosted, multi-tenant MCP server**: one deployment anyone can point Bob at,
storing context in a data lake, so memory follows a person (or a team) across machines and
projects instead of living in one folder on one laptop.

```
TODAY                                    TARGET
┌──────────────┐                         ┌──────────────┐   ┌──────────────┐
│ Bob (laptop) │                         │ Bob (laptop) │   │ Bob (laptop) │
│  ├ hook.py   │──in-process──┐          │  └ hook ─────┼───┼──── hook ────┼──┐
│  └ MCP stdio │              │          │  └ MCP http ─┼───┼──── MCP http─┼──┤
└──────────────┘              ▼          └──────────────┘   └──────────────┘  │
                        ┌──────────┐                                          │ HTTPS + auth
                        │ .rebob/  │                                          ▼
                        │ sqlite   │                             ┌────────────────────────┐
                        │ vectors  │                             │  ReBOB server (MCP)    │
                        │ sessions │                             │  auth │ tenancy │ RAG  │
                        └──────────┘                             └───┬────────────────┬───┘
                         per-laptop,                                 │                │
                         no sharing                        ┌─────────▼──────┐  ┌──────▼───────┐
                                                           │ Serving store  │  │  Data lake   │
                                                           │ Postgres +     │  │  COS (raw    │
                                                           │ pgvector + FTS │  │  + Iceberg)  │
                                                           │ hot path, ms   │  │  cold, bulk  │
                                                           └────────────────┘  └──────────────┘
```

**The single most important architectural point in this document:** the data lake and the
serving store are *two different systems with two different jobs*. Details in §4.

---

## 2. What actually breaks when you host this

I audited the current code against a hosted model. These aren't style issues — each one is a
correctness, security, or availability failure in a shared deployment.

### 2.1 SECURITY — raw unredacted transcripts would leave the user's machine

**This is the blocker. Nothing else matters until it's fixed.**

`redact.py` is good — it catches bearer tokens, AWS keys, env-style secret assignments, emails,
IPs, and high-entropy strings. But look at *when* it runs:

| Step | What happens | Redacted? |
|---|---|---|
| Hook fires | `api.record(event)` writes the raw event to `<home>/sessions/<id>.jsonl` (`api.py:180-189`) | **No** |
| Later, `/mem` | `worker.process_session()` → `assemble()` → `redact_transcript()` (`worker.py:80-82`) | Yes |

Redaction happens at **distillation** time, not at **capture** time. That's fine today — the raw
JSONL never leaves your disk. The moment `record()` becomes an HTTP POST, **you are shipping
unredacted tool output, file contents, and prompts to a shared server.** Every `PostToolUse`
event. That is a data-exfiltration bug, not a nice-to-have.

**Fix (Phase 2, must land before any network code):** move `redact()` to the client, inside
`record()`, so the raw event is scrubbed *before* it is written or transmitted. Keep the
distillation-time redaction as defense in depth. Also: `_TEXT_FIELDS` (`redact.py:165`) only
covers `prompt`, `tool_response`, `output`, `last_assistant_message` — for transmission, invert
this to an **allowlist**: only send fields you've explicitly decided are safe, drop everything
else. An unknown field added by a future Bob version must fail closed, not silently ship.

### 2.2 CORRECTNESS — `append_vector` loses data under any concurrency

`store.py:208-224`:

```python
existing = np.load(str(npy_path))                    # read whole file
updated  = np.vstack([existing, vec.reshape(1, dim)]) # append in memory
np.save(str(npy_path), updated)                       # rewrite whole file
```

Read-modify-write of the entire file, no lock. Two concurrent captures: both read N rows, both
write N+1, one vector is silently lost — **and both memory rows now claim `vector_row = N`**, so
one of them permanently points at the other's embedding. Wrong memories get retrieved, with no
error anywhere.

It is also O(N) per write. At 50k memories × 768 floats that's ~150MB read and rewritten on
every single capture.

Single-user this is survivable (one process, rarely concurrent). On a server it is fatal on day
one.

### 2.3 SCALE — retrieval full-scans everything on every hook call

Per query:
- `store.list_active_memories()` (`retrieve.py:266`) — every active row into Python
- `store.load_vectors()` (`retrieve.py:88`) — the entire `vectors.npy` into RAM
- `_dense_search` (`retrieve.py:81`) — cosine against all of them in a Python loop

Fine at 100 memories. At 10k across tenants, on the `UserPromptSubmit` path with an **8000 ms
hook timeout** (`_util.py:68`), this misses the budget and the user's prompt just... proceeds
without memory, silently (`retrieve()` swallows everything and returns `""`, `retrieve.py:246-250`).

### 2.4 `vector_row` is a positional index into a flat file

`vector_row` is the row number in `vectors.npy`. It is only meaningful relative to one exact
file. You cannot delete a memory and compact the file, cannot shard by tenant, cannot rebuild
the index, cannot migrate — every operation shifts every subsequent row. This must become a
stable ID before anything else is built on top.

### 2.5 No tenancy, no auth

The schema already has `scope`, `repo_url`, `branch`, `author_id` (`store.py:34-37`) — good
instinct — but **only `scope` is ever written**, hardcoded to `"repo"` (`resolve.py:137`).
`repo_url`, `branch`, and `author_id` are dead columns. So there is currently zero isolation and
zero identity. Good news: the columns exist, so the migration is additive rather than a schema
rewrite.

### 2.6 SQLite is a single-writer, single-host store

WAL + `busy_timeout` (added in PR #10) makes it fine for one laptop. It is not a multi-writer
network database and shouldn't be made into one.

### 2.7 watsonx credentials and cost move to the server

Today each user pays for their own embed/generate/rerank calls with their own key in `.env`.
Hosted, the *server* makes those calls. That's a billing model, an abuse surface, and a quota
problem, not just a config change.

### 2.8 The hook is an in-process call, not a client

`hook.py:39` imports `rebob.contract` and calls `record()`/`search()` directly in-process.
There is no client/server split to switch on. This is the largest single piece of new code.

---

## 3. Design principles

1. **Local mode must keep working.** Offline, air-gapped, and privacy-sensitive users are a real
   segment, and it's also how you develop and test. Hosted is a *backend choice*, not a fork.
2. **Redact at the edge.** The client decides what leaves the machine. The server is never
   trusted with raw transcripts.
3. **Lake ≠ serving store.** See §4.
4. **Isolation enforced by the database, not by application code.** One forgotten `WHERE
   tenant_id = ?` should not be able to leak another org's memories.
5. **Fail open, never block the prompt.** The hook's never-crash contract (`hook.py:53-56`)
   extends to the network: server down, slow, or 500 → empty brief, exit 0, user unaffected.

---

## 4. Architecture: the lake / serving split

The ask is "store all the data in a data lake." The important nuance: **a data lake is the wrong
thing to read from on the hook path.** Object storage and Iceberg/Presto have latencies in the
hundreds of milliseconds to seconds. The `UserPromptSubmit` hook has an 8 s hard timeout and
already spends 1–2 s on watsonx embed + rerank. Querying a lake per keystroke-batch would blow
the budget and silently degrade to "no memory."

So: **write to both, read from the right one.**

### Raw zone — the actual data lake (IBM Cloud Object Storage)

Every recorded event, append-only, immutable:

```
cos://rebob-lake/raw/
  tenant_id=<uuid>/
    dt=2026-08-30/
      session_id=<uuid>/events.jsonl.gz
```

This is the system of record. Cheap, durable, replayable — if you change the extraction prompt
or the model, you can re-derive every memory from the raw zone without asking users to
re-do work. That replayability is the real payoff of the lake, and it's worth building for that
reason alone.

### Curated zone — Iceberg tables over COS, queried via watsonx.data

Partitioned Parquet/Iceberg for analytics: memory records, retrieval events, feedback signals,
benchmark runs. This is where the Arm 1 / Arm 2 comparison in `bench/results.csv` should
eventually live as real queryable data instead of a hand-maintained CSV.

### Serving store — Postgres + pgvector (the hot path)

Everything the hook and MCP tools read: memory rows, embeddings, FTS index, session dedup,
feedback counters. Millisecond queries, real concurrency, real transactions.

**Recommendation: Postgres with `pgvector` for v1**, not Milvus/Elasticsearch. One system gives
you relational rows, vector similarity (`<=>` operator, HNSW index), *and* full-text search
(`tsvector`) — replacing SQLite + `vectors.npy` + FTS5 with a single managed service. Three
systems' worth of ops for one. IBM Cloud Databases for PostgreSQL supports pgvector.

Move to Milvus (available inside watsonx.data) only when a measured limit forces it — realistically
past ~1M vectors per tenant, which is far away.

### Write path

```
hook → redact (client) → POST /events → server
                                          ├─→ COS raw zone      (async, durable)
                                          └─→ Postgres sessions (sync, for /mem)
/mem → server: assemble → redact → salience → extract → resolve → embed
                                          ├─→ Postgres memory + pgvector (serving)
                                          └─→ Iceberg curated zone (async, analytics)
```

Note the pipeline stages (`assemble` → `redact` → `salience` → `extract` → `resolve`) stay exactly
as they are — they're pure functions over a transcript. **They move from the laptop to the
server; they don't get rewritten.** That's the main reason this port is tractable.

---

## 5. Tenancy and data model

### What is a tenant?

Three-level scoping, all three already half-present in the schema:

| Level | Key | Meaning |
|---|---|---|
| `org` | `org_id` | Billing + hard isolation boundary. Nothing crosses it, ever. |
| `project` | `repo_url` (normalized) | Default sharing unit — a team on one repo sees each other's memories. |
| `personal` | `author_id` | Private to one user, invisible to teammates. |

Add `org_id` and `visibility` (`personal` | `project` | `org`) columns; start populating the
existing `repo_url`, `branch`, `author_id`. `scope` stays for backwards compatibility.

Normalize `repo_url` carefully — `git@github.com:IBM/x.git`, `https://github.com/IBM/x`, and
`https://github.com/IBM/x.git` are the same project and must produce the same key, or two people
on the same repo get two disjoint memory sets and it looks broken.

### Isolation: Postgres Row-Level Security

```sql
ALTER TABLE memory ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON memory
  USING (org_id = current_setting('rebob.org_id')::uuid);
```

The server sets `rebob.org_id` per request from the authenticated token. Every query is then
filtered by the database itself. This is principle #4: a missing `WHERE` clause in application
code cannot leak data, because the database refuses. For a system holding other people's source
context, that defense-in-depth is worth the setup cost.

### Auth

**v1: bearer tokens.** Server issues an API key per user; `rebob login --token <key>` stores it
in the OS keychain (not `.env` — it's a credential, and `.env` gets committed by accident).
`Authorization: Bearer <key>` on every request.

**v2: OAuth 2.1**, which the MCP spec defines for remote servers, so any MCP client can
authenticate without ReBOB-specific setup. Don't start here; bearer tokens unblock everything
and OAuth is a drop-in replacement later.

---

## 6. Implementation phases

Each phase leaves the tree working, tested, and shippable.

### Phase 0 — Decisions
Answer §9 before writing code. Especially the trust question — it changes the architecture.

### Phase 1 — Storage abstraction (the key enabler)
Define a `StorageBackend` protocol covering exactly what `store.py` exposes today
(`insert_memory`, `get_by_claim_key`, `list_active_memories`, `fts_search`, `append_vector` /
`load_vectors`, `increment_retrieval`, `update_feedback`, `count_by_status`).

Ship `SqliteBackend` (current behavior, byte-identical) behind it. Select via
`REBOB_BACKEND=sqlite|postgres`.

**Do this first.** Without it, hosted mode forks the codebase and local mode rots. With it,
every later phase is "add a backend," and the 187 existing tests keep running against SQLite as
a regression net.

**Also in this phase:** replace `vector_row` (positional) with a stable `embedding_id` (UUID).
It's a small change now and an impossible one later.

**Exit:** `pytest` green, zero behavior change.

### Phase 2 — Client-side redaction (security prerequisite)
Move `redact()` into `record()` so events are scrubbed before they're written. Switch
transmission to a field **allowlist**. Add `rebob privacy --show` so a user can see exactly what
would be sent for a given session — trust in a hosted memory product is the whole product, and
"show me" beats "trust me."

**Exit:** a test that asserts a synthetic secret planted in tool output never appears in the
recorded JSONL. Not just "redact() works" — end-to-end through `record()`.

### Phase 3 — Postgres backend
`PostgresBackend`: schema migration (Alembic), pgvector HNSW index, `tsvector` FTS replacing
FTS5, connection pooling, RLS policies. Run the same backend test suite against both SQLite and
Postgres.

**Exit:** every existing test passes against Postgres via `REBOB_BACKEND=postgres`.

### Phase 4 — Data lake writer
COS client, gzipped JSONL to the raw zone, partitioned as §4. Async/queued — a lake write must
never be on the hook's latency path. Iceberg curated tables + a replay job that re-derives
memories from raw.

**Exit:** replay reconstructs an identical memory set from raw events alone.

### Phase 5 — Auth + tenancy
Token issuance/validation, `org_id`/`visibility` columns, `repo_url` normalization, RLS wired to
the authenticated principal, `rebob login`.

**Exit:** a test proving tenant A cannot retrieve tenant B's memory — by ID, by search, by
`mem_why`, by any path.

### Phase 6 — HTTP server + client mode
Server: FastMCP over `streamable-http` (endpoint `/mcp`) or `sse` (endpoint `/sse`) —
**these differ and mismatching them yields a silent 404 with Bob showing "disconnected"; we
already lost time to exactly this.** Add `GET /healthz`, `/readyz`.

Client: `rebob/client.py` — a thin HTTP client. `hook.py` switches on config between in-process
(local) and HTTP (hosted). Timeouts strictly under the hook budget (8 s prompt / 5 s tool), with
retry + circuit breaker, and **fail-open on every error path** — the existing never-crash
contract (`hook.py:53-56`) extended across the network.

`rebob init --server https://…` writes the hosted `.bob/mcp.json` and hook config.

**Exit:** kill the server mid-session; prompts still work, hook still exits 0, nothing blocks.

### Phase 7 — Deploy
IBM Code Engine (scales to zero, HTTPS built in, straightforward for a FastAPI/FastMCP app).
Secrets in Code Engine secrets, not env files in the image. Terraform or a documented deploy
script — not click-ops, or nobody else can redeploy it.

### Phase 8 — Operations
Per-tenant quotas and rate limits (§2.7 — server-side watsonx calls are now *your* bill).
Structured logging with tenant/session IDs and **no memory content in logs**. Metrics:
retrieval p50/p95/p99 against the 8 s budget, capture success rate, `added: 0` rate. Backups,
and a `rebob migrate --to-server` for existing local users.

---

## 7. What stays exactly the same

Worth being explicit, because it's most of the value and none of the risk:

- The five MCP tools and their signatures (`contract.py`) — frozen public API, unchanged.
- The whole distillation pipeline: `assemble` → `redact` → `salience` → `extract` → `resolve`.
  Pure functions over a transcript; they relocate, they don't get rewritten.
- The retrieval algorithm: dense + sparse + structural → RRF → rerank → score → pack. Only the
  *storage calls underneath it* change.
- `rebob.paths` and the local-mode layout, for anyone staying local.
- All 187 existing tests, as the regression net for every phase.

---

## 8. Latency budget (the constraint that decides the design)

`UserPromptSubmit` hard timeout: **8000 ms**. Rough current spend:

| Stage | Now (local) | Hosted |
|---|---|---|
| Process cold start | 300–2000 ms (Windows, per call) | ~0 (warm server) |
| Query embed (watsonx) | 200–500 ms | 200–500 ms (server-side, cacheable) |
| Candidate fetch | full scan, grows unbounded | indexed, ~10 ms |
| Rerank (watsonx) | 300–800 ms | 300–800 ms |
| Network | 0 | 50–200 ms |

Hosted is plausibly **faster than local today**, because eliminating per-call Python cold start
on Windows more than pays for the network hop. Worth measuring and stating — it reframes hosting
as a performance win, not just a convenience.

Two levers if it gets tight: server-side embedding cache (the `embed_cache` concept already
exists, `watsonx.py:_cache_dir`), and making rerank optional under a deadline — skip it and
return RRF order rather than blow the budget.

---

## 9. Decisions needed before starting

1. **Trust model — the big one.** Does the hosted server see redacted transcripts in plaintext?
   Options: (a) plaintext + redaction + strong isolation, simplest, requires users to trust the
   host; (b) client-side encryption of raw sessions in the lake, server decrypts only to
   distill; (c) BYO-storage — user supplies their own COS bucket + Postgres, we host only
   compute. **This changes the architecture, so decide it first.** (c) is the strongest
   enterprise story; (a) is the fastest path to a demo.

2. **Who pays for watsonx?** Server-side key with per-tenant quotas, or bring-your-own-key per
   tenant? BYO-key removes the whole abuse/billing surface at the cost of a rougher onboarding.

3. **Tenancy default:** is a new user's memory private-by-default (`personal`) or shared with
   their repo (`project`)? Affects the demo more than the code — team sharing is the compelling
   story, private-by-default is the safe one.

4. **Postgres + pgvector, or watsonx.data Milvus?** My recommendation is Postgres for v1 (§4).
   If there's a hackathon/product reason to showcase watsonx.data specifically, that's a
   legitimate reason to override the engineering default — but know that's the tradeoff.

5. **Hosting target:** Code Engine (recommended — scale-to-zero, managed HTTPS), Kubernetes/ROKS,
   or a VM?

6. **Does local mode stay a supported product, or become dev-only?** I'd keep it supported
   (principle #1), but it's a real maintenance cost and worth saying out loud.

---

## 10. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Raw secrets shipped to server | Data exfiltration; kills adoption | Phase 2 lands before any network code. Non-negotiable ordering. |
| Cross-tenant leak | Catastrophic, unrecoverable trust loss | Postgres RLS (DB-enforced, not app-enforced) + explicit isolation tests |
| Hook latency blows the 8 s budget | Silent degradation — memory just stops working, no error | Budget in §8, deadline-aware rerank, fail-open, p99 alerting |
| `vector_row` migration | Positional indices break silently, wrong memories retrieved | Stable UUIDs in Phase 1, before anything depends on them |
| Server outage blocks every user's prompt | Worse than no memory at all | Fail-open contract + circuit breaker; test by killing the server mid-session |
| watsonx cost/abuse | Uncapped spend on your account | Per-tenant quotas in Phase 8, or BYO-key (decision #2) |
| Local and hosted diverge | Two codebases, double the bugs | `StorageBackend` in Phase 1; same test suite against both |

---

## 11. Suggested sequence

```
 1. feat(store): StorageBackend protocol + SqliteBackend behind it
 2. refactor(store): stable embedding_id, retire positional vector_row
 3. feat(redact): redact at record() time + transmission allowlist
 4. test(redact): end-to-end secret-never-persisted test
 5. feat(store): PostgresBackend — pgvector + tsvector + pooling
 6. test(store): run the full backend suite against both backends
 7. feat(lake): COS raw-zone writer, async, partitioned
 8. feat(lake): Iceberg curated tables + replay job
 9. feat(auth): bearer tokens, org_id/visibility, repo_url normalization
10. feat(auth): Postgres RLS wired to authenticated principal
11. test(auth): cross-tenant isolation suite
12. feat(server): FastMCP streamable-http + healthz/readyz
13. feat(client): HTTP client, hook local/hosted switch, fail-open
14. feat(cli): rebob login, rebob init --server
15. chore(deploy): Code Engine + IaC
16. feat(ops): quotas, metrics, structured logging
17. feat(cli): rebob migrate --to-server
```

---

## Appendix — file reference for the audit in §2

| Finding | Location |
|---|---|
| Raw event written unredacted | `rebob/core/api.py:180-189` |
| Redaction only at distillation | `rebob/core/worker.py:80-82` |
| Redaction field list (make it an allowlist) | `rebob/core/redact.py:165` |
| `append_vector` read-modify-write | `rebob/core/store.py:208-224` |
| Retrieval full scan — all rows | `rebob/core/retrieve.py:266` |
| Retrieval full scan — all vectors | `rebob/core/retrieve.py:88` |
| Dense search Python loop | `rebob/core/retrieve.py:81` |
| Retrieval swallows all errors | `rebob/core/retrieve.py:246-250` |
| Unused tenancy columns | `rebob/core/store.py:34-37` |
| `scope` hardcoded to "repo" | `rebob/core/resolve.py:137` |
| Hook in-process calls | `rebob/hook.py:39` |
| Hook never-crash contract | `rebob/hook.py:53-56` |
| Hook timeouts (8 s / 5 s / 5 s) | `rebob/commands/_util.py:68-70` |
| Frozen tool contract | `rebob/contract.py` |
