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
    p_init.add_argument("--transport", choices=["stdio", "sse", "http"], default="stdio")
    p_init.add_argument("--port", type=int, default=8000)
    p_init.add_argument("--server", default="", help="Hosted ReBOB server URL (enables HTTP mode)")
    p_init.add_argument("--api-token", default="", help="Bearer token for hosted MCP (optional)")

    p_doctor = sub.add_parser("doctor", help="Diagnose a ReBOB installation")
    p_doctor.add_argument("--fix", action="store_true", help="Rewrite stale Bob config")

    p_serve = sub.add_parser("serve", help="Run the ReBOB MCP server")
    p_serve.add_argument("--transport", choices=["stdio", "sse", "http"], default="stdio")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="0.0.0.0")

    p_login = sub.add_parser("login", help="Store hosted API token")
    p_login.add_argument("--token", required=True, help="Bearer token from rebob admin issue-token")
    p_login.add_argument("--server-url", default="", help="Hosted server base URL")

    p_admin = sub.add_parser("admin", help="Server administration")
    p_admin_sub = p_admin.add_subparsers(dest="admin_command")
    p_issue = p_admin_sub.add_parser("issue-token", help="Issue a new API token")
    p_issue.add_argument("--org", required=True, help="Organization name")
    p_issue.add_argument("--author", default="", help="Author id/email")
    p_issue.add_argument("--admin-token", default="", help="Admin token (or REBOB_ADMIN_TOKEN env)")

    p_wx = sub.add_parser("register-watsonx", help="Register BYO watsonx creds with hosted server")
    p_wx.add_argument("--api-key", default="", help="IBM_CLOUD_API_KEY")
    p_wx.add_argument("--project-id", default="", help="WATSONX_PROJECT_ID")
    p_wx.add_argument("--url", default="", help="WATSONX_URL")

    p_privacy = sub.add_parser("privacy", help="Show redacted events that would be transmitted")
    p_privacy.add_argument("--show", action="store_true", help="Print sanitized session payload")
    p_privacy.add_argument("--session", default="", help="Session id (default: most recent)")

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
            server=args.server,
            api_token=args.api_token,
        )
    elif args.command == "doctor":
        from rebob.commands.doctor import run_doctor
        run_doctor(fix=args.fix)
    elif args.command == "serve":
        from rebob.commands.serve import run_serve
        run_serve(transport=args.transport, port=args.port, host=args.host)
    elif args.command == "login":
        from rebob.commands.login import run_login
        run_login(token=args.token, server_url=args.server_url)
    elif args.command == "admin":
        if args.admin_command == "issue-token":
            from rebob.commands.admin import run_admin_issue_token
            run_admin_issue_token(org=args.org, author=args.author, admin_token=args.admin_token)
        else:
            parser.print_help()
            raise SystemExit(1)
    elif args.command == "register-watsonx":
        from rebob.commands.register_watsonx import run_register_watsonx
        run_register_watsonx(api_key=args.api_key, project_id=args.project_id, url=args.url)
    elif args.command == "privacy":
        from rebob.commands.privacy import run_privacy
        run_privacy(session_id=args.session)
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
