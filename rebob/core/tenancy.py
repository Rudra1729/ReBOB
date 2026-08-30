"""Tenancy helpers — repo URL normalization and visibility scoping."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_SSH_RE = re.compile(r"^git@([^:]+):(.+?)(?:\.git)?$")


def normalize_repo_url(url: str) -> str:
    """Canonicalize git remote URLs to a single project key."""
    if not url:
        return ""
    url = url.strip()
    ssh = _SSH_RE.match(url)
    if ssh:
        host, path = ssh.group(1), ssh.group(2)
        return f"{host.lower()}/{path.rstrip('/').lower()}"

    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        path = path.lower()
        return f"{parsed.netloc.lower()}/{path}"

    return url.lower().rstrip("/")


def visibility_clause(alias: str = "m") -> str:
    """SQL fragment enforcing project/personal/org visibility for the current author/repo."""
    a = alias
    # COALESCE so NULL repo_url in the row matches an empty current repo
    # (common for inserts that omit repo_url).
    return f"""
      (
        {a}.visibility = 'org'
        OR ({a}.visibility = 'project'
            AND COALESCE({a}.repo_url, '') = %(repo_url)s)
        OR ({a}.visibility = 'personal' AND {a}.author_id = %(author_id)s)
        OR ({a}.visibility IS NULL)
      )
    """
