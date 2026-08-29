"""rebob init — configure ReBOB in the current project."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

import rebob.server

from rebob.commands._util import (
    confirm_overwrite,
    ensure_gitignore_entries,
    load_template,
    merge_mcp_server,
    merge_rebob_hooks,
    read_json,
    write_json,
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

    # mcp.json / settings.json are merged, not replaced -- a project may already have
    # its own MCP servers and hooks configured, and overwriting the whole file would
    # silently delete them. Only ReBOB's own entries are added or refreshed.
    mcp_path = root / ".bob" / "mcp.json"
    mcp_data = merge_mcp_server(read_json(mcp_path), python, server_script, root)
    write_json(mcp_path, mcp_data)
    print(f"  wrote {mcp_path} (merged)")

    settings_path = root / ".bob" / "settings.json"
    settings_data = merge_rebob_hooks(read_json(settings_path), python, hook_script)
    write_json(settings_path, settings_data)
    print(f"  wrote {settings_path} (merged)")

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
