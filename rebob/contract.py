"""
rebob/contract.py — Frozen public contract for ReBOB.

Signatures must not change without a team-wide agreement.
server.py and hook.py both import from here.
"""

from rebob.core import api


# ---------------------------------------------------------------------------
# MCP-facing tools (called by Bob via FastMCP)
# ---------------------------------------------------------------------------

def mem_search(
    query: str,
    k: int = 8,
    budget_tokens: int = 600,
    session_id: str = "",
) -> str:
    """Return a markdown memory brief of up to *k* entries within *budget_tokens*."""
    return api.mem_search(query, k=k, budget_tokens=budget_tokens, session_id=session_id)


def mem_capture(
    session_id: str = "",
    label: str = "",
    summary: str = "",
) -> dict:
    """Distil a session into memory records.

    Returns ``{"added": int, "updated": int, "rejected": int, "ids": list[str]}``.
    """
    return api.mem_capture(session_id=session_id, label=label, summary=summary)


def mem_stats() -> dict:
    """Return aggregate counts from the memory store."""
    return api.mem_stats()


def mem_why(id: str) -> dict:
    """Explain why a memory entry exists and where it came from."""
    return api.mem_why(id)


def mem_feedback(id: str, verdict: str) -> dict:
    """Record whether a recalled memory was useful or wrong.

    *verdict* must be ``"useful"`` or ``"wrong"``.
    """
    return api.mem_feedback(id, verdict)


# ---------------------------------------------------------------------------
# Hook-facing helpers (called in-process by .rebob/hook.py)
# ---------------------------------------------------------------------------

def search(query: str, session_id: str = "") -> str:
    """Return a memory brief for injection into a prompt."""
    return api.search(query, session_id=session_id)


def record(event: dict) -> None:
    """Persist a lifecycle event emitted by the hook."""
    api.record(event)
