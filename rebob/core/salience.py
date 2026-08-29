"""
rebob/core/salience.py — heuristic salience scoring for a session transcript.

Owned by Person B. Second stage of the write-path pipeline:
assemble -> redact -> salience -> extract -> resolve -> embed -> store.
"""

import re

_ERROR_PATTERN = re.compile(r"\b(error|exception|traceback|failed|failure)\b", re.IGNORECASE)
_SUCCESS_PATTERN = re.compile(r"\b(passed|success|ok|fixed|resolved)\b", re.IGNORECASE)
_TEST_FAIL_PATTERN = re.compile(r"\b(\d+)\s+failed\b", re.IGNORECASE)
_TEST_PASS_PATTERN = re.compile(r"\b(\d+)\s+passed\b", re.IGNORECASE)
_ROLLBACK_PATTERN = re.compile(r"\b(rollback|roll(?:ed)?\s+back|reverted?|undo(?:ne)?)\b", re.IGNORECASE)

_WEIGHTS = {
    "error_resolution": 0.30,
    "tests_red_to_green": 0.30,
    "rollback": 0.15,
    "files_touched": 0.15,
    "turn_count": 0.10,
}

_FILES_TOUCHED_CAP = 5
_TURN_COUNT_CAP = 20


def score(transcript: list[dict], explicit: bool = False) -> float:
    """Score a transcript's worth capturing into memory, in [0.0, 1.0].

    ``explicit=True`` (user ran /mem) always scores 1.0. Otherwise the score
    sums weighted heuristic signals: an error followed later by a
    resolution, a test run going from failing to passing, any rollback, how
    many distinct files were touched, and overall turn count.
    """
    if explicit:
        return 1.0

    if not transcript:
        return 0.0

    total = 0.0
    total += _WEIGHTS["error_resolution"] * _error_then_resolution(transcript)
    total += _WEIGHTS["tests_red_to_green"] * _tests_red_to_green(transcript)
    total += _WEIGHTS["rollback"] * _has_rollback(transcript)
    total += _WEIGHTS["files_touched"] * _files_touched_ratio(transcript)
    total += _WEIGHTS["turn_count"] * _turn_count_ratio(transcript)

    return round(min(total, 1.0), 4)


_TEXT_FIELDS = ("prompt", "tool_response", "output", "last_assistant_message", "tool_input", "input")


def _stringify(value) -> str:
    if isinstance(value, dict):
        return " ".join(_stringify(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_stringify(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _entry_text(entry: dict) -> str:
    """Flatten every text-bearing field on an entry into one string.

    Real Bob hook payloads use ``tool_input``/``tool_response`` (and
    ``last_assistant_message`` on stop events); ``input``/``output`` are
    kept too for hand-built transcripts that don't come from a real hook.
    """
    return " ".join(_stringify(entry.get(key)) for key in _TEXT_FIELDS if entry.get(key))


def _error_then_resolution(transcript: list[dict]) -> float:
    saw_error = False
    for entry in transcript:
        text = _entry_text(entry)
        if not saw_error and _ERROR_PATTERN.search(text):
            saw_error = True
            continue
        if saw_error and _SUCCESS_PATTERN.search(text):
            return 1.0
    return 0.0


def _tests_red_to_green(transcript: list[dict]) -> float:
    saw_failure = False
    for entry in transcript:
        text = _entry_text(entry)
        fail_match = _TEST_FAIL_PATTERN.search(text)
        if fail_match and int(fail_match.group(1)) > 0:
            saw_failure = True
            continue
        pass_match = _TEST_PASS_PATTERN.search(text)
        if saw_failure and pass_match and int(pass_match.group(1)) > 0:
            return 1.0
    return 0.0


def _has_rollback(transcript: list[dict]) -> float:
    for entry in transcript:
        if _ROLLBACK_PATTERN.search(_entry_text(entry)):
            return 1.0
        for key in ("tool_name", "tool"):
            if _ROLLBACK_PATTERN.search(str(entry.get(key, ""))):
                return 1.0
    return 0.0


def _files_touched_ratio(transcript: list[dict]) -> float:
    files = set()
    for entry in transcript:
        for input_key in ("tool_input", "input"):
            candidate = entry.get(input_key)
            if isinstance(candidate, dict):
                for key in ("path", "file", "file_path"):
                    if candidate.get(key):
                        files.add(str(candidate[key]))
    return min(len(files) / _FILES_TOUCHED_CAP, 1.0)


def _turn_count_ratio(transcript: list[dict]) -> float:
    return min(len(transcript) / _TURN_COUNT_CAP, 1.0)
