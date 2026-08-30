"""Tenancy normalization and cross-tenant isolation tests."""

import os
import uuid

import pytest

from rebob.core.tenancy import normalize_repo_url


class TestNormalizeRepoUrl:
    def test_https_with_git_suffix(self):
        assert normalize_repo_url("https://github.com/IBM/ReBOB.git") == "github.com/ibm/rebob"

    def test_https_without_git_suffix(self):
        assert normalize_repo_url("https://github.com/IBM/ReBOB") == "github.com/ibm/rebob"

    def test_ssh_format(self):
        assert normalize_repo_url("git@github.com:IBM/ReBOB.git") == "github.com/ibm/rebob"


def _postgres_available() -> bool:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://rebob:rebob@localhost:5433/rebob",
    )
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _postgres_available(), reason="Postgres not available")
class TestCrossTenantIsolation:
    def test_org_b_cannot_read_org_a_memory(self, monkeypatch):
        from rebob.core.auth import create_organization, issue_token
        from rebob.core.context import RequestContext, set_context
        from rebob.core.storage import get_backend, reset_backend

        url = os.environ.get(
            "DATABASE_URL",
            "postgresql://rebob:rebob@localhost:5433/rebob",
        )
        monkeypatch.setenv("REBOB_BACKEND", "postgres")
        monkeypatch.setenv("DATABASE_URL", url)
        reset_backend()

        backend = get_backend()
        backend.init_db()

        org_a = create_organization("tenant-a")
        org_b = create_organization("tenant-b")
        token_a = issue_token(org_a, author_id="alice")
        issue_token(org_b, author_id="bob")

        # Insert memory as org A
        backend.set_org_id(org_a)
        set_context(RequestContext(org_id=org_a, author_id="alice", repo_url="github.com/acme/app"))
        mem_id = backend.insert_memory({
            "claim_key": "secret",
            "memory_type": "gotcha",
            "content": "Tenant A secret memory.",
            "rationale": "test",
            "scope": "repo",
            "status": "active",
            "repo_url": "github.com/acme/app",
            "author_id": "alice",
            "visibility": "project",
        })

        # Read as org B — must not see org A memory
        backend.set_org_id(org_b)
        set_context(RequestContext(org_id=org_b, author_id="bob", repo_url="github.com/acme/app"))
        row = backend.get_memory(mem_id)
        assert row is None

        active = backend.list_active_memories()
        assert all(m["id"] != mem_id for m in active)

        # Sanity: org A token validates
        from rebob.core.auth import validate_token

        ctx = validate_token(token_a)
        assert ctx is not None
        assert ctx.org_id == org_a
