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

    prov_p = sub.add_parser("provision", help="write WiFi credentials + token to NVS (BL-024)")
    prov_p.add_argument("board", choices=["idf"], help="board to provision")
    prov_p.add_argument("--ssid", help="WiFi SSID (defaults to WIFI_SSID from env file)")
    prov_p.add_argument("--psk", help="WiFi password (defaults to WIFI_PSK from env file)")
    prov_p.add_argument("--psk-file", help="Path to file containing WiFi password")
    prov_p.add_argument("--token", help="Bearer token for OTA server (defaults to OTA_TOKEN from env file)")
    prov_p.add_argument("--env-file", default="credentials.env", help="Path to credentials env file (default: credentials.env)")
    prov_p.add_argument("--port", help="Explicit serial port (defaults to resolved rig.yaml port)")

    args = p.parse_args(argv)

    if args.cmd == "doctor":
        from labflash.doctor import main as doctor_main
        return doctor_main()
    if args.cmd == "resolve":
        return _resolve_cmd(json_out=args.json, wait_s=args.wait)
    if args.cmd == "provision":
        return _provision_cmd(args)
    p.print_help()
    return 1


def _provision_cmd(args) -> int:
    import os
    from labflash.core import BoardResolutionError, resolve_board
    from labflash.provision import load_credentials_from_env, provision_idf

    creds = {}
    if os.path.exists(args.env_file):
        try:
            creds = load_credentials_from_env(args.env_file)
        except Exception as e:
            print(f"Warning: could not load {args.env_file}: {e}", file=sys.stderr)

    ssid = args.ssid or creds.get("ssid") or os.environ.get("WIFI_SSID")
    if not ssid:
        print("ERROR: WiFi SSID not provided (--ssid or WIFI_SSID in credentials.env)", file=sys.stderr)
        return 1

    psk = args.psk
    if not psk and args.psk_file:
        with open(args.psk_file, "r") as f:
            psk = f.read().strip()
    if not psk:
        psk = creds.get("psk") or os.environ.get("WIFI_PSK") or ""

    token = args.token or creds.get("token") or os.environ.get("OTA_TOKEN") or "lab-bearer-token-default"

    port = args.port
    if not port:
        try:
            port = resolve_board(args.board)
        except BoardResolutionError as e:
            print(f"ERROR: could not resolve board {args.board}: {e}", file=sys.stderr)
            return 1

    print(f"Provisioning {args.board} on {port} (NVS 0x9000)...")
    try:
        provision_idf(port=port, ssid=ssid, psk=psk, token=token)
        print("OK: Provisioning complete. Board will connect to WiFi on next boot.")
        return 0
    except Exception as e:
        print(f"ERROR: Provisioning failed: {e}", file=sys.stderr)
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
