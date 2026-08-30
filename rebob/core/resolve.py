"""
rebob/core/resolve.py — Dedup, embed, and store extracted memory records.

resolve(records) -> {"added": int, "updated": int, "rejected": int, "ids": list[str]}
"""

import os
import re
import secrets
from datetime import datetime, timezone

from rebob import config

config.load_env()


# ---------------------------------------------------------------------------
# Claim key normalisation
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_claim_key(content: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace, take first 120 chars."""
    s = content.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s[:120]


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

def resolve(records: list[dict]) -> dict:
    """Dedup, embed, and store each validated record.

    Returns {"added": int, "updated": int, "rejected": int, "ids": list[str]}.
    """
    from rebob.core import store, watsonx

    store.init_db()

    added = 0
    updated = 0
    rejected = 0
    ids: list[str] = []

    for rec in records:
        content = rec.get("content", "").strip()
        if not content:
            rejected += 1
            continue

        claim_key = normalize_claim_key(content)
        existing_list = store.get_by_claim_key(claim_key, status="active")

        if existing_list:
            existing = existing_list[0]
            existing_content_norm = normalize_claim_key(existing["content"])

            if existing_content_norm == normalize_claim_key(content):
                # Identical claim — NOOP
                continue

            if existing.get("pinned"):
                # Contradicts a pinned record — REJECT
                rejected += 1
                continue

            # Different content, not pinned — SUPERSEDE
            new_version = (existing.get("version") or 1) + 1
            store.update_memory(existing["id"], {"status": "superseded"})

            embedding = watsonx.embed(content)
            embedding_id = store.store_embedding(embedding)

            new_id = "mem_" + secrets.token_hex(4)
            _insert_row(
                store,
                new_id,
                claim_key,
                rec,
                content,
                embedding_id,
                version=new_version,
                supersedes=existing["id"],
            )
            ids.append(new_id)
            updated += 1

        else:
            # No existing record — ADD
            embedding = watsonx.embed(content)
            embedding_id = store.store_embedding(embedding)

            new_id = "mem_" + secrets.token_hex(4)
            _insert_row(store, new_id, claim_key, rec, content, embedding_id)
            ids.append(new_id)
            added += 1

    return {"added": added, "updated": updated, "rejected": rejected, "ids": ids}


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_row(
    store_mod,
    new_id: str,
    claim_key: str,
    rec: dict,
    content: str,
    embedding_id: str,
    version: int = 1,
    supersedes: str | None = None,
) -> None:
    import os

    from rebob.core.context import get_context
    from rebob.core.tenancy import normalize_repo_url

    ctx = get_context()
    repo_url = normalize_repo_url(
        rec.get("repo_url")
        or os.environ.get("REBOB_REPO_URL", "")
        or (ctx.repo_url if ctx else "")
    )
    branch = rec.get("branch") or os.environ.get("REBOB_BRANCH", "") or (ctx.branch if ctx else "")
    author_id = (
        rec.get("author_id")
        or os.environ.get("REBOB_AUTHOR_ID", "")
        or (ctx.author_id if ctx else "")
    )
    row = {
        "id": new_id,
        "claim_key": claim_key,
        "version": version,
        "supersedes": supersedes,
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
        "memory_type": rec.get("memory_type", "gotcha"),
        "content": content,
        "rationale": rec.get("rationale", ""),
        "counter_example": rec.get("counter_example"),
        "scope": rec.get("scope", "repo"),
        "visibility": rec.get("visibility", "project"),
        "repo_url": repo_url,
        "branch": branch,
        "author_id": author_id,
        "source_kind": rec.get("source_kind", "hook_session"),
        "task_id": rec.get("task_id", ""),
        "extractor_model": os.getenv("WATSONX_LLM_MODEL", "ibm/granite-4-h-small"),
        "confidence": rec.get("confidence", 0.5),
        "evidence_count": 1,
        "volatility": rec.get("volatility", "durable"),
        "verification": "asserted",
        "anchor_valid": True,
        "usefulness": 0.5,
        "sensitivity": "internal",
        "pinned": False,
        "embedding_id": embedding_id,
        "file_paths": rec.get("file_paths", []),
        "keywords": rec.get("keywords", []),
        "redaction_applied": rec.get("redaction_applied", []),
    }
    if ctx and ctx.org_id:
        row["org_id"] = ctx.org_id
    else:
        try:
            from rebob.core.storage import get_backend

            org = getattr(get_backend(), "_org_id", None)
            if org:
                row["org_id"] = org
        except Exception:
            pass
    store_mod.insert_memory(row)
