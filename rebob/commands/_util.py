"""Shared helpers for rebob init / doctor / serve."""

from __future__ import annotations

import json
import os
import re
import sys
from importlib import resources
from pathlib import Path


def load_template(name: str) -> str:
    return resources.files("rebob").joinpath("templates", name).read_text(encoding="utf-8")


def resolve_python() -> Path:
    """Prefer the active venv's interpreter, else the current interpreter.

    Checks both the Windows layout (Scripts\\python.exe) and the POSIX
    layout (bin/python) under VIRTUAL_ENV, so this works correctly
    regardless of host OS.
    """
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        venv_path = Path(venv)
        candidates = [
            venv_path / "Scripts" / "python.exe",  # Windows
            venv_path / "bin" / "python3",  # POSIX
            venv_path / "bin" / "python",  # POSIX
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return Path(sys.executable)


def quote_cmd(path: Path) -> str:
    """Quote a path for hook command strings (Windows-safe, spaces-safe)."""
    return f'"{path}"'


def hook_command(python: Path, hook_type: str) -> str:
    """Build the hook invocation as a module launch: `<python> -m rebob.hook <type>`.

    Using `-m rebob.hook` instead of a script path means there is no second
    absolute path to go stale — only the interpreter path needs to be right.
    """
    return f"{quote_cmd(python)} -m rebob.hook {hook_type}"


def build_settings(python: Path, *, server_url: str = "", api_token: str = "") -> dict:
    """Build Bob settings.json hook config with JSON-safe command strings."""

    def hook_entry(hook_type: str, timeout: int) -> dict:
        hook: dict = {
            "type": "command",
            "command": hook_command(python, hook_type),
            "timeout": timeout,
        }
        if server_url:
            env = {"REBOB_SERVER_URL": server_url.rstrip("/")}
            if api_token:
                env["REBOB_API_TOKEN"] = api_token
            hook["env"] = env
        return {"hooks": [hook]}

    return {
        "hooks": {
            "UserPromptSubmit": [hook_entry("prompt", 8000)],
            "PostToolUse": [hook_entry("tool", 5000)],
            "Stop": [hook_entry("stop", 5000)],
        }
    }


def build_mcp(
    python: Path,
    project_root: Path,
    *,
    transport: str = "stdio",
    port: int = 8000,
    server_url: str = "",
    api_token: str = "",
) -> dict:
    """Build Bob mcp.json using module launch (portable across installs).

    REBOB_HOME is set explicitly in the env block so the server finds the
    right data directory regardless of what cwd Bob actually launches it
    with — belt and braces alongside the `cwd` field.
    """
    if server_url:
        url = server_url.rstrip("/") + "/mcp"
        token = api_token
        if not token:
            try:
                from rebob.credentials import get_token

                token = get_token()
            except Exception:
                token = ""
        server_entry: dict = {"url": url}
        if token:
            server_entry["headers"] = {"Authorization": f"Bearer {token}"}
        return {"mcpServers": {"rebob": server_entry}}

    rebob_home = str((project_root / ".rebob").resolve())
    env = {
        "REBOB_HOME": rebob_home,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }

    if transport == "stdio":
        server_entry = {
            "command": str(python),
            "args": ["-m", "rebob.server"],
            "cwd": str(project_root),
            "env": env,
        }
    else:
        server_entry = {
            "url": f"http://127.0.0.1:{port}/{'sse' if transport == 'sse' else 'mcp'}",
        }

    return {"mcpServers": {"rebob": server_entry}}


_HOOK_CMD_RE = re.compile(r'"([^"]*)"')


def parse_hook_command(command: str) -> tuple[Path, str]:
    """Parse a Bob hook command string (`"<python>" -m rebob.hook <type>`)
    into (python, hook_type).
    """
    parts = _HOOK_CMD_RE.findall(command)
    if not parts:
        raise ValueError(f"invalid hook command: {command!r}")
    hook_type = command.strip().split()[-1]
    return Path(parts[0]), hook_type


def load_json(path: Path) -> tuple[dict | None, str | None]:
    """Load JSON from *path*. Returns (data, error)."""
    if not path.is_file():
        return None, "file missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str, *, overwrite: bool = True) -> bool:
    """Write text to *path*. Returns True if written, False if skipped."""
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def merge_mcp(existing: dict | None, new: dict) -> dict:
    """Merge the rebob server entry into an existing mcp.json, preserving
    any other MCP servers the user already configured.
    """
    merged = dict(existing) if existing else {}
    servers = dict(merged.get("mcpServers", {}))
    servers.update(new.get("mcpServers", {}))
    merged["mcpServers"] = servers
    return merged


def merge_settings(existing: dict | None, new: dict) -> dict:
    """Merge rebob's hook entries into an existing settings.json, preserving
    any other hooks the user already configured for the same event names.

    For each hook event (UserPromptSubmit, PostToolUse, Stop), drops any
    prior entry whose command was a rebob hook invocation, then appends
    the fresh one — avoiding duplicate rebob entries across repeated
    `rebob init` runs while leaving unrelated hooks untouched.
    """
    merged = dict(existing) if existing else {}
    hooks = dict(merged.get("hooks", {}))

    for event, entries in new.get("hooks", {}).items():
        existing_entries = list(hooks.get(event, []))
        kept = [
            e for e in existing_entries
            if not _is_rebob_hook_entry(e)
        ]
        hooks[event] = kept + entries

    merged["hooks"] = hooks
    return merged


def _is_rebob_hook_entry(entry: dict) -> bool:
    for h in entry.get("hooks", []):
        if "rebob.hook" in h.get("command", ""):
            return True
    return False


def ensure_gitignore_entries(root: Path, entries: list[str]) -> list[str]:
    """Append any missing entries to .gitignore. Returns the list actually added."""
    gitignore = root / ".gitignore"
    existing_lines = set()
    if gitignore.exists():
        existing_lines = {ln.strip() for ln in gitignore.read_text(encoding="utf-8").splitlines()}

    to_add = [e for e in entries if e not in existing_lines]
    if to_add:
        with gitignore.open("a", encoding="utf-8") as f:
            if gitignore.exists() and gitignore.stat().st_size > 0:
                f.write("\n")
            f.write("# ReBOB (added by `rebob init`)\n")
            for e in to_add:
                f.write(e + "\n")
    return to_add


def confirm_overwrite(path: Path) -> bool:
    answer = input(f"{path} already exists - overwrite? [y/N]: ").strip().lower()
    return answer in ("y", "yes")
