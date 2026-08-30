"""rebob register-watsonx — register BYO watsonx credentials with hosted server."""

from __future__ import annotations

import os

from rebob.client import _request
from rebob.credentials import get_server_url, get_token


def run_register_watsonx(
    *,
    api_key: str = "",
    project_id: str = "",
    url: str = "",
) -> None:
    from rebob.config import load_env

    load_env()
    api_key = api_key or os.environ.get("IBM_CLOUD_API_KEY", "")
    project_id = project_id or os.environ.get("WATSONX_PROJECT_ID", "")
    url = url or os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

    if not api_key or not project_id:
        print("ERROR: provide --api-key and --project-id (or set in .env)")
        raise SystemExit(1)
    if not get_token():
        print("ERROR: run rebob login --token <key> first")
        raise SystemExit(1)
    if not get_server_url():
        print("ERROR: set REBOB_SERVER_URL or pass --server to rebob init")
        raise SystemExit(1)

    result = _request(
        "POST",
        "/register-watsonx",
        {"api_key": api_key, "project_id": project_id, "url": url},
    )
    if not result or not result.get("ok"):
        print("ERROR: registration failed")
        raise SystemExit(1)
    print("watsonx credentials registered with server.")
