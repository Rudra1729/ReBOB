"""
rebob/server.py — ReBOB MCP server.

Transports:
  - stdio (default): Bob spawns a process per call. Zero setup.
  - sse / http:      persistent server, no per-call cold start. Opt-in via
                      `rebob init --transport sse` or `rebob serve --transport sse`.

Run via:  python -m rebob.server [--transport stdio|sse] [--port 8000]
      or: rebob serve [--transport stdio|sse] [--port 8000]
"""

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
    """Distil a session into memory records."""
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
    import argparse

    parser = argparse.ArgumentParser(description="ReBOB MCP server")
    parser.add_argument("--transport", choices=["stdio", "sse", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    init_db()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        endpoint = "sse" if args.transport == "sse" else "mcp"
        print(
            f"ReBOB: starting {args.transport} server on http://127.0.0.1:{args.port}/{endpoint}",
            flush=True,
        )
        mcp.run(transport=args.transport, port=args.port)
