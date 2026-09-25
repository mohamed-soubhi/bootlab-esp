"""labflash — command-line entry point."""
import argparse
import sys
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="labflash", description="ESP32-S3 Bootloader & OTA Lab CLI")
    sub = p.add_subparsers(dest="command", required=True)

    def add_cmd(name: str, *args: Any, **kwargs: Any) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, *args, **kwargs)
        sp.set_defaults(cmd=name)
        return sp

    add_cmd("doctor", help="environment check (BL-007 stub)")
    resolve_p = add_cmd("resolve", help="resolve board device paths by USB serial (BL-040)")
    resolve_p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    resolve_p.add_argument("--wait", type=float, default=5.0, help="seconds to wait for re-enumeration (default 5)")
    id_p = add_cmd(
        "identify",
        help="map boards by LABID query over serial (BL-041)",
        description="Sends LABID $LAB,ID? over serial and matches device UID against rig.yaml.",
    )
    id_p.add_argument("--port", help="serial port to query (default: resolve all boards)")
    id_p.add_argument("--board", choices=["idf", "zephyr"], help="board to identify")
    id_p.add_argument("--json", action="store_true", help="output JSON")

    info_p = add_cmd(
        "info",
        help="show board identity, software versions, and runtime state (BL-041)",
        description="Queries LABID ID?, VER?, and STATE? from the board.",
    )
    info_p.add_argument("board", choices=["idf", "zephyr"], help="board to query")
    info_p.add_argument("--port", help="serial port to query (default: resolved from rig.yaml)")
    info_p.add_argument("--json", action="store_true", help="output JSON")

    meas_p = add_cmd(
        "measure",
        help="measure LED blink rate over LABID from toggle counter (BL-041)",
        description="Samples STATE.toggles over duration and verifies measured Hz matches expected blink rate.",
    )
    meas_p.add_argument("board", choices=["idf", "zephyr"], help="board to measure")
    meas_p.add_argument("--port", help="serial port to query (default: resolved from rig.yaml)")
    meas_p.add_argument("--seconds", type=float, default=5.0, help="sample duration in seconds (default: 5.0)")
    meas_p.add_argument("--expect-hz", type=float, default=None, help="expected blink rate in Hz")
    meas_p.add_argument("--tolerance", type=int, default=1, help="acceptable toggle delta error (default: +/-1 toggle)")

    flash_p = add_cmd(
        "flash",
        help="factory flash a board with identity check before writing (BL-042)",
        description="Flashes bootloader, partition table, otadata, and factory app to the board. "
                    "Enforces mandatory hardware identity check before writing.",
    )
    flash_p.add_argument("board", choices=["idf", "zephyr"], help="board to flash")
    flash_p.add_argument("--port", help="serial port (default: resolved from rig.yaml)")

    rec_p = add_cmd(
        "recover",
        help="erase flash and factory flash a board with identity check before writing (BL-042)",
        description="Erases flash and re-flashes factory binaries with identity check before writing.",
    )
    rec_p.add_argument("board", choices=["idf", "zephyr"], help="board to recover")
    rec_p.add_argument("--port", help="serial port (default: resolved from rig.yaml)")
    upd = add_cmd(
        "update", help="OTA an ESP-IDF or Zephyr board over BLE, WiFi, or UDP and verify it via LABID (BL-043, BL-044)",
        description="Sends a signed app image to the board, then verifies: it runs the version the image carries, "
                    "the slot is confirmed, the uid matches, and LABID agrees with transport status (HTTPS or SMP). "
                    "The board's identity is checked BEFORE anything is sent.")
    upd.add_argument("board", choices=["idf", "zephyr"], help="board to update")
    upd.add_argument("--image", required=True, help="signed application .bin (4096-aligned for BLE on IDF)")
    upd.add_argument("--transport", choices=["ble", "wifi", "udp"], required=True)
    upd.add_argument("--labid-port", help="serial port for LABID verification (default: resolved from rig.yaml)")
    upd.add_argument("--no-labid", action="store_true", help="verify over transport only (identity is then NOT checked)")
    upd.add_argument("--board-mac", help="board base MAC (default: from rig.yaml); BLE address must share its first 5 octets")
    upd.add_argument("--address", help="BLE address (default: ble_mac from rig.yaml or scan)")
    upd.add_argument("--scan-timeout", type=float, default=10.0)
    upd.add_argument("--board-ip", help="board IP (required for wifi or zephyr udp if not in rig.yaml)")
    upd.add_argument("--udp-port", type=int, default=1337, help="UDP SMP port for Zephyr (default 1337)")
    upd.add_argument("--host-ip", help="IP the board uses to reach this machine (default: auto)")
    upd.add_argument("--http-port", type=int, default=8443, help="local HTTPS image server port (default 8443)")
    upd.add_argument("--keys", help="dir with ca.pem, server_cert.pem, server_key.pem (default: <repo>/keys)")
    upd.add_argument("--ca-cert")
    upd.add_argument("--server-cert")
    upd.add_argument("--server-key")
    upd.add_argument("--token", help="OTA bearer token (default: OTA_TOKEN from --env-file)")
    upd.add_argument("--env-file", default="credentials.env")
    upd.add_argument("--rig", help="rig.yaml path (default: host/config/rig.yaml)")
    upd.add_argument("--timeout", type=float, default=240.0, help="seconds to wait for the new version (default 240)")
    upd.add_argument("--confirm-timeout", type=float, default=30.0, help="seconds to wait for confirmation (default 30)")

    prov_p = add_cmd("provision", help="write WiFi credentials + token to NVS (BL-024)")
    prov_p.add_argument("board", choices=["idf"], help="board to provision")
    prov_p.add_argument("--ssid", help="WiFi SSID (defaults to WIFI_SSID from env file)")
    prov_p.add_argument("--psk", help="WiFi password (defaults to WIFI_PSK from env file)")
    prov_p.add_argument("--psk-file", help="Path to file containing WiFi password")
    prov_p.add_argument("--token", help="Bearer token for OTA server (defaults to OTA_TOKEN from env file)")
    prov_p.add_argument("--env-file", default="credentials.env", help="Path to credentials env file (default: credentials.env)")
    prov_p.add_argument("--port", help="Explicit serial port (defaults to resolved rig.yaml port)")

    bld_p = add_cmd(
        "build",
        help="build and sign application image variants (BL-045)",
        description="Builds and signs IDF / Zephyr application image variants per PLAN R15. "
                    "Enforces per-dir sdkconfig and verifies symbols and RSA signatures post-build."
    )
    bld_p.add_argument("board", choices=["idf", "zephyr", "all"], help="board to build for")
    bld_p.add_argument(
        "--variant",
        choices=["v1", "v2", "v3", "v4", "no_confirm", "hang", "bad_sig", "all"],
        default=None,
        help="variant to build (default: all)",
    )
    bld_p.add_argument("--clean", action="store_true", help="clean build directory before building")

    gen_p = add_cmd(
        "gen-images",
        help="build the BL-069 signed image pool offline (WSL only)",
        description="Generates deterministic signed IDF images that differ in size, LED behaviour and spare pins, "
                    "and writes manifest.json next to them.",
    )
    gen_p.add_argument("--out", required=True, help="output directory (e.g. esp_idf/build_pool)")
    gen_p.add_argument("--seed-base", required=True, help="name that seeds the whole pool (recorded in the manifest)")
    gen_p.add_argument("--limit", type=int, default=None, help="build only the first N images (no manifest)")
    gen_p.add_argument("--only", default=None, help="comma-separated image indices to build (no manifest)")
    gen_p.add_argument("--dry-run", action="store_true", help="print the plan without building")

    gui_p = add_cmd(
        "gui",
        help="launch the bootlab-esp web operations console",
        description="Launch local browser operations console to run and monitor tools.",
    )
    gui_p.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    gui_p.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    gui_p.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    return p


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    p = build_parser()
    args = p.parse_args(argv)

    cmd = getattr(args, "command", getattr(args, "cmd", None))
    if cmd == "gui":
        from labflash.gui_cmd import run_gui
        return run_gui(host=args.host, port=args.port, open_browser=not args.no_browser)
    if cmd == "doctor":
        from labflash.doctor import main as doctor_main
        return doctor_main()
    if cmd == "resolve":
        return _resolve_cmd(json_out=args.json, wait_s=args.wait)
    if cmd == "provision":
        return _provision_cmd(args)
    if cmd == "update":
        from labflash.update_cli import run_update
        return run_update(args)
    if cmd == "build":
        return _build_cmd(args)
    if cmd == "gen-images":
        return _gen_images_cmd(args)
    if cmd == "identify":
        return _identify_cmd(args)
    if cmd == "info":
        return _info_cmd(args)
    if cmd == "measure":
        return _measure_cmd(args)
    if cmd == "flash":
        return _flash_cmd(args, recover=False)
    if cmd == "recover":
        return _flash_cmd(args, recover=True)
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
        except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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


def _build_cmd(args) -> int:
    from labflash.build import BuildError, ZephyrGatedError, build_board

    try:
        results = build_board(args.board, variant=args.variant, clean=args.clean)
        print("\n=== Build & Signature Verification Results ===")
        print(f"{'Variant':<12} {'Version':<16} {'Size (B)':<10} {'Symbol Check':<15} {'Signature':<12}")
        print("-" * 75)
        for var, res in results.items():
            var_ok = "PASS" if res.verified_variant else "FAIL"
            sig_ok = "PASS" if res.verified_signature else "FAIL"
            print(f"{var:<12} {res.project_ver:<16} {res.binary_size:<10} {var_ok:<15} {sig_ok:<12}")
            if res.details:
                print(f"  -> {res.binary_path} ({res.details})")
        print("\nAll built variants verified successfully (PLAN R15).")
        return 0
    except ZephyrGatedError as e:
        print(f"[BLOCKED] {e}", file=sys.stderr)
        return 2
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _gen_images_cmd(args) -> int:
    from pathlib import Path

    from labflash.build import BuildError
    from labflash.genvariants import GenError, run
    from labflash.poolmanifest import ManifestError

    try:
        only = [int(x) for x in args.only.split(",")] if args.only else None
        return run(Path(args.out), args.seed_base, limit=args.limit, dry_run=args.dry_run, only=only)
    except (BuildError, GenError, ManifestError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _identify_cmd(args) -> int:
    import json as jsonlib

    from labflash.core import BoardResolutionError, load_rig_config, resolve_board
    from labflash.identify import (
        SerialLineTransport,
        map_board_by_id,
    )

    rig = load_rig_config()
    out: dict[str, dict[str, Any]] = {}

    ports_to_check: list[tuple[str, str | None]] = []
    if args.port:
        ports_to_check.append((args.port, args.board))
    elif args.board:
        try:
            p = resolve_board(args.board, rig=rig)
            ports_to_check.append((p, args.board))
        except BoardResolutionError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    else:
        for bkey in rig.get("boards", {}):
            try:
                p = resolve_board(bkey, rig=rig, wait_s=0.5)
                ports_to_check.append((p, bkey))
            except BoardResolutionError:
                pass

    if not ports_to_check:
        print("ERROR: no boards resolved to scan", file=sys.stderr)
        return 1

    for port, hint in ports_to_check:
        try:
            trans = SerialLineTransport(port)
            try:
                bname, id_fields = map_board_by_id(trans, rig=rig)
                out[bname] = {"port": port, "id": id_fields}
            finally:
                trans.close()
        except Exception as e:  # noqa: BLE001
            if args.board or args.port:
                print(f"ERROR on {port}: {e}", file=sys.stderr)
                return 1

    if args.json:
        print(jsonlib.dumps({"ok": True, "identified": out}))
    else:
        print(f"{'Board':<10} {'Port':<16} {'UID':<16} {'MCU':<12} {'Board Name'}")
        print("-" * 65)
        for bname, info in out.items():
            idf = info["id"]
            print(f"{bname:<10} {info['port']:<16} {idf.get('uid', ''):<16} {idf.get('mcu', ''):<12} {idf.get('board', '')}")
    return 0


def _info_cmd(args) -> int:
    import json as jsonlib

    from labflash.core import BoardResolutionError, resolve_board
    from labflash.identify import SerialLineTransport, query_info

    port = args.port
    if not port:
        try:
            port = resolve_board(args.board)
        except BoardResolutionError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    try:
        trans = SerialLineTransport(port)
        try:
            info = query_info(trans)
        finally:
            trans.close()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR querying {args.board} on {port}: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(jsonlib.dumps({"ok": True, "board": args.board, "port": port, **info}))
    else:
        id_f = info["id"]
        ver_f = info["version"]
        st_f = info["state"]
        print(f"=== {args.board} on {port} ===")
        print(f"Identity : UID={id_f.get('uid')} MCU={id_f.get('mcu')} HW={id_f.get('hw')} OS={id_f.get('os')} Flash={id_f.get('flash_kb')}KB")
        print(f"Version  : App={ver_f.get('app')} Git={ver_f.get('git')} Slot={ver_f.get('slot')} Confirmed={ver_f.get('confirmed')} Variant={ver_f.get('variant')}")
        print(f"State    : Toggles={st_f.get('toggles')} Rate={st_f.get('blink_hz')}Hz Uptime={st_f.get('uptime_ms')}ms Reset={st_f.get('reset')}")
    return 0


def _measure_cmd(args) -> int:
    from labflash.core import BoardResolutionError, resolve_board
    from labflash.identify import SerialLineTransport, get_state, measure

    port = args.port
    if not port:
        try:
            port = resolve_board(args.board)
        except BoardResolutionError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    try:
        trans = SerialLineTransport(port)
        try:
            expect_hz = args.expect_hz
            if expect_hz is None:
                try:
                    s = get_state(trans)
                    expect_hz = float(s.get("blink_hz", 1.0))
                except Exception:  # noqa: BLE001
                    expect_hz = 1.0
            delta, hz, ok = measure(
                trans,
                duration_s=args.seconds,
                expect_hz=expect_hz,
                tolerance_toggles=args.tolerance,
            )
        finally:
            trans.close()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR measuring {args.board} on {port}: {e}", file=sys.stderr)
        return 1

    expected_toggles = round(expect_hz * args.seconds * 2.0)
    res_str = "PASS" if ok else "FAIL"
    print(f"[{res_str}] toggles delta={delta} in {args.seconds:.2f}s = {hz:.2f} Hz (expected {expected_toggles} toggles, {expect_hz} Hz, tolerance +/- {args.tolerance})")
    return 0 if ok else 1


def _flash_cmd(args, recover: bool = False) -> int:
    from labflash.flash import FlashError, ZephyrGatedError, flash_board

    try:
        flash_board(args.board, port=args.port, recover=recover)
        return 0
    except ZephyrGatedError as e:
        print(f"[BLOCKED] {e}", file=sys.stderr)
        return 2
    except FlashError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
