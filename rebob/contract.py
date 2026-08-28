"""
rebob/contract.py — Public contract for ReBOB memory functions.

All functions here are stubs.  Real implementations will be added later.
"""


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def mem_search(query: str, top_k: int = 5) -> list[dict]:
    """Return the top-k memory entries most relevant to *query*."""
    return []


def mem_capture(text: str, metadata: dict | None = None) -> str:
    """Store *text* as a new memory entry.  Returns the entry id."""
    return "stub-id"


def mem_stats() -> dict:
    """Return basic statistics about the memory store."""
    return {"total_entries": 0, "store": "stub"}


def mem_why(entry_id: str) -> str:
    """Explain why a memory entry was captured."""
    return f"No explanation available for entry '{entry_id}' (stub)."


def mem_feedback(entry_id: str, useful: bool) -> None:
    """Record whether a recalled memory was useful."""
    return


# ---------------------------------------------------------------------------
# Retrieval-augmented helpers
# ---------------------------------------------------------------------------

def search(query: str, top_k: int = 5) -> list[dict]:
    """Search across all sources (memory + external) for *query*."""
    return []


def record(text: str, source: str = "user", metadata: dict | None = None) -> str:
    """Persist *text* from *source*.  Returns the record id."""
    return "stub-record-id"
