"""Request-scoped context for hosted mode."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class RequestContext:
    org_id: str
    author_id: str = ""
    repo_url: str = ""
    branch: str = ""


_current_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "rebob_request_context", default=None
)


def get_context() -> Optional[RequestContext]:
    return _current_context.get()


def set_context(ctx: RequestContext) -> None:
    _current_context.set(ctx)


def clear_context() -> None:
    _current_context.set(None)
