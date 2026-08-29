"""rebob doctor — validate ReBOB setup in the current project."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from rebob.commands._util import (
    check_mcp_import,
    repair_config,
    resolve_python,
    validate_mcp,
    validate_settings,
)
from rebob.core.paths import project_root

_REQUIRED_ENV = ("IBM_CLOUD_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL")


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def run_doctor(*, fix: bool = False) -> None:
    root = project_root()
    python = resolve_python()
    print(f"ReBOB doctor — project: {root}")
    if fix:
        print("Mode: --fix (will rewrite stale Bob config)")
    print()

    all_ok = True
    config_errors: list[str] = []

    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    all_ok &= _check(".env exists", env_path.exists())

    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    all_ok &= _check(
        "watsonx env vars",
        not missing,
        "missing: " + ", ".join(missing) if missing else "all set",
    )

    hook_path = root / ".rebob" / "hook.py"
    mcp_path = root / ".bob" / "mcp.json"
    settings_path = root / ".bob" / "settings.json"
    all_ok &= _check(".rebob/hook.py", hook_path.is_file(), str(hook_path))
    all_ok &= _check(".bob/mcp.json", mcp_path.is_file(), str(mcp_path))
    all_ok &= _check(".bob/settings.json", settings_path.is_file(), str(settings_path))

    if fix:
        print()
        print("Repairing Bob config from live values...")
        for path in repair_config(root, python=python):
            print(f"  rewrote {path}")

    settings_errors = validate_settings(settings_path) if settings_path.is_file() else ["settings.json: file missing"]
    mcp_errors = validate_mcp(mcp_path) if mcp_path.is_file() else ["mcp.json: file missing"]

    if not fix:
        config_errors.extend(settings_errors)
        config_errors.extend(mcp_errors)

    detail_suffix = "repaired" if fix else "ok"
    all_ok &= _check(
        "settings.json valid",
        not settings_errors,
        settings_errors[0] if settings_errors else detail_suffix,
    )
    all_ok &= _check(
        "mcp.json valid",
        not mcp_errors,
        mcp_errors[0] if mcp_errors else detail_suffix,
    )

    import_ok, import_detail = check_mcp_import(python)
    all_ok &= _check(
        "MCP server import",
        import_ok,
        f"{python} -m rebob.server — {import_detail}",
    )

    try:
        from rebob.core.store import init_db, count_by_status

        init_db()
        stats = count_by_status()
        all_ok &= _check(
            "SQLite store",
            True,
            f"{stats['active']} active / {stats['total']} total memories",
        )
    except Exception as exc:
        all_ok &= _check("SQLite store", False, str(exc))

    if not missing:
        try:
            from rebob.core.watsonx import get_token

            get_token()
            all_ok &= _check("watsonx IAM token", True, "connected")
        except Exception as exc:
            _check("watsonx IAM token", False, str(exc))
            # Soft warning — offline/local FTS still works
            print("  (warn) watsonx unreachable — retrieval will degrade to local-only")

    print()
    if all_ok:
        print("All checks passed.")
    else:
        hint = "rebob doctor --fix" if config_errors and not fix else "rebob init"
        print(f"Some checks failed. Run: {hint}")
        raise SystemExit(1)
