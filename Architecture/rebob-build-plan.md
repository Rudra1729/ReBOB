# ReBOB — 48-Hour Build Plan (v2, hooks architecture)

Two people. All times ET. **A** = server, pipeline, retrieval. **B** = hooks, Bob config, evidence, video.
Every phase ends in a **gate**. Do not start the next phase until the gate passes.

Rule for the weekend: **one deep hole.** If it isn't in this plan, it isn't in the submission.

---

## Roles


|               | Person A                                                                                             | Person B                                                                            |
| ------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Owns          | `rebob/core/` — SQLite store, watsonx client, redaction, extraction, resolver, retrieval, MCP server | `.rebob/hook.py`, `.bob/` config, benchmark harness, screenshots, video, submission |
| Never touches | `.bob/`, `.rebob/hook.py`                                                                            | `rebob/core/` *(except Phase 2 — see below)*                                        |


The hook script is the one place your work meets. It imports A's `search()` and `record()` and does nothing else clever. Agree that boundary at hour 1 and keep it.

**Phase 2 exception:** B owns `assemble.py` and `salience.py` inside `rebob/core/`. Freeze interfaces at 19:00; A owns `worker.py` orchestration.

---



## PHASE 0 — Setup and de-risk

**Aug 28, 10:00–12:00 · both**

- [ ] **B, 10:00 sharp:** request the team IBM Cloud account (one person only — the button greys out for the other). **2h activation lag**, so this is the first thing anyone does.
- [ ] **B:** register the team on the platform, confirm both emails, name a Team Lead.
- [x] **Both:** confirm the Bob invite (`ibm-hackathon-xxxx`, Enterprise plan). Create IBMid if needed.
- [x] **Both:** install Bob IDE **v2.0.2+**. Log in.
- [x] **Both:** Settings → General → switch team to `ibm-coding-challenge-uat` **(us-east)**. Confirm Budget 40.00. Screenshot — this is your zero point.
- [x] **Both:** Settings → Chat → **set Task retention to 0** (requires 2.0.3+) or 90 days. Default is 14 days and it deletes your evidence.
- [x] **Both:** verify `python` resolves on PATH from a plain `cmd` shell. Hooks run via `cmd /c` on Windows.
- [x] **A:** repo from the **IBM Hackathon template** (ships `.gitignore` + `.bobignore`). **First commit at or after 10:00.** Push.
- [x] **A:** add `.rebob/`, `*.npy`, `.env` to both ignore files.
- [x] **A:** write `contract.py` — the five MCP signatures plus `search(query, session_id) -> str` and `record(event: dict) -> None` for the hook. Push. **Frozen from here.**
- [ ] **B:** clone **Galaxium Travels** (IBM's own tutorial app — zero setup risk, judges know it). Get it running.
- [x] **B:** enable "Enable MCP tools for new tasks" in Settings → MCP.
- [x] **Both:** join Slack `#support_dev_day_hackathon_aug_2026`.

**GATE G0** — repo with post-10:00 first commit · both Bobs on the hackathon instance · task retention raised · `python` works from `cmd` · Galaxium runs · contract frozen.

*(The v3 filesystem-archaeology spike is gone. Hooks are documented; there is nothing to discover.)*

---



## PHASE 1 — Prove both wires with fakes

**Aug 28, 12:00–16:00**

The most important phase. There are now **two** wires into Bob, and the hook is the critical one.

**Person B — hooks**

- [x] `.rebob/hook.py` — reads JSON from stdin, dispatches on `argv[1]` (`prompt` / `tool` / `stop`)
- [x] Appends every event to `.rebob/sessions/<session_id>.jsonl`
- [x] On `prompt`: prints a **hardcoded** two-line brief to stdout
- [x] **try/except around everything,** `sys.exit(0)` **unconditionally**
- [x] `.bob/settings.json` registering `UserPromptSubmit`, `PostToolUse`, `Stop` with absolute paths
- [x] `.bob/rules/rules.md` — ≤15 lines
- [x] `/mem` custom slash command

**Person A — server**

- [x] `rebob/server.py` — FastMCP, stdio, five tools registered
- [x] `mem_search` returns a hardcoded brief; `mem_capture` writes a file; `mem_stats` returns zeros
- [x] SQLite schema created on first run
- [x] `.bob/mcp.json` entry (hand to B to install)

**TEST T1 — three checks, in this order**

1. Type any prompt in Bob. Does the hardcoded brief appear in the model's context? (Ask Bob "what memory brief did you receive?")
2. Does `.rebob/sessions/<id>.jsonl` fill with prompt + tool events including tool **output**?
3. In a fresh task, does Bob call the MCP `mem_search` tool and show the brief?

**Then break it on purpose:** put `raise Exception` at the top of `hook.py`. Send a prompt. **The prompt must still go through.** If it doesn't, your exit-code handling is wrong and it will kill your demo. Fix it now.

**GATE G1 (hard deadline 16:00)** — injection works, recording works, MCP works, and a crashing hook does not block prompts.
**If G1 is red at 16:00, stop and escalate in Slack.** Do not build pipeline code on a broken wire.

---



## PHASE 2 — Real pipeline + baseline data

**Aug 28, 16:00–22:00**

G1 is green. Now build the write path and collect the control-arm baseline.

**Phase 2 splits** `rebob/core/` **by module** — both people write pipeline code. The Phase 1 boundary (B never touches `rebob/core/`) is relaxed here to avoid overloading one person. **Freeze function signatures at 19:00.** Merge branches and run T2 together at 21:00.

### Write-path chain

```
Stop marker → assemble → redact → salience → extract → resolve → embed → store
                 B          A         B         A        A       A      A
```



### Frozen interfaces (agree at 19:00, do not change without a Slack ping)

```python
# assemble.py (B)
def assemble(session_id: str, jsonl_path: Path) -> list[dict]: ...

# redact.py (A)
def redact(text: str) -> tuple[str, list[str]]: ...  # cleaned text, patterns matched

# salience.py (B)
def score(transcript: list[dict], explicit: bool = False) -> float: ...

# extract.py (A)
def extract(transcript: list[dict], salience: float) -> list[dict]: ...  # raw memory dicts

# resolve.py (A)
def resolve(records: list[dict]) -> dict: ...  # {"added", "updated", "rejected", "ids"}
```

`worker.py` (A) orchestrates the chain. B does not edit `worker.py`.

---



### Person A — cloud, security, extraction, storage

`rebob/core/`

- [x] Expand `store.py` to full architecture schema (§7) before any pipeline writes
- [x] `watsonx.py` — IAM token with **refresh at 55 min**, project ID, Dallas endpoint
- [x] Embedding call + cache by content hash
- [x] `redact.py` — API keys, bearer tokens, `.env` patterns, emails, IPs, entropy threshold
- [x] `extract.py` — Granite, strict JSON, one atomic claim per record; loads few-shots from `bench/extract_few_shots.json`
- [x] Validator: drop malformed, drop confidence < 0.4
- [x] `resolve.py` — claim_key, ADD / UPDATE / SUPERSEDE / NOOP / REJECT
- [x] `worker.py` — watches for Stop markers, runs the pipeline end-to-end

**Tests (A runs)**

- [ ] `tests/test_redact.py` — make B's redact test vectors pass **before** any real session hits watsonx
- [ ] Run `assemble` → full pipeline on `tests/fixtures/sample_session.jsonl`
- [ ] Operate the pipeline for **T2** (B reviews output)

---



### Person B — transcript, ranking, benchmarks, fixtures

`rebob/core/`

- [ ] `assemble.py` — session JSONL → ordered transcript of prompts, tools, outputs
- [ ] `salience.py` — heuristics per `bench/salience_heuristics.md`: error→resolution, tests red→green, rollbacks, files touched, turn count

`bench/`**,** `tests/`**,** `bob_sessions/`

- [ ] Export `tests/fixtures/sample_session.jsonl` from a rich G1 Bob session (hand to A by **16:15**)
- [ ] `bench/extract_few_shots.json` — 3 examples (`gotcha`, `decision`, `env_setup`) for A's extractor
- [ ] `bench/salience_heuristics.md` — document what gets a salience boost and why
- [ ] `tests/test_redact.py` — define nasty strings (API keys, emails, tokens); A implements `redact.py` to pass
- [ ] `tests/test_assemble.py` + `tests/test_salience.py` — own these
- [ ] Write **6 benchmark task pairs** on Galaxium. Each pair = a *learning* task (hits a problem, resolves it) and a later *test* task needing the same knowledge but not identical. Commit as `bench/tasks.md`.
- [ ] `bench/results.csv` template (columns from Metrics section below)
- [ ] Run all 6 **test** tasks in fresh Bob tasks, **memory off** (stub brief is fine). Arm 1.
- [ ] Record per run: **API Cost (Bobcoins)**, Tokens ↑/↓, Context Length, turns, files read before first edit, first-attempt success, rollbacks, wall clock
- [ ] Screenshot every task session consumption summary → `bob_sessions/rebob_task01_<desc>_summary.png`

**Tests (B runs)**

- [ ] Arm-1 Galaxium runs + screenshots (does **not** need A's pipeline — baseline is cold Bob)
- [ ] **T2 review** — read every extracted record aloud with A: atomic? true? non-obvious? any secrets?

---



### What is parallel vs what needs both


| Work                                           | Parallel?                     | Notes                             |
| ---------------------------------------------- | ----------------------------- | --------------------------------- |
| B writes `bench/tasks.md`, fixtures, few-shots | Yes — start now               |                                   |
| B runs arm-1 on Galaxium (memory off)          | Yes — stub brief OK           | Hooks still record JSONL for A    |
| A builds watsonx + redact + schema             | Yes — start now               |                                   |
| A builds extract + resolve + worker            | Yes — after interfaces frozen | Can dev against B's fixture JSONL |
| **T2** — real session → pipeline → DB records  | **No — together ~21:00**      | A runs; B reviews                 |
| **G2**                                         | **No — together**             | Pipeline + arm-1 both required    |


---



### Hour-by-hour (16:00–22:00 ET)


| Time            | Person A                                                                              | Person B                                                                     |
| --------------- | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **16:00–18:00** | Schema + `watsonx.py` + `redact.py`                                                   | Galaxium running + `assemble.py` + `sample_session.jsonl` + `tasks.md` draft |
| **18:00**       | **5-min sync** — interfaces check, fixture handoff                                    | **5-min sync**                                                               |
| **18:00–20:00** | `extract.py` + validator + `resolve.py` start                                         | `salience.py` + few-shots + redact test vectors + arm-1 tasks 1–3            |
| **20:00**       | `resolve.py` finish + `worker.py`                                                     | arm-1 tasks 4–6 + screenshots + `results.csv`                                |
| **21:00–22:00** | **Together:** T2 on one rich JSONL session · fix redaction if secrets leak · G2 check | **Together:** T2 review · G2 check                                           |
| **22:00**       | **Sleep.**                                                                            | **Sleep.**                                                                   |


**Branches:** `a/pipeline-cloud` and `b/pipeline-transcript`. Merge to `main` at 21:00 for T2.

---

**TEST T2** — run one real recorded session through the pipeline. A operates; B reads every record aloud. Atomic? True? Non-obvious? Any secrets? If yes to the last one, stop and fix redaction before anything else.

**GATE G2** — one session yields ≥5 records you'd defend to a judge · zero secrets in the DB · arm-1 baseline complete with screenshots.

**22:00 — both sleep.** A tired Saturday is how this fails.

---



## PHASE 3 — Retrieval, dedup, backfill

**Aug 29, 08:00–13:00**

**Person A**

- [x] Dense (cosine over `.npy`) + sparse (FTS5) + structural (file anchors), top 30 each
- [x] Reciprocal rank fusion → watsonx rerank on top 20
- [x] Scoring, budget packing to 600 tokens, cited IDs
- [x] **Session dedup:** `.rebob/injected/<session_id>.json`, filter already-injected IDs
- [x] **Degradation:** skip rerank if slow, local-only if watsonx unreachable, never exceed 8s
- [x] `mem_why` and `mem_feedback` (30 min total, high judging value)

**Person B**

- [ ] Swap the hardcoded brief for A's real `search()`
- [ ] **Retroactive flow:** Tasks panel → re-open a past task → `/mem` → records land. Rehearse until it's one smooth motion.
- [ ] **AGENTS.md flow:** `/init` on Galaxium → screenshot its token cost → capture it → replace with the stub → screenshot the new cost
- [ ] 5 fixed queries in `bench/retrieval.md` with the memory IDs you expect back — A's regression check

**TEST T3**

- Run B's 5 queries. ≥4 of 5 return the expected memory in the top 3.
- **Ten-prompt session test:** send ten prompts in one task and watch tokens injected per prompt. It must fall toward zero. If it doesn't, dedup is broken and you are recreating the problem you're solving.
- Pull the network cable mid-session. Prompts must still work.

**GATE G3** — briefs under 600 tokens · retrieval precision acceptable · injection decays across a session · offline degradation verified · retroactive capture demonstrated on a task from yesterday.

---



## PHASE 4 — Treatment arm and the chart

**Aug 29, 13:00–16:00 · both**

- [ ] Seed memory: run all 6 **learning** tasks (recorded passively — that's the point)
- [ ] Run all 6 **test** tasks in fresh tasks, memory on. Arm 2.
- [ ] Same metrics, same screenshots
- [ ] `bench/results.csv` complete; chart via matplotlib; commit PNG **and** script
- [ ] Headline numbers: % Bobcoin reduction per task · % token reduction · first-attempt success rate · AGENTS.md tokens replaced · tokens injected per session

**TEST T4** — sanity-check the direction of every metric. If memory made something worse, say so in the video. Six perfect green bars reads as fabricated; an honest mixed result reads as competent.

**GATE G4** — a chart with real numbers is in the repo.

**16:00 — FEATURE FREEZE.** Bug fixes to demo paths only.

---



## PHASE 5 — Deliverables and the early draft submit

**Aug 29, 16:00–21:00**

- [ ] **A:** README — problem, architecture diagram, clean-clone run instructions, `.env.example` with no real keys
- [ ] **A:** clean-clone test on B's machine. It must run.
- [ ] **A:** secret scan the repo. Then eyeball every `bob_sessions/` screenshot for visible keys.
- [ ] **B:** problem + solution statement, **≤500 words**
- [ ] **B:** Bob usage statement — name **lifecycle hooks**, MCP, slash commands, modes, subagents, parallel tasks, rollback, document understanding, and where watsonx does embeddings / rerank / extraction
- [ ] **B:** confirm `bob_sessions/` has **both** members' PNGs, clearly named
- [ ] **B:** record a **rough** video, complete, uploaded publicly

- [ ] **21:00 — SUBMIT A DRAFT.** All fields, rough video link, real repo link.

The confirmation email carries **AI Submission Advisor** feedback flagging weak areas. Submitting early buys that for free. Resubmission requires **re-entering all deliverables**, not just the changed one.

**GATE G5** — draft submitted, confirmation received.

---



## PHASE 6 — Video and advisor fixes

**Aug 29 21:00 → Aug 30 06:00**

**3:00 hard maximum. ≥90 seconds must be the solution running on screen.**


| Time      | Beat                                                                                                                                                                              |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0:00–0:30 | The problem in IBM's words: compaction is lossful, best under 50%, "new task, not stored, because of security", **history deleted after 14 days**. Hover the real context window. |
| 0:30–0:45 | Guides vs Sensors. "Bob gave us both ends of the wire — `PostToolUse` is the sensor, `UserPromptSubmit` is the guide."                                                            |
| 0:45–1:15 | Cold Bob on a test task: crawls files, re-derives yesterday's lesson, gets it wrong. Show the Bobcoin cost.                                                                       |
| 1:15–1:50 | Memory on. **You type nothing extra** — the brief is already in context. Straight to the right files, passes first attempt. Lower cost on screen.                                 |
| 1:50–2:20 | **The forgotten session.** Re-open Tuesday's task, `/mem`. Show one memory **rejected** for contradicting a pinned record.                                                        |
| 2:20–2:40 | AGENTS.md captured and deleted: 2,700 tokens always-on → ~600 tokens once per session.                                                                                            |
| 2:40–3:00 | The chart. One line: `PreToolUse` can block a write that violates a pinned memory — memory with teeth. Stop.                                                                      |


- [ ] Record, edit, upload public (YouTube/Vimeo/Drive), verify in incognito
- [ ] Apply the advisor feedback from the draft
- [ ] Final secret scan; re-export any new sessions

---



## PHASE 7 — Final submit

**Aug 30, 06:00–08:00**

- [ ] Clean-clone dry run
- [ ] Re-enter **all** deliverables, resubmit
- [ ] Confirmation received
- [ ] **08:00 — done. Touch nothing.** No changes are permitted after the deadline.

Buffer 08:00–10:00 exists because something will go wrong. Do not spend it on features.

---



## Metrics

Every number is on the **task session consumption summary**, which you're screenshotting anyway as a deliverable.


| Metric                           | Source                       | Why it lands                                       |
| -------------------------------- | ---------------------------- | -------------------------------------------------- |
| **API Cost (Bobcoins) per task** | Consumption summary          | IBM's own billing unit. Headline.                  |
| Tokens ↑ / ↓                     | Consumption summary          |                                                    |
| Context Length at completion     | Consumption summary          | Ties to "best performance under 50%"               |
| **Tokens injected per session**  | ReBOB logs                   | Proves we don't recreate the AGENTS.md problem     |
| Turns to accepted solution       | Count                        |                                                    |
| Files read before first edit     | `PostToolUse` log — free now | Onboarding cost, made visible                      |
| Rollbacks                        | Bob rollback events          | Rework proxy. Bob-native. Nobody else will use it. |
| First-attempt test pass          | `PostToolUse` output         | Captured automatically by the recorder             |
| AGENTS.md tokens replaced        | Context window before/after  | 2,700 → ~600                                       |


Report **per-pair deltas**, not grand averages. Six pairs is a small sample — say so.

---



## Submission checklist

- [ ] Video URL public, ≤3:00, ≥90s live demo, narrated
- [ ] Problem + solution statement ≤500 words
- [ ] Bob usage statement, specific
- [ ] Public repo URL
- [ ] `bob_sessions/` with **both members'** PNG screenshots, clearly named
- [ ] Runs from a clean clone
- [ ] Zero credentials anywhere, including inside screenshots
- [ ] English throughout
- [ ] Affiliation disclosed (UMass)
- [ ] Age declaration completed
- [ ] Submitted by **08:00**, not 09:55

---



## Standing rules

1. **Gate before you proceed.** A red gate means stop, not carry on hopefully.
2. **G1 by 16:00 Friday**, including the deliberate-crash test. That's the one non-negotiable.
3. The hook must never block a prompt. Ever. Re-test this after every change to `hook.py`.
4. Screenshot every consumption summary as you go — deliverable *and* data.
5. Commit hourly. Git history is your originality proof.
6. Not in Phase 1–4 = doesn't exist. It goes on the roadmap slide.
7. Sleep Friday night. Both of you.

