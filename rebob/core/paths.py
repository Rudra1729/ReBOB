"""Project-local path resolution for ReBOB data (.rebob/, .env)."""

import os
import subprocess
from pathlib import Path


def project_root(start: Path | None = None) -> Path:
    """Best-effort git repo root, else *start* or cwd."""
    cwd = (start or Path.cwd()).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        return Path(out.stdout.strip()).resolve()
    except Exception:
        return cwd


def rebob_home(root: Path | None = None) -> Path:
    """Return the project-local .rebob directory.

    Override with REBOB_HOME for tests or custom layouts.
    """
    override = os.environ.get("REBOB_HOME")
    if override:
        return Path(override).expanduser().resolve()
    base = root or project_root()
    return (base / ".rebob").resolve()
