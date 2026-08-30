"""Bearer token auth for hosted ReBOB."""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from typing import Optional

from rebob.core.context import RequestContext


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    return "rebob_" + secrets.token_urlsafe(32)


def _require_postgres():
    from rebob.core.storage import get_backend

    backend = get_backend()
    if backend.__class__.__name__ != "PostgresBackend":
        raise RuntimeError("Auth requires REBOB_BACKEND=postgres")
    return backend


def issue_token(org_id: str, author_id: str = "") -> str:
    """Create a new API token; returns the plaintext (shown once)."""
    backend = _require_postgres()
    token = generate_token()
    token_id = str(uuid.uuid4())
    with backend._connection() as conn:
        conn.execute(
            """
            INSERT INTO api_tokens (id, org_id, author_id, token_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (token_id, org_id, author_id, hash_token(token)),
        )
    return token


def validate_token(token: str) -> Optional[RequestContext]:
    """Look up bearer token; return RequestContext or None."""
    if not token or not token.startswith("rebob_"):
        return None
    backend = _require_postgres()
    th = hash_token(token)
    pool = backend._get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT t.org_id::text, t.author_id
            FROM api_tokens t
            WHERE t.token_hash = %s AND t.revoked_at IS NULL
            """,
            (th,),
        ).fetchone()
    if not row:
        return None
    backend.set_org_id(row["org_id"])
    return RequestContext(org_id=row["org_id"], author_id=row["author_id"] or "")


def create_organization(name: str) -> str:
    backend = _require_postgres()
    org_id = str(uuid.uuid4())
    with backend._connection() as conn:
        conn.execute(
            "INSERT INTO organizations (id, name) VALUES (%s, %s)",
            (org_id, name),
        )
    return org_id


def register_watsonx_credentials(
    org_id: str,
    *,
    api_key: str,
    project_id: str,
    url: str = "https://us-south.ml.cloud.ibm.com",
) -> None:
    from rebob.core.crypto import encrypt_secret

    backend = _require_postgres()
    enc = encrypt_secret(api_key)
    with backend._connection() as conn:
        conn.execute(
            """
            UPDATE organizations
            SET watsonx_api_key_enc = %s,
                watsonx_project_id = %s,
                watsonx_url = %s
            WHERE id = %s
            """,
            (enc, project_id, url, org_id),
        )


def get_org_watsonx_config(org_id: str) -> Optional[dict]:
    backend = _require_postgres()
    with backend._connection() as conn:
        row = conn.execute(
            """
            SELECT watsonx_api_key_enc, watsonx_project_id, watsonx_url
            FROM organizations WHERE id = %s
            """,
            (org_id,),
        ).fetchone()
    if not row or not row["watsonx_api_key_enc"]:
        return None
    from rebob.core.crypto import decrypt_secret

    return {
        "IBM_CLOUD_API_KEY": decrypt_secret(row["watsonx_api_key_enc"]),
        "WATSONX_PROJECT_ID": row["watsonx_project_id"],
        "WATSONX_URL": row["watsonx_url"] or "https://us-south.ml.cloud.ibm.com",
    }


def check_admin_token(provided: str) -> bool:
    expected = os.environ.get("REBOB_ADMIN_TOKEN", "")
    if not expected:
        return False
    return secrets.compare_digest(provided, expected)
