"""rebob doctor — diagnose a ReBOB installation."""

from __future__ import annotations

import platform
import sys

from rebob import paths
from rebob.commands._util import (
    build_mcp,
    build_settings,
    load_json,
    merge_mcp,
    merge_settings,
    resolve_python,
    write_json,
)

_REQUIRED_ENV = ("IBM_CLOUD_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL")


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = "[ok]" if ok else "[FAIL]"
    line = f"  {status} {label}"
    if detail:
        line += f" - {detail}"
    print(line)
    return ok


def _check_mcp_import() -> tuple[bool, str]:
    try:
        import fastmcp  # noqa: F401

        from rebob import server  # noqa: F401

        return True, f"fastmcp {getattr(fastmcp, '__version__', '?')}"
    except Exception as e:
        return False, str(e)


def run_doctor(*, fix: bool = False) -> None:
    root = paths.project_root()
    python = resolve_python()

    print(f"ReBOB doctor - project: {root}")
    print(f"Python: {python} ({platform.python_version()} on {platform.system()})")
    if fix:
        print("Mode: --fix (will rewrite stale Bob config)")
    print()

    print("Resolved paths:")
    for key, value in paths.describe().items():
        print(f"  {key}: {value}")
    print()

    all_ok = True

    env_path = paths.env_file()
    if env_path.exists():
        from dotenv import dotenv_values

        env_vars = dotenv_values(env_path)
        missing = [k for k in _REQUIRED_ENV if not env_vars.get(k)]
        all_ok &= _check(
            ".env has required keys",
            not missing,
            f"missing: {', '.join(missing)}" if missing else "ok",
        )
    else:
        all_ok &= _check(".env exists", False, str(env_path))

    mcp_path = root / ".bob" / "mcp.json"
    settings_path = root / ".bob" / "settings.json"

    all_ok &= _check(".bob/mcp.json exists", mcp_path.is_file(), str(mcp_path))
    all_ok &= _check(".bob/settings.json exists", settings_path.is_file(), str(settings_path))

    if fix:
        print()
        print("Repairing Bob config from live values...")
        existing_mcp, _ = load_json(mcp_path)
        transport = "stdio"
        if existing_mcp and "url" in existing_mcp.get("mcpServers", {}).get("rebob", {}):
            transport = "sse"
        write_json(mcp_path, merge_mcp(existing_mcp, build_mcp(python, root, transport=transport)))
        print(f"  rewrote {mcp_path}")

        existing_settings, _ = load_json(settings_path)
        write_json(settings_path, merge_settings(existing_settings, build_settings(python)))
        print(f"  rewrote {settings_path}")

    mcp_data, mcp_err = load_json(mcp_path)
    settings_data, settings_err = load_json(settings_path)

    rebob_entry = (mcp_data or {}).get("mcpServers", {}).get("rebob")
    mcp_problem = mcp_err or ("no 'rebob' entry in mcpServers" if not rebob_entry else None)
    all_ok &= _check("mcp.json valid", mcp_problem is None, mcp_problem or "ok")

    settings_problem = settings_err
    all_ok &= _check("settings.json valid", settings_problem is None, settings_problem or "ok")

    import_ok, import_detail = _check_mcp_import()
    all_ok &= _check("MCP server import", import_ok, import_detail)

    try:
        from rebob.core.store import count_by_status, init_db

        init_db()
        counts = count_by_status()
        all_ok &= _check(
            "memory store readable",
            True,
            f"{counts['total']} total ({counts['active']} active)",
        )
    except Exception as e:
        all_ok &= _check("memory store readable", False, str(e))

    print()
    if all_ok:
        print("All checks passed.")
    else:
        hint = "rebob doctor --fix" if not fix else "rebob init"
        print(f"Some checks failed. Run: {hint}")
        raise SystemExit(1)
