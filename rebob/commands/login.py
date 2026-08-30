"""rebob login — store hosted API token in OS keychain."""

from __future__ import annotations

from rebob.credentials import save_credentials


def run_login(*, token: str, server_url: str = "") -> None:
    if not token:
        print("ERROR: --token is required")
        raise SystemExit(1)
    save_credentials(token=token, server_url=server_url)
    print("Credentials saved.")
    if server_url:
        print(f"  server: {server_url}")
