"""rebob init — configure ReBOB in the current project."""

from __future__ import annotations

import getpass

from rebob import paths
from rebob.commands._util import (
    build_mcp,
    build_settings,
    confirm_overwrite,
    ensure_gitignore_entries,
    load_json,
    load_template,
    merge_mcp,
    merge_settings,
    resolve_python,
    write_json,
    write_text,
)


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


def run_init(
    *,
    non_interactive: bool = False,
    api_key: str = "",
    project_id: str = "",
    url: str = "",
    transport: str = "stdio",
    port: int = 8000,
) -> None:
    root = paths.project_root()
    python = resolve_python()

    print(f"ReBOB init - project: {root}")
    print(f"Python: {python}")
    print()

    env_path = paths.env_file()
    write_env = True
    if env_path.exists():
        if non_interactive:
            write_env = False
            print(f"  .env exists, keeping it ({env_path})")
        elif not confirm_overwrite(env_path):
            write_env = False
            print("Skipping .env (keeping existing file).")

    if write_env:
        if non_interactive:
            if not (api_key and project_id):
                print("ERROR: --non-interactive requires --api-key and --project-id")
                raise SystemExit(1)
            url = url or "https://us-south.ml.cloud.ibm.com"
        else:
            print("IBM watsonx credentials (from IBM Cloud -> watsonx project):")
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

    mcp_path = root / ".bob" / "mcp.json"
    existing_mcp, _ = load_json(mcp_path)
    new_mcp = build_mcp(python, root, transport=transport, port=port)
    write_json(mcp_path, merge_mcp(existing_mcp, new_mcp))
    print(f"  wrote {mcp_path} (transport={transport})")

    settings_path = root / ".bob" / "settings.json"
    existing_settings, _ = load_json(settings_path)
    new_settings = build_settings(python)
    write_json(settings_path, merge_settings(existing_settings, new_settings))
    print(f"  wrote {settings_path}")

    mem_path = root / ".bob" / "commands" / "mem.md"
    if write_text(mem_path, load_template("mem.md")):
        print(f"  wrote {mem_path}")

    rules_path = root / ".bob" / "rules" / "rules.md"
    if write_text(rules_path, load_template("rules.md")):
        print(f"  wrote {rules_path}")

    skill_path = root / ".bob" / "skills" / "mem" / "SKILL.md"
    if write_text(skill_path, load_template("SKILL.md")):
        print(f"  wrote {skill_path}")

    added = ensure_gitignore_entries(
        root,
        [".rebob/", ".env", "*.npy", ".bob/mcp.json", ".bob/settings.json"],
    )
    if added:
        print(f"  added to .gitignore: {', '.join(added)}")

    print()
    print("ReBOB initialized.")
    print("Next steps:")
    print("  1. Open this folder in Bob IDE")
    print("  2. Settings -> MCP -> enable tools for new tasks")
    print("  3. Run: rebob doctor")
    print("  4. Start a new Bob task and type a prompt")
