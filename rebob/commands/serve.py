"""rebob serve — run the ReBOB MCP server as a persistent process."""

from __future__ import annotations


def run_serve(*, transport: str = "stdio", port: int = 8000) -> None:
    from rebob.core.store import init_db

    init_db()

    from rebob.server import mcp

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        endpoint = "sse" if transport == "sse" else "mcp"
        print(f"ReBOB: starting {transport} server on http://127.0.0.1:{port}/{endpoint}", flush=True)
        mcp.run(transport=transport, port=port)
