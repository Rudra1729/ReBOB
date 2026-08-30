"""rebob serve — run the ReBOB MCP server as a persistent process."""

from __future__ import annotations


def run_serve(*, transport: str = "stdio", port: int = 8000, host: str = "0.0.0.0") -> None:
    from rebob.core.store import init_db

    init_db()

    if transport == "stdio":
        from rebob.server import mcp

        mcp.run(transport="stdio")
    else:
        import uvicorn

        from starlette.middleware import Middleware

        from rebob.server import AuthMiddleware, mcp

        http_transport = "streamable-http" if transport == "http" else transport
        endpoint = "sse" if transport == "sse" else "mcp"
        print(
            f"ReBOB: starting {transport} server on http://{host}:{port}/{endpoint}",
            flush=True,
        )
        app = mcp.http_app(
            path=f"/{endpoint}",
            transport=http_transport,
            middleware=[Middleware(AuthMiddleware)],
        )
        uvicorn.run(app, host=host, port=port)
