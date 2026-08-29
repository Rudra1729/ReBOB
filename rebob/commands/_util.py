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
    """Render a template that will be parsed as JSON.

    Values are JSON-escaped before substitution -- Windows paths contain
    backslashes, which are JSON escape characters, so a raw string.replace()
    of e.g. "C:\\Users\\..." into a template's quoted string produces
    invalid JSON (json.decoder.JSONDecodeError: Invalid \\escape).
    """
    text = load_template(name)
    for key, value in replacements.items():
        escaped = json.dumps(value)[1:-1]
        text = text.replace(f"{{{{{key}}}}}", escaped)
    return text


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


_HOOK_EVENT_TIMEOUTS = {
    "UserPromptSubmit": ("prompt", 8000),
    "PostToolUse": ("tool", 5000),
    "Stop": ("stop", 5000),
}


def merge_mcp_server(mcp: dict, python: Path, server_script: Path, project_root: Path) -> dict:
    """Set/replace only the "rebob" entry, preserving any other configured MCP servers."""
    servers = mcp.setdefault("mcpServers", {})
    servers["rebob"] = {
        "command": str(python),
        "args": [str(server_script)],
        "cwd": str(project_root),
    }
    return mcp


def merge_rebob_hooks(settings: dict, python: Path, hook_script: Path) -> dict:
    """Add/replace ReBOB's own hook entries, preserving any other hooks already configured.

    Re-running this (e.g. `rebob init` a second time) must not duplicate ReBOB's own
    entries -- identify them by hook_script's path appearing in the command string,
    drop any prior match, then append the current one.
    """
    hooks = settings.setdefault("hooks", {})
    hook_script_str = str(hook_script)
    for event_type, (hook_type, timeout) in _HOOK_EVENT_TIMEOUTS.items():
        groups = hooks.setdefault(event_type, [])
        groups[:] = [
            g for g in groups
            if not any(hook_script_str in h.get("command", "") for h in g.get("hooks", []))
        ]
        groups.append({
            "hooks": [{
                "type": "command",
                "command": hook_command(python, hook_script, hook_type),
                "timeout": timeout,
            }]
        })
    return settings


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
