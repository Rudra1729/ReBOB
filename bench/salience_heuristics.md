# Salience heuristics

`rebob/core/salience.py`'s `score(transcript, explicit=False) -> float` decides how much a
session is worth extracting into memory, on a 0.0-1.0 scale. It's free (no watsonx call) so it
runs on every `Stop` event before the expensive extraction step does.

## Explicit capture always wins

If the user ran `/mem` (`explicit=True`), the score is always **1.0**, no heuristics applied.
An explicit "save this" is a stronger signal than anything we can infer from the transcript, so
it always extracts.

## The five signals

| Signal | Weight | What it detects | Why it's worth a boost |
|---|---|---|---|
| Error -> resolution | 0.30 | An error/exception/traceback/failure keyword appears, then a passed/success/ok/fixed/resolved keyword appears later in the same transcript | This is the session that re-derives a lesson every time it's missing: hitting a bug and fixing it is exactly the "what was tried, what failed, why a decision went the way it did" content the architecture doc says only exists in the session |
| Tests red -> green | 0.30 | An `N failed` count followed later by an `N passed` count (N > 0 in both) | Same shape as error->resolution but grounded in a test run instead of free text, so it's a stronger, less falsifiable signal — a real before/after outcome, not just wording |
| Rollback present | 0.15 | `rollback`, `rolled back`, `roll back`, `revert(ed)`, `undo(ne)` in any entry's text or tool name | A rollback means an approach was tried and abandoned — that's a `decision`/`failure_mode` candidate (a rejected option worth not re-proposing), even without an explicit error message |
| Files touched | 0.15 | Count of distinct file paths seen in tool inputs, capped at 5 | More files touched suggests more surface area was actually worked through (a real task), not a one-line question-and-answer; capped because touching 20 files isn't 4x more salient than touching 5 |
| Turn count | 0.10 | Number of transcript entries, capped at 20 | A longer back-and-forth correlates with the session mattering more than a single throwaway prompt, but it's the weakest signal on its own (a long session can still be low-value chatter), hence the smallest weight |

Weights sum to 1.0, so a session tripping every heuristic maximally scores 1.0 without needing
the explicit-capture shortcut.

## Where the text comes from

All five signals read from `_entry_text()`, which flattens every text-bearing field on a
transcript entry: `prompt`, `tool_response`, `last_assistant_message`, and (recursively
stringified) `tool_input`. `tool_response`/`tool_input`/`tool_name`/`last_assistant_message` are
the real field names Bob's hooks actually send — `output`/`input`/`tool` are also checked for
compatibility with hand-built transcripts, but they don't appear in real session data.

This match to the real schema was verified against an actual recorded session
(`tests/fixtures/sample_session.jsonl`): before the fix, `score()` only ever saw `prompt` text,
so it was blind to every tool result and every touched file, and a real session scored ~0.08
(turn count alone). After reading the real field names, the same session scores 0.59.

## What does *not* get a boost

- Plain reads/greps/globs with no error, no test run, no rollback, and few files — these look
  like normal exploration, not a lesson learned, and mostly get whatever the turn-count signal
  gives them.
- A test run that only ever passes (no prior failure) does not get the tests-red-to-green boost
  — passing on the first try isn't evidence of anything worth remembering.
- Success wording that appears *before* any error in the transcript doesn't trigger the
  error->resolution boost — order matters, since the point is capturing a fix, not just the
  presence of positive words.

## Known limitations

- Keyword matching is naive: it can't tell "the error was already fixed before this session
  started" from "we fixed it just now," and a session that talks *about* errors without hitting
  one could still trip the pattern.
- The heuristics don't currently look at `hook_event_name` distinctions beyond what `assemble.py`
  already normalizes into `type` (`prompt`/`tool`/`stop`).
- All caps and weights (0.30/0.30/0.15/0.15/0.10, files-touched cap of 5, turn-count cap of 20)
  are hand-picked, not tuned against benchmark data — Phase 2's Arm 1/Arm 2 comparison
  (`bench/tasks.md`, `bench/results.csv`) is the first real check on whether they're reasonable.
