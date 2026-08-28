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

import json
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP

from rebob.core.store import init_db

# ── startup ──────────────────────────────────────────────────────────────────
init_db()

mcp = FastMCP("rebob")

_CAPTURES_DIR = Path(".rebob") / "captures"

# ── tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def mem_search(
    query: str,
    k: int = 8,
    budget_tokens: int = 600,
    session_id: str = "",
) -> str:
    """Search ReBOB memory and return a markdown brief."""
    return (
        "## ReBOB Memory Brief\n\n"
        "- [mem_001] Galaxium uses SQLite for article storage.\n"
        "- [mem_002] Run `make setup` before `make start`.\n"
    )


@mcp.tool()
def mem_capture(
    session_id: str = "",
    label: str = "",
    summary: str = "",
) -> dict:
    """Distil a session into memory records (stub: writes a capture file)."""
    _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"session_id": session_id, "label": label, "summary": summary, "ts": ts}
    (_CAPTURES_DIR / f"{ts}.json").write_text(json.dumps(payload, indent=2))
    return {"added": 0, "updated": 0, "rejected": 0, "ids": []}


@mcp.tool()
def mem_stats() -> dict:
    """Return aggregate memory counts."""
    return {"total": 0, "active": 0, "superseded": 0, "rejected": 0}


@mcp.tool()
def mem_why(id: str) -> dict:
    """Explain why a memory entry exists."""
    return {"id": id, "content": "stub — not implemented yet", "provenance": []}


@mcp.tool()
def mem_feedback(id: str, verdict: str) -> dict:
    """Record whether a memory was useful or wrong."""
    return {"ok": True, "id": id, "verdict": verdict}


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
