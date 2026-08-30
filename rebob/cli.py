"""rebob — command-line entry point (argparse subcommands)."""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rebob", description="ReBOB — persistent memory for Bob.")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Configure ReBOB in the current project")
    p_init.add_argument("--non-interactive", "--yes", dest="non_interactive", action="store_true")
    p_init.add_argument("--api-key", default="", help="IBM_CLOUD_API_KEY (for --non-interactive)")
    p_init.add_argument("--project-id", default="", help="WATSONX_PROJECT_ID (for --non-interactive)")
    p_init.add_argument("--url", default="", help="WATSONX_URL (for --non-interactive)")
    p_init.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    p_init.add_argument("--port", type=int, default=8000)

    p_doctor = sub.add_parser("doctor", help="Diagnose a ReBOB installation")
    p_doctor.add_argument("--fix", action="store_true", help="Rewrite stale Bob config")

    p_serve = sub.add_parser("serve", help="Run the ReBOB MCP server")
    p_serve.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    p_serve.add_argument("--port", type=int, default=8000)

    sub.add_parser("path", help="Print resolved ReBOB paths as JSON")
    sub.add_parser("version", help="Print ReBOB version and environment info")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command is None:
        parser.print_help()
        raise SystemExit(0)

    if args.command == "init":
        from rebob.commands.init import run_init
        run_init(
            non_interactive=args.non_interactive,
            api_key=args.api_key,
            project_id=args.project_id,
            url=args.url,
            transport=args.transport,
            port=args.port,
        )
    elif args.command == "doctor":
        from rebob.commands.doctor import run_doctor
        run_doctor(fix=args.fix)
    elif args.command == "serve":
        from rebob.commands.serve import run_serve
        run_serve(transport=args.transport, port=args.port)
    elif args.command == "path":
        from rebob.commands.path import run_path
        run_path()
    elif args.command == "version":
        import platform

        from rebob import __version__
        print(f"rebob {__version__}")
        print(f"python {platform.python_version()} on {platform.system()}")
    else:
        parser.print_help()
        raise SystemExit(1)
