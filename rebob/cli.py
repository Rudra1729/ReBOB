def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("ReBOB — usage: rebob init | rebob doctor")
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
