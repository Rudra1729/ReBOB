"""HTTP client for hosted ReBOB — fail-open on every error."""

from __future__ import annotations

import json
import os
import time

from rebob.credentials import get_server_url, get_token


class _CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: float = 30.0) -> None:
        self._failures = 0
        self._threshold = threshold
        self._cooldown = cooldown
        self._open_until = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self._open_until

    def record_success(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_until = time.monotonic() + self._cooldown


_breaker = _CircuitBreaker()


def _timeout_seconds() -> float:
    hook = os.environ.get("REBOB_HOOK_TYPE", "prompt")
    if hook == "prompt":
        return float(os.environ.get("REBOB_HTTP_TIMEOUT", "7"))
    return float(os.environ.get("REBOB_HTTP_TIMEOUT", "4"))


def _headers() -> dict:
    token = get_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method: str, path: str, body: dict | None = None) -> dict | None:
    if not _breaker.allow():
        return None
    base = get_server_url().rstrip("/")
    if not base:
        return None
    try:
        import httpx

        url = f"{base}{path}"
        timeout = _timeout_seconds()
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                resp = client.get(url, headers=_headers())
            else:
                resp = client.post(url, headers=_headers(), json=body or {})
            resp.raise_for_status()
            _breaker.record_success()
            if resp.content:
                return resp.json()
            return {}
    except Exception as exc:
        _breaker.record_failure()
        if os.environ.get("REBOB_DEBUG") == "1":
            try:
                from rebob import paths

                paths.rebob_home().mkdir(parents=True, exist_ok=True)
                with paths.hook_log_path().open("a", encoding="utf-8") as f:
                    f.write(f"hosted {method} {path} failed: {exc}\n")
            except Exception:
                pass
        return None


def record(event: dict) -> dict | None:
    """POST a redacted event — never raises. Returns response or None."""
    return _request("POST", "/events", {"event": event})


def search(query: str, session_id: str = "") -> str:
    """POST a search request — returns brief or empty string."""
    result = _request(
        "POST",
        "/search",
        {"query": query, "session_id": session_id},
    )
    if not result:
        return ""
    return result.get("brief", "") or ""
