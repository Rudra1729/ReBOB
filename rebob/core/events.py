"""Event field allowlist and sanitization for capture/transmission."""

from __future__ import annotations

from rebob.core.redact import redact_transcript

# Fail closed: only explicitly allowlisted fields may be stored or transmitted.
ALLOWED_EVENT_FIELDS = frozenset({
    "hook",
    "session_id",
    "prompt",
    "tool_name",
    "tool_input",
    "tool_response",
    "cwd",
    "hook_event_name",
    "tool_use_id",
    "last_assistant_message",
    # Legacy hook payloads (tests / older Bob versions)
    "type",
    "tool",
    "input",
    "output",
    # Tenancy context (populated from git/env in hosted mode)
    "repo_url",
    "branch",
    "author_id",
})


def filter_event_fields(event: dict) -> dict:
    """Drop unknown top-level keys (fail closed for future Bob fields)."""
    return {k: v for k, v in event.items() if k in ALLOWED_EVENT_FIELDS}


def sanitize_event(event: dict) -> dict:
    """Allowlist + redact a single lifecycle event before storage or transmission."""
    filtered = filter_event_fields(event)
    return redact_transcript([filtered])[0]


def sanitize_session_events(events: list[dict]) -> list[dict]:
    """Allowlist + redact an entire session transcript."""
    filtered = [filter_event_fields(e) for e in events]
    return redact_transcript(filtered)
