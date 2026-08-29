"""rebob doctor — validate ReBOB setup in the current project."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from rebob.core.paths import project_root


_REQUIRED_ENV = ("IBM_CLOUD_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL")


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def run_doctor() -> None:
    root = project_root()
    print(f"ReBOB doctor — project: {root}")
    print()

    all_ok = True

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
        print("Some checks failed. Run: rebob init")
        raise SystemExit(1)
