"""
rebob/server.py — ReBOB MCP server.

Transports:
  - stdio (default): Bob spawns a process per call. Zero setup.
  - http:            streamable-http at /mcp for hosted deployment.

Run via:  python -m rebob.server [--transport stdio|http] [--port 8000]
      or: rebob serve [--transport stdio|http] [--port 8000]
"""

from __future__ import annotations

import json
import os

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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


# ── HTTP routes (hosted) ─────────────────────────────────────────────────────

def _is_public_path(path: str) -> bool:
    return path.rstrip("/") in ("/healthz", "/readyz")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        from rebob.core.auth import validate_token
        from rebob.core.context import clear_context, set_context

        if _is_public_path(request.url.path):
            return await call_next(request)

        if os.environ.get("REBOB_BACKEND", "sqlite") != "postgres":
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        ctx = validate_token(auth.split(" ", 1)[1].strip())
        if ctx is None:
            return JSONResponse({"error": "invalid token"}, status_code=401)

        repo = request.headers.get("x-rebob-repo-url", "")
        branch = request.headers.get("x-rebob-branch", "")
        if repo:
            ctx.repo_url = repo
        if branch:
            ctx.branch = branch
        set_context(ctx)
        try:
            return await call_next(request)
        finally:
            clear_context()


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(_request: Request) -> JSONResponse:
    try:
        from rebob.core.storage import get_backend

        backend = get_backend()
        if hasattr(backend, "_get_pool"):
            with backend._get_pool().connection() as conn:
                conn.execute("SELECT 1")
        return JSONResponse({"status": "ready"})
    except Exception as exc:
        return JSONResponse({"status": "not ready", "error": str(exc)}, status_code=503)


@mcp.custom_route("/events", methods=["POST"])
async def ingest_event(request: Request) -> JSONResponse:
    from rebob.core.events import sanitize_event
    from rebob.core.storage import get_backend

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    event = body.get("event") if isinstance(body, dict) else None
    if not isinstance(event, dict):
        return JSONResponse({"error": "missing event"}, status_code=400)

    clean = sanitize_event(event)
    session_id = clean.get("session_id", "unknown")
    backend = get_backend()
    if hasattr(backend, "append_session_event"):
        backend.append_session_event(session_id, clean)
    else:
        contract.record(clean)
    return JSONResponse({"ok": True, "session_id": session_id})


@mcp.custom_route("/search", methods=["POST"])
async def http_search(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    query = body.get("query", "")
    session_id = body.get("session_id", "")
    brief = contract.search(query, session_id=session_id)
    return JSONResponse({"brief": brief})


@mcp.custom_route("/register-watsonx", methods=["POST"])
async def http_register_watsonx(request: Request) -> JSONResponse:
    from rebob.core.auth import register_watsonx_credentials
    from rebob.core.context import get_context

    ctx = get_context()
    if ctx is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    api_key = body.get("api_key", "")
    project_id = body.get("project_id", "")
    url = body.get("url", "https://us-south.ml.cloud.ibm.com")
    if not api_key or not project_id:
        return JSONResponse({"error": "api_key and project_id required"}, status_code=400)

    register_watsonx_credentials(
        ctx.org_id, api_key=api_key, project_id=project_id, url=url
    )
    return JSONResponse({"ok": True})


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="ReBOB MCP server")
    parser.add_argument("--transport", choices=["stdio", "sse", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    init_db()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        transport = "streamable-http" if args.transport == "http" else args.transport
        endpoint = "sse" if args.transport == "sse" else "mcp"
        print(
            f"ReBOB: starting {args.transport} server on http://{args.host}:{args.port}/{endpoint}",
            flush=True,
        )
        app = mcp.http_app(
            path=f"/{endpoint}",
            transport=transport,
            middleware=[Middleware(AuthMiddleware)],
        )
        uvicorn.run(app, host=args.host, port=args.port)
