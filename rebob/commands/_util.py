"""Shared helpers for rebob init / doctor."""

from __future__ import annotations

import json
import sys
from importlib import resources
from pathlib import Path


def load_template(name: str) -> str:
    return resources.files("rebob").joinpath("templates", name).read_text(encoding="utf-8")


def quote_cmd(path: Path) -> str:
    """Quote a path for Bob hook command strings (Windows-safe)."""
    return f'"{path}"'


def hook_command(python: Path, hook_script: Path, hook_type: str) -> str:
    return f"{quote_cmd(python)} {quote_cmd(hook_script)} {hook_type}"


def render_template(name: str, **replacements: str) -> str:
    text = load_template(name)
    for key, value in replacements.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str, *, overwrite: bool = False) -> bool:
    """Write *content* to *path*. Returns True if written, False if skipped."""
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    answer = input(f"{path} already exists. Overwrite? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def ensure_gitignore_entries(root: Path, entries: list[str]) -> list[str]:
    """Append missing entries to .gitignore. Returns lines that were added."""
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    added = []
    for entry in entries:
        if entry not in existing:
            added.append(entry)
    if added:
        gitignore.parent.mkdir(parents=True, exist_ok=True)
        suffix = "" if (not existing or existing[-1] == "") else "\n"
        with gitignore.open("a", encoding="utf-8") as f:
            f.write(suffix + "\n".join(added) + "\n")
    return added
