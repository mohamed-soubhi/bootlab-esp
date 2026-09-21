"""labflash update — command-line adapters for `labflash update idf` (BL-043).

Wires the real transports (BLE via bleak, WiFi via a local HTTPS server) and the real board
readers (LABID over serial, HTTPS /version) into the pure orchestration in labflash.update.

Where to run it: the serial port and the BLE radio must be used NATIVELY (Windows, or the RPi4).
Over usbipd/WSL2 the board resets when the port is opened (PLAN R14) and WSL2 has no Bluetooth.
From WSL2 the WiFi transport works with --no-labid, provided the board can reach this machine
(WSL2 NAT hides it from the LAN: run scripts/tcp_forwarder.py on Windows and pass --host-ip).
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
import tempfile
from pathlib import Path

from labflash.update import Snapshot, UpdateError, update_idf

REPO = Path(__file__).resolve().parents[2]
DEFAULT_KEYS = REPO / "keys"
DEFAULT_TOKEN = "lab-bearer-token-default"   # what `labflash provision` writes when no token is given
TOKEN_KEYS = ("OTA_TOKEN", "LAB_TOKEN")


def guess_host_ip(target_ip: str) -> str:
    """The local address the OS would use to reach the board (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((target_ip, 9))
        return s.getsockname()[0]


def read_token(env_file: str | None, explicit: str | None) -> str:
    if explicit:
        return explicit
    from_env = os.environ.get("OTA_TOKEN")     # same variable `labflash provision` honours
    if from_env:
        return from_env
    if env_file and Path(env_file).exists():
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            key, _, value = line.strip().partition("=")
            if key in TOKEN_KEYS:
                return value.strip().strip("\"'")
    print("note: no OTA token found; using the provisioning default", file=sys.stderr)
    return DEFAULT_TOKEN


def rig_mac(rig_path: str | None, board: str) -> str | None:
    try:
        from labflash.core import load_rig_config
        rig = load_rig_config(rig_path)
    except Exception:   # noqa: BLE001 - optional (no yaml / no file): --board-mac can replace it
        return None
    return rig.get("boards", {}).get(board, {}).get("mac") or None


def labid_snapshot_fn(port: str):
    def snap() -> Snapshot:
        from labflash.identify import SerialLineTransport, get_version, identify
        tr = SerialLineTransport(port)
        try:
            ver, ident = get_version(tr), identify(tr)
        finally:
            tr.close()
        return Snapshot(app=ver["app"], slot=int(ver["slot"]), confirmed=ver["confirmed"] == "1",
                        uid=ident.get("uid"), source="labid")
    return snap


def https_snapshot_fn(board):
    def snap() -> Snapshot:
        v = board.version()
        if v is None:
            raise UpdateError("the board did not answer GET /version")
        return Snapshot(app=v["app"], slot=int(v["slot"]), confirmed=bool(v["confirmed"]), uid=None, source="https")
    return snap


def make_wifi_send(board, server, host_ip: str, workdir: Path):
    def send(image: bytes, version: str) -> None:
        (workdir / "update.bin").write_bytes(image)
        status = board.trigger(f"https://{host_ip}:{server.port}/update.bin", version)
        if status != 202:
            raise UpdateError(f"the board refused POST /ota: HTTP {status} (401 = wrong token, 409 = an OTA is running)")
        print(f"  WiFi: board accepted the request; serving {len(image)} bytes from {host_ip}:{server.port}", flush=True)
    return send


def make_ble_send(board_mac: str | None, address: str | None, scan_timeout: float):
    def send(image: bytes, version: str) -> None:
        from labflash import idf_ble_ota as ble

        async def run():
            dev = await ble.find_device(address=address, board_mac=board_mac, timeout=scan_timeout)
            print(f"  BLE: found {dev.name or '?'} at {dev.address}", flush=True)
            return await ble.upload(image, dev.address,
                                    on_progress=lambda d, t: print(f"  BLE: sector {d}/{t}", flush=True))
        try:
            asyncio.run(run())
        except ble.BleOtaError as err:
            raise UpdateError(f"BLE transfer failed: {err}") from err
    return send


def run_update(args) -> int:
    try:
        image = Path(args.image).read_bytes()
    except OSError as err:
        print(f"ERROR: cannot read the image: {err}", file=sys.stderr)
        return 1
    mac = args.board_mac or rig_mac(args.rig, args.board)
    expected_uid = mac.replace(":", "").upper() if mac else None

    workdir_cm = tempfile.TemporaryDirectory(prefix="labflash-ota-")
    server = None
    try:
        https_fn = None
        board = None
        keys = Path(args.keys) if args.keys else DEFAULT_KEYS
        if args.transport == "wifi" or args.board_ip:
            if not args.board_ip:
                print("ERROR: --board-ip is required for the wifi transport", file=sys.stderr)
                return 1
            from labflash.idf_wifi_ota import OtaServer, WifiBoard
            board = WifiBoard(args.board_ip, read_token(args.env_file, args.token), args.ca_cert or keys / "ca.pem")
            https_fn = https_snapshot_fn(board)

        if args.no_labid:
            if https_fn is None:
                print("ERROR: --no-labid needs --board-ip (the HTTPS /version is then the only reader)", file=sys.stderr)
                return 1
            snapshot_fn, https_fn, expected_uid = https_fn, None, None
            print("note: --no-labid: identity is NOT verified (HTTPS carries no uid)", file=sys.stderr)
        else:
            port = args.labid_port
            if not port:
                from labflash.core import BoardResolutionError, resolve_board
                try:
                    port = resolve_board(args.board)
                except BoardResolutionError as err:
                    print(f"ERROR: {err} (pass --labid-port COMx, or --no-labid)", file=sys.stderr)
                    return 1
            snapshot_fn = labid_snapshot_fn(port)

        if args.transport == "wifi":
            server = OtaServer(workdir_cm.name, args.http_port, args.server_cert or keys / "server_cert.pem",
                               args.server_key or keys / "server_key.pem").start()
            host_ip = args.host_ip or guess_host_ip(args.board_ip)
            send_fn = make_wifi_send(board, server, host_ip, Path(workdir_cm.name))
        else:
            send_fn = make_ble_send(mac, args.address, args.scan_timeout)

        print(f"Updating {args.board} over {args.transport}: {args.image} ({len(image)} bytes)", flush=True)
        try:
            result = update_idf(image, args.transport, snapshot_fn=snapshot_fn, send_fn=send_fn,
                                expected_uid=expected_uid, https_snapshot_fn=https_fn, timeout_s=args.timeout)
        except UpdateError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 1
        print(f"image version {result.version}; before: app={result.pre.app} slot={result.pre.slot}; "
              f"after: app={result.post.app if result.post else '?'} slot={result.post.slot if result.post else '?'}")
        for c in result.checks:
            print(f"[{'PASS' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
        print("UPDATE OK" if result.ok else "UPDATE FAILED")
        return 0 if result.ok else 1
    finally:
        if server is not None:
            server.stop()
        workdir_cm.cleanup()
