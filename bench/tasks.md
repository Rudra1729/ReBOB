# Benchmark task pairs (Galaxium Travels)

Six pairs, run against a real clone of [IBM/galaxium-travels](https://github.com/IBM/galaxium-travels)
(`booking_system_backend`, Python/FastAPI). Each pair is a *learning* task (hits a real problem,
resolves it) followed by a later, differently-phrased *test* task that needs the same underlying
knowledge to go smoothly.

**Arm 1 (this run):** memory OFF (stub brief) — run only the **test** task half of each pair, in a
fresh Bob task, cold. This is the baseline: no session memory, whatever's in `AGENTS.md`/README is
all the agent has going in.

**Arm 2 (Phase 4):** run all 6 **learning** tasks first (recorded passively), then re-run the same
6 **test** tasks in fresh Bob tasks, memory ON, and compare.

## A note on how these were chosen

Two of the six (#1 and #2 below) are **verified stale documentation** — `AGENTS.md` and the README
both describe an MCP integration pattern that a later commit (`e668e44`, "Replace hand-rolled MCP
tools with fastapi-mcp") already replaced, and the docs were never updated. That's the strongest,
most honest kind of pair for this benchmark: a cold agent trusting the static docs gets actively
misled, and no amount of re-reading `AGENTS.md` fixes it — only actually hitting the real code does.
The other four are real, currently-accurate patterns in the codebase (verified by reading the
source, not just quoting `AGENTS.md`), framed so the *learning* task requires actually hitting the
concrete failure and diagnosing it rather than just reciting a documented rule — since an agent
under token pressure often misses or misapplies static doc content anyway, actually hitting the
failure once is a distinct, real learning event.

---

## Pair 1 — MCP tools are now auto-generated, not hand-written

**memory_type:** `gotcha` / stale doc

`AGENTS.md` and the README both say: "add a REST handler **and** a matching MCP tool, following
the pattern in `server.py`" and describe `FastMCP` being instantiated before `FastAPI`. Neither is
true anymore — `server.py` now uses `fastapi_mcp.FastApiMCP(app)` (`server.py:336-337`), which
auto-generates MCP tools from the existing FastAPI routes. There is no hand-written MCP tool
pattern to follow; adding one manually would just duplicate an already-auto-generated tool.

- **Learning task:** "Add a new REST endpoint `GET /flights/{flight_id}` that returns a single
  flight's details (404 if not found), following the pattern of the existing endpoints in
  `server.py` and `services/flight.py`. Per `AGENTS.md`, also add the matching MCP tool for it."
- **Test task (later, fresh task):** "Add a new REST endpoint `GET /users/{user_id}` that returns
  a single user's details by ID. Make sure it's usable by AI agents the same way the other
  endpoints are."

## Pair 2 — Test isolation uses `dependency_overrides`, not a dual `SessionLocal` patch

**memory_type:** `gotcha` / stale doc

`AGENTS.md` says tests "patch `SessionLocal` in two places... patching only one leaves MCP tools
hitting the real DB," citing `conftest.py` lines 49-50. The real `conftest.py`'s `client` fixture
instead overrides the `get_db` FastAPI dependency directly
(`server.app.dependency_overrides[db_module.get_db] = override_get_db`) — one override, no
`SessionLocal` patching at all, and it's not at lines 49-50 anymore either.

- **Learning task:** "Write a pytest test for the `GET /flights/{flight_id}` endpoint you just
  added (or `GET /bookings/{user_id}` if that one isn't done yet), following `AGENTS.md`'s guidance
  on patching `SessionLocal` in two places so tests don't hit the real database."
- **Test task (later, fresh task):** "Write a pytest test for the `GET /user` endpoint that
  confirms it doesn't touch the real `booking.db` file."

## Pair 3 — `book_flight` validates both `user_id` AND `name` on purpose

**memory_type:** `security_note` / `decision`

`services/booking.py:51-65` — a booking request is rejected with `NAME_MISMATCH` if `user_id`
exists but the provided `name` doesn't match the registered name. This looks like a bug on first
read (why would a valid user ID get rejected?) but it's an intentional non-standard identity check.

- **Learning task:** "A user reports that booking a flight with their correct `user_id` but a
  nickname instead of their registered name gets rejected with a 409 'Name mismatch' error.
  Investigate `POST /book` and `services/booking.py` and decide whether this is a bug to fix or
  intended behavior to document/test."
- **Test task (later, fresh task):** "Add a new endpoint `POST /bookings/{booking_id}/seat-class`
  to let a user upgrade their seat class on an existing booking. Make sure it enforces the same
  identity checks as booking creation."

## Pair 4 — Service functions return `BookingOut | ErrorResponse`, never raise

**memory_type:** `api_contract`

Every function in `services/booking.py` (and the other service modules) returns a Pydantic model
or an `ErrorResponse` — never raises an exception for expected failure cases. Callers in
`server.py` check `isinstance(result, ErrorResponse)` and translate that into the right HTTP status.

- **Learning task:** "Add `services/flight.py::get_flight_details(flight_id)` plus a
  `GET /flights/{flight_id}/details` endpoint that returns 404 cleanly when the flight doesn't
  exist. Wire it up the way the other service functions in this codebase handle a not-found case."
  (If this overlaps with Pair 1's learning task, treat this as reinforcement of the same lesson via
  a second function — `get_user_details` on the user service instead.)
- **Test task (later, fresh task):** "Add `services/user.py::deactivate_user(user_id)` plus an
  endpoint for it, handling the case where the user doesn't exist."

## Pair 5 — The Java proxy swallows failures as HTTP 200 with an `error` body

**memory_type:** `api_contract` / `gotcha`

`server.py`'s `/quotes`, `/holds/*` proxy endpoints (lines 242-330) catch `httpx.HTTPError` and
return `{"error": "..."}` with HTTP **200** — the frontend must check the response body, not the
HTTP status, to detect a failure (`booking_system_frontend/src/services/api.ts`).

- **Learning task:** "Add frontend handling in the holds flow so that if releasing an
  already-released hold fails, the UI shows an error banner instead of silently treating it as
  success. Your first pass checking `response.ok` won't catch it — find out why and fix it the way
  this codebase actually reports proxy failures."
- **Test task (later, fresh task):** "Add frontend error handling for confirming a hold that has
  already expired — make sure the UI actually detects and displays that failure."

## Pair 6 — `SEED_DEMO_DATA` re-seeds on every start; `.db` files are committed artefacts

**memory_type:** `env_setup`

`server.py:34` reseeds demo data on every startup if `SEED_DEMO_DATA` is unset or true (default),
**only if the DB is empty**. `booking.db`/`holds.db` are committed on purpose so a fresh clone has
data immediately, and get regenerated on startup.

- **Learning task:** "You added a test booking through the API, then restarted the backend to test
  something else, and the booking is gone / replaced by demo data. Figure out why and find the
  right way to keep your local test data across restarts."
- **Test task (later, fresh task):** "Set up local dev so a fresh teammate's clone still starts
  with the full demo dataset, but *your* ongoing local changes don't get wiped every time you
  restart the backend."

---

## Running Arm 1 (this pass)

For each pair, run only the **test task**, in a brand-new Bob task, memory off (stub brief). Record
per run: API cost (Bobcoins), tokens ↑/↓, context length at completion, turns, files read before
first edit, first-attempt success, rollbacks, wall clock — into `bench/results.csv`. Screenshot each
task's consumption summary to `bob_sessions/rebob_task0N_<desc>_summary.png`.
