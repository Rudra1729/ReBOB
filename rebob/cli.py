def main() -> None:
    import sys

    # Some Windows consoles (Git Bash in particular) default stdout/stderr
    # to a non-UTF-8 codepage. init.py and doctor.py print Unicode
    # decoration (em-dash, arrows, checkmarks); without this, the first
    # such character raises UnicodeEncodeError and aborts the command
    # before it writes anything. errors="replace" makes that merely
    # cosmetic (a "?" in place of the character) instead of a hard crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("ReBOB installed.")
        print()
        print("Next: run `rebob init` in your project's root directory")
        print("      (wherever you'll open this project in Bob IDE).")
        print()
        print("Commands: rebob init | rebob doctor")
        raise SystemExit(0)

    cmd = sys.argv[1]
    if cmd == "init":
        from rebob.commands.init import run_init
        run_init()
    elif cmd == "doctor":
        from rebob.commands.doctor import run_doctor
        run_doctor()
    else:
        print(f"unknown command: {cmd}")
        raise SystemExit(1)
