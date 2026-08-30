"""rebob admin — server-side administration (token issuance)."""

from __future__ import annotations

import os

from rebob.core.auth import check_admin_token, create_organization, issue_token


def run_admin_issue_token(
    *,
    org: str,
    author: str = "",
    admin_token: str = "",
) -> None:
    token = admin_token or os.environ.get("REBOB_ADMIN_TOKEN", "")
    if not check_admin_token(token):
        print("ERROR: invalid admin token (set REBOB_ADMIN_TOKEN)")
        raise SystemExit(1)

    os.environ.setdefault("REBOB_BACKEND", "postgres")
    from rebob.core.storage import get_backend

    get_backend().init_db()

    org_id = create_organization(org)
    api_token = issue_token(org_id, author_id=author)
    print(f"org_id: {org_id}")
    print(f"token:  {api_token}")
    print("(Save the token — it cannot be retrieved again.)")
