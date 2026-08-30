"""
rebob/core/retrieve.py — Full retrieval pipeline for ReBOB.

Entry point: retrieve(query, *, k, budget_tokens, session_id, file_hints)

Pipeline stages:
  1. Dense  — cosine over vectors.npy (watsonx embed, cached)
  2. Sparse — FTS5 BM25 via store.fts_search
  3. Struct — memories whose file_paths overlap with file_hints / query tokens
  4. Fuse   — Reciprocal Rank Fusion
  5. Rerank — watsonx Text Rerank on top 20 (degrades gracefully)
  6. Filter — active, anchor_valid, not already injected this session
  7. Score  — rerank_norm·0.5 + usefulness·0.2 + recency·0.15 + confidence·0.15
  8. Pack   — markdown brief ≤ budget_tokens, cited IDs
  9. Log    — increment_retrieval + mark_injected

Session dedup: <rebob_home>/injected/<session_id>.json tracks IDs already sent.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from rebob import paths


# ---------------------------------------------------------------------------
# Session dedup helpers
# ---------------------------------------------------------------------------

def _injected_path(session_id: str) -> Optional[Path]:
    if not session_id:
        return None
    injected_dir = paths.injected_dir()
    injected_dir.mkdir(parents=True, exist_ok=True)
    return injected_dir / f"{session_id}.json"


def load_injected(session_id: str) -> set:
    """Return the set of memory IDs already injected into this session."""
    if not session_id:
        return set()
    p = _injected_path(session_id)
    if p is None or not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("injected_ids", []))
    except Exception:
        return set()


def mark_injected(session_id: str, ids: list) -> None:
    """Append newly-cited IDs to the session's injected log."""
    if not session_id or not ids:
        return
    existing = load_injected(session_id)
    merged = sorted(existing | set(ids))
    p = _injected_path(session_id)
    if p is None:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(
        json.dumps({"injected_ids": merged, "updated_at": now}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Dense search
# ---------------------------------------------------------------------------

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _dense_search(query: str, memories: list, limit: int = 30) -> list:
    """Return mem IDs sorted by cosine similarity (best first), up to limit."""
    if not memories:
        return []

    from rebob.core import store, watsonx

    try:
        qvec = np.array(watsonx.embed(query), dtype=np.float32)
    except Exception:
        return []

    memory_ids = [m["id"] for m in memories]
    return store.vector_search(qvec, limit=limit, memory_ids=memory_ids)


# ---------------------------------------------------------------------------
# Structural search
# ---------------------------------------------------------------------------

_FILE_TOKEN_RE = re.compile(r"\b\w+\.(?:py|ts|js|tsx|jsx|md|yaml|yml|json|toml|sh|sql)\b")


def _structural_search(query: str, memories: list, file_hints: Optional[list], limit: int = 30) -> list:
    """Boost memories whose file_paths overlap with file_hints or query file tokens."""
    hints = set(file_hints or [])
    # Extract filename tokens from the query text
    hints.update(_FILE_TOKEN_RE.findall(query))

    if not hints:
        return []

    scored = []
    for mem in memories:
        raw = mem.get("file_paths") or "[]"
        try:
            paths = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            paths = []
        overlap = sum(
            1 for p in paths
            if any(h in p for h in hints)
        )
        if overlap > 0:
            scored.append((mem["id"], overlap))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [mid for mid, _ in scored[:limit]]


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def _rrf_fuse(ranked_lists: list, k: int = 60) -> list:
    """Standard Reciprocal Rank Fusion. Returns IDs sorted by fused score."""
    scores: dict = {}
    for lst in ranked_lists:
        for rank, mem_id in enumerate(lst):
            scores[mem_id] = scores.get(mem_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.__getitem__, reverse=True)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _recency_score(created_at: Optional[str]) -> float:
    """Decay: 1 / (1 + days/30). Returns 0.5 if timestamp missing."""
    if not created_at:
        return 0.5
    try:
        ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = max(0.0, (now - ts).total_seconds() / 86400)
        return 1.0 / (1.0 + days / 30.0)
    except Exception:
        return 0.5


def _final_score(rank: int, total: int, mem: dict) -> float:
    """
    score = rerank_norm·0.5 + usefulness·0.2 + recency·0.15 + confidence·0.15
    rank is 0-based position in the reranked list (lower = better).
    """
    rerank_norm = 1.0 - (rank / max(total - 1, 1))
    usefulness = float(mem.get("usefulness") or 0.5)
    recency = _recency_score(mem.get("created_at"))
    confidence = float(mem.get("confidence") or 0.5)
    return rerank_norm * 0.5 + usefulness * 0.2 + recency * 0.15 + confidence * 0.15


# ---------------------------------------------------------------------------
# Brief packing
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4  # good enough for budget estimation

_BRIEF_HEADER = "## ReBOB Memory Brief\n\n"
_BRIEF_PREAMBLE = (
    "Confirmed findings from prior work on this exact codebase, not guesses. "
    "Apply them directly — do not re-read the referenced files or re-derive these "
    "facts to double-check them. Only deviate if you hit a direct, concrete "
    "contradiction while editing.\n\n"
)


def _pack_brief(memories: list, budget_tokens: int) -> tuple:
    """
    Format memories as markdown brief lines, stopping at budget_tokens.

    Returns (brief_str, list_of_ids_included).
    """
    if not memories:
        return "", []

    lines = []
    ids = []
    used_chars = len(_BRIEF_HEADER) + len(_BRIEF_PREAMBLE)

    for mem in memories:
        mem_id = mem["id"]
        content = mem.get("content", "").strip()
        mem_type = mem.get("memory_type", "")
        line = f"- [{mem_id}] {content}"
        if mem_type:
            line += f" _({mem_type})_"
        line += "\n"

        chunk = used_chars + len(line)
        if chunk / _CHARS_PER_TOKEN > budget_tokens:
            break

        lines.append(line)
        ids.append(mem_id)
        used_chars = chunk

    if not lines:
        return "", []

    brief = _BRIEF_HEADER + _BRIEF_PREAMBLE + "".join(lines)
    return brief, ids


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    *,
    k: int = 8,
    budget_tokens: int = 600,
    session_id: str = "",
    file_hints: Optional[list] = None,
) -> str:
    """
    Run the full retrieval pipeline and return a markdown memory brief.

    On any unhandled error returns "" so the hook always exits 0.
    """
    try:
        return _retrieve(query, k=k, budget_tokens=budget_tokens,
                         session_id=session_id, file_hints=file_hints)
    except Exception:
        return ""


def _retrieve(
    query: str,
    *,
    k: int,
    budget_tokens: int,
    session_id: str,
    file_hints: Optional[list],
) -> str:
    from rebob.core import store, watsonx

    store.init_db()

    # 1. Candidate pool
    all_memories = store.list_active_memories()
    if not all_memories:
        return ""

    mem_by_id = {m["id"]: m for m in all_memories}

    # 2a. Dense search
    dense_ids = _dense_search(query, all_memories, limit=30)

    # 2b. Sparse search
    sparse_rows = store.fts_search(query, limit=30)
    sparse_ids = [r["id"] for r in sparse_rows]

    # 2c. Structural search
    struct_ids = _structural_search(query, all_memories, file_hints, limit=30)

    # 3. RRF fusion
    ranked_lists = [lst for lst in [dense_ids, sparse_ids, struct_ids] if lst]
    if not ranked_lists:
        # Fall back to all active memories in insertion order
        ranked_lists = [[m["id"] for m in all_memories]]

    fused = _rrf_fuse(ranked_lists)[:20]  # top 20 for rerank

    # 4. Rerank (degrades silently)
    if fused:
        docs = [
            (mem_by_id[mid].get("content", "") + " " + (mem_by_id[mid].get("rationale") or "")).strip()
            for mid in fused
            if mid in mem_by_id
        ]
        valid_fused = [mid for mid in fused if mid in mem_by_id]
        try:
            reranked_indices = watsonx.rerank(query, docs, top_n=len(docs))
            reranked = [valid_fused[i] for i in reranked_indices if i < len(valid_fused)]
        except Exception:
            reranked = valid_fused
    else:
        reranked = []

    # 5. Filter: active, anchor_valid already enforced by list_active_memories;
    #    additionally drop IDs already injected this session
    already_injected = load_injected(session_id)
    filtered = [mid for mid in reranked if mid not in already_injected]

    if not filtered:
        return ""

    # 6. Score + take top k
    scored = []
    total = len(filtered)
    for rank, mid in enumerate(filtered):
        if mid not in mem_by_id:
            continue
        mem = mem_by_id[mid]
        s = _final_score(rank, total, mem)
        scored.append((mid, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_ids = [mid for mid, _ in scored[:k]]
    top_mems = [mem_by_id[mid] for mid in top_ids]

    # 7. Pack brief
    brief, cited_ids = _pack_brief(top_mems, budget_tokens)

    if not brief:
        return ""

    # 8. Log
    store.increment_retrieval(cited_ids)
    mark_injected(session_id, cited_ids)

    return brief
