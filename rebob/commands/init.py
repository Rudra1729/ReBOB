"""rebob init — configure ReBOB in the current project."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

import rebob.server

from rebob.commands._util import (
    confirm_overwrite,
    ensure_gitignore_entries,
    hook_command,
    load_template,
    render_template,
    write_text,
)
from rebob.core.paths import project_root


def _prompt(label: str, default: str = "", *, secret: bool = False) -> str:
    if default:
        label = f"{label} [{default}]"
    label += ": "
    if secret:
        value = getpass.getpass(label)
    else:
        value = input(label)
    value = value.strip()
    return value or default


def run_init() -> None:
    root = project_root()
    python = Path(sys.executable).resolve()
    hook_script = (root / ".rebob" / "hook.py").resolve()
    server_script = Path(rebob.server.__file__).resolve()

    print(f"ReBOB init — project: {root}")
    print(f"Python: {python}")
    print()

    env_path = root / ".env"
    if env_path.exists() and not confirm_overwrite(env_path):
        print("Skipping .env (keeping existing file).")
        api_key = project_id = url = None
    else:
        print("IBM watsonx credentials (from IBM Cloud → watsonx project):")
        api_key = _prompt("IBM_CLOUD_API_KEY", secret=True)
        project_id = _prompt("WATSONX_PROJECT_ID")
        url = _prompt("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        env_body = (
            f"IBM_CLOUD_API_KEY={api_key}\n"
            f"WATSONX_PROJECT_ID={project_id}\n"
            f"WATSONX_URL={url}\n"
            f"WATSONX_LLM_MODEL=ibm/granite-4-h-small\n"
            f"WATSONX_EMBEDDING_MODEL=ibm/granite-embedding-278m-multilingual\n"
        )
        write_text(env_path, env_body, overwrite=True)
        print(f"  wrote {env_path}")

    hook_py = load_template("hook.py")
    write_text(hook_script, hook_py, overwrite=True)
    print(f"  wrote {hook_script}")

    mcp_body = render_template(
        "mcp.json",
        PYTHON=str(python),
        SERVER_SCRIPT=str(server_script),
        PROJECT_ROOT=str(root),
    )
    mcp_path = root / ".bob" / "mcp.json"
    if not mcp_path.exists() or confirm_overwrite(mcp_path):
        write_text(mcp_path, mcp_body, overwrite=True)
        print(f"  wrote {mcp_path}")

    settings_body = render_template(
        "settings.json",
        HOOK_PROMPT=hook_command(python, hook_script, "prompt"),
        HOOK_TOOL=hook_command(python, hook_script, "tool"),
        HOOK_STOP=hook_command(python, hook_script, "stop"),
    )
    settings_path = root / ".bob" / "settings.json"
    if not settings_path.exists() or confirm_overwrite(settings_path):
        write_text(settings_path, settings_body, overwrite=True)
        print(f"  wrote {settings_path}")

    mem_path = root / ".bob" / "commands" / "mem.md"
    if write_text(mem_path, load_template("mem.md")):
        print(f"  wrote {mem_path}")

    rules_path = root / ".bob" / "rules" / "rules.md"
    if write_text(rules_path, load_template("rules.md")):
        print(f"  wrote {rules_path}")

    added = ensure_gitignore_entries(root, [".rebob/", ".env", "*.npy"])
    if added:
        print(f"  added to .gitignore: {', '.join(added)}")

    print()
    print("ReBOB initialized.")
    print("Next steps:")
    print("  1. Open this folder in Bob IDE")
    print("  2. Settings → MCP → enable tools for new tasks")
    print("  3. Run: rebob doctor")
    print("  4. Start a new Bob task and type a prompt")
