"""Shared helpers for rebob init / doctor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib import resources
from pathlib import Path


def load_template(name: str) -> str:
    return resources.files("rebob").joinpath("templates", name).read_text(encoding="utf-8")


def resolve_python() -> Path:
    """Prefer the active venv Python, else the current interpreter."""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        for name in ("python3.12", "python3", "python"):
            candidate = Path(venv) / "bin" / name
            if candidate.exists():
                # Keep the venv shim path; resolving symlinks can point at system Python.
                return candidate
    return Path(sys.executable)


def quote_cmd(path: Path) -> str:
    """Quote a path for Bob hook command strings (Windows-safe)."""
    return f'"{path}"'


def hook_command(python: Path, hook_script: Path, hook_type: str) -> str:
    return f"{quote_cmd(python)} {quote_cmd(hook_script)} {hook_type}"


def build_settings(python: Path, hook_script: Path) -> dict:
    """Build Bob settings.json hook config with JSON-safe command strings."""

    def hook_entry(hook_type: str, timeout: int) -> dict:
        return {
            "hooks": [
                {
                    "type": "command",
                    "command": hook_command(python, hook_script, hook_type),
                    "timeout": timeout,
                }
            ]
        }

    return {
        "hooks": {
            "UserPromptSubmit": [hook_entry("prompt", 8000)],
            "PostToolUse": [hook_entry("tool", 5000)],
            "Stop": [hook_entry("stop", 5000)],
        }
    }


def build_mcp(python: Path, project_root: Path) -> dict:
    """Build Bob mcp.json using module launch (portable across installs)."""
    return {
        "mcpServers": {
            "rebob": {
                "command": str(python),
                "args": ["-m", "rebob.server"],
                "cwd": str(project_root),
            }
        }
    }


_HOOK_CMD_RE = re.compile(r'"([^"]*)"')


def parse_hook_command(command: str) -> tuple[Path, Path, str]:
    """Parse a Bob hook command string into (python, script, hook_type)."""
    parts = _HOOK_CMD_RE.findall(command)
    if len(parts) < 2:
        raise ValueError(f"invalid hook command: {command!r}")
    hook_type = command.strip().split()[-1]
    return Path(parts[0]), Path(parts[1]), hook_type


def load_json(path: Path) -> tuple[dict | None, str | None]:
    """Load JSON from *path*. Returns (data, error)."""
    if not path.is_file():
        return None, "file missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def validate_settings(settings_path: Path) -> list[str]:
    """Return a list of validation errors for settings.json."""
    data, err = load_json(settings_path)
    if err:
        return [f"settings.json: {err}"]
    if not isinstance(data, dict):
        return ["settings.json: root must be an object"]

    errors: list[str] = []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return ["settings.json: missing hooks object"]

    for hook_name, entries in hooks.items():
        if not isinstance(entries, list):
            errors.append(f"settings.json: hooks.{hook_name} must be a list")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks", []):
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    continue
                command = hook.get("command", "")
                try:
                    python, script, _ = parse_hook_command(command)
                except ValueError as exc:
                    errors.append(f"settings.json: {exc}")
                    continue
                if not python.is_file():
                    errors.append(f"settings.json: python not found: {python}")
                if not script.is_file():
                    errors.append(f"settings.json: hook script not found: {script}")
    return errors


def validate_mcp(mcp_path: Path) -> list[str]:
    """Return a list of validation errors for mcp.json."""
    data, err = load_json(mcp_path)
    if err:
        return [f"mcp.json: {err}"]
    if not isinstance(data, dict):
        return ["mcp.json: root must be an object"]

    servers = data.get("mcpServers", {})
    rebob = servers.get("rebob") if isinstance(servers, dict) else None
    if not isinstance(rebob, dict):
        return ["mcp.json: missing mcpServers.rebob"]

    errors: list[str] = []
    command = rebob.get("command", "")
    if command and not Path(command).is_file():
        errors.append(f"mcp.json: python not found: {command}")

    args = rebob.get("args", [])
    if args != ["-m", "rebob.server"]:
        errors.append(
            "mcp.json: stale launch args "
            f"(expected [\"-m\", \"rebob.server\"], got {args!r})"
        )

    cwd = rebob.get("cwd", "")
    if cwd and not Path(cwd).is_dir():
        errors.append(f"mcp.json: cwd not found: {cwd}")

    return errors


def check_mcp_import(python: Path) -> tuple[bool, str]:
    """Verify *python* can import rebob.server."""
    try:
        result = subprocess.run(
            [str(python), "-c", "import rebob.server"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False, "import timed out"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "import failed").strip()
        return False, detail.splitlines()[0]
    return True, "ok"


def repair_config(root: Path, *, python: Path | None = None) -> list[str]:
    """Rewrite mcp.json and settings.json from live values. Returns paths written."""
    python = python or resolve_python()
    hook_script = (root / ".rebob" / "hook.py").resolve()

    written: list[str] = []
    mcp_path = root / ".bob" / "mcp.json"
    write_json(mcp_path, build_mcp(python, root))
    written.append(str(mcp_path))

    settings_path = root / ".bob" / "settings.json"
    write_json(settings_path, build_settings(python, hook_script))
    written.append(str(settings_path))

    return written


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
