"""labflash — command-line entry point."""
import argparse
import sys


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="labflash", description="ESP32-S3 Bootloader & OTA Lab CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="environment check (BL-007 stub)")
    resolve_p = sub.add_parser("resolve", help="resolve board device paths by USB serial (BL-040)")
    resolve_p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    resolve_p.add_argument("--wait", type=float, default=5.0, help="seconds to wait for re-enumeration (default 5)")
    sub.add_parser("identify", help="(later epic) map boards by LABID")
    sub.add_parser("info", help="(later epic) show board identity/versions")
    sub.add_parser("flash", help="(later epic) flash a board")
    sub.add_parser("recover", help="(later epic) erase + factory flash")
    sub.add_parser("update", help="(later epic) OTA over BLE/WiFi")

    args = p.parse_args(argv)

    if args.cmd == "doctor":
        from labflash.doctor import main as doctor_main
        return doctor_main()
    if args.cmd == "resolve":
        return _resolve_cmd(json_out=args.json, wait_s=args.wait)
    p.print_help()
    return 1


def _resolve_cmd(json_out: bool, wait_s: float) -> int:
    import json as jsonlib

    from labflash.core import BoardResolutionError, resolve_all_boards

    try:
        mapping = resolve_all_boards(wait_s=wait_s)
    except BoardResolutionError as e:
        if json_out:
            print(jsonlib.dumps({"ok": False, "error": str(e)}))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if json_out:
        print(jsonlib.dumps({"ok": True, "boards": mapping}))
    else:
        for board, path in mapping.items():
            print(f"{board}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
