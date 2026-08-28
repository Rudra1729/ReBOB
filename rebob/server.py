"""
rebob/server.py — ReBOB MCP server (Phase 1 stubs).

Transport: stdio — Bob is the MCP client.
Run:  python rebob/server.py
"""

# Ensure the repo root is on sys.path regardless of how this file is invoked
# (e.g. `python rebob/server.py` or via MCP config with an absolute path).
import sys as _sys
from pathlib import Path as _Path
_repo_root = str(_Path(__file__).resolve().parent.parent)
if _repo_root not in _sys.path:
    _sys.path.insert(0, _repo_root)

from fastmcp import FastMCP

from rebob import contract
from rebob.core.store import init_db

mcp = FastMCP("rebob")

# ── tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def mem_search(
    query: str,
    k: int = 8,
    budget_tokens: int = 600,
    session_id: str = "",
) -> str:
    """Search ReBOB memory and return a markdown brief."""
    return contract.mem_search(query, k=k, budget_tokens=budget_tokens, session_id=session_id)


@mcp.tool()
def mem_capture(
    session_id: str = "",
    label: str = "",
    summary: str = "",
) -> dict:
    """Distil a session into memory records (stub: writes a capture file)."""
    return contract.mem_capture(session_id=session_id, label=label, summary=summary)


@mcp.tool()
def mem_stats() -> dict:
    """Return aggregate memory counts."""
    return contract.mem_stats()


@mcp.tool()
def mem_why(id: str) -> dict:
    """Explain why a memory entry exists."""
    return contract.mem_why(id)


@mcp.tool()
def mem_feedback(id: str, verdict: str) -> dict:
    """Record whether a memory was useful or wrong."""
    return contract.mem_feedback(id, verdict)


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    mcp.run(transport="stdio")
