"""Client-side credential storage for hosted ReBOB."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _credentials_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "rebob" / "credentials.json"
    return Path.home() / ".config" / "rebob" / "credentials.json"


def load_credentials() -> dict:
    try:
        import keyring

        token = keyring.get_password("rebob", "api_token")
        server_url = keyring.get_password("rebob", "server_url")
        if token:
            return {"token": token, "server_url": server_url or ""}
    except Exception:
        pass

    path = _credentials_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_credentials(*, token: str, server_url: str = "") -> None:
    try:
        import keyring

        keyring.set_password("rebob", "api_token", token)
        if server_url:
            keyring.set_password("rebob", "server_url", server_url)
        return
    except Exception:
        pass

    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"token": token, "server_url": server_url}, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)


def get_server_url() -> str:
    return os.environ.get("REBOB_SERVER_URL") or load_credentials().get("server_url", "")


def get_token() -> str:
    return os.environ.get("REBOB_API_TOKEN") or load_credentials().get("token", "")
