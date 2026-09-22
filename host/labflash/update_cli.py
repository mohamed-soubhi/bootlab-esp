"""labflash update — command-line adapters for `labflash update idf|zephyr` (BL-043, BL-044).

Wires the real transports (BLE, WiFi/HTTPS, UDP/SMP) and the real board readers
(LABID over serial, HTTPS /version, SMP ImageStatesRead) into the pure orchestration
in labflash.update.

Where to run it: the serial port and the BLE radio must be used NATIVELY (Windows, or the RPi4).
Over usbipd/WSL2 the board resets when the port is opened (PLAN R14) and WSL2 has no Bluetooth.
From WSL2 the WiFi and UDP transports work with --no-labid, provided the board can reach this machine.
"""
from __future__ import annotations

import asyncio
import contextlib
import json as jsonlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from labflash.update import (
    Snapshot,
    UpdateError,
    check_zephyr_image,
    update_idf,
    update_zephyr,
)

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


def rig_board_info(rig_path: str | None, board: str) -> dict:
    try:
        from labflash.core import load_rig_config
        rig = load_rig_config(rig_path)
    except Exception:   # noqa: BLE001 - optional (no yaml / no file)
        return {}
    return rig.get("boards", {}).get(board, {}) or {}


def rig_mac(rig_path: str | None, board: str) -> str | None:
    return rig_board_info(rig_path, board).get("mac") or None


def rig_ble_mac(rig_path: str | None, board: str) -> str | None:
    return rig_board_info(rig_path, board).get("ble_mac") or None


def rig_ip(rig_path: str | None, board: str) -> str | None:
    return rig_board_info(rig_path, board).get("ip") or None


def rig_udp_port(rig_path: str | None, board: str) -> int | None:
    return rig_board_info(rig_path, board).get("udp_port") or None


def labid_snapshot_fn(port: str, transport_factory=None):
    """`transport_factory`, when given, replaces the default one-shot `SerialLineTransport(port)`
    (e.g. a `SharedConsolePort` kept open for the whole run so console.log captures continuously)."""
    def snap() -> Snapshot:
        from labflash.identify import SerialLineTransport, get_version, identify
        tr = transport_factory() if transport_factory else SerialLineTransport(port)
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
        if status == -1:
            raise UpdateError("the board never answered POST /ota (timed out after retrying)")
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


# ---------------------------------------------------------------- Zephyr SMP adapters
def make_zephyr_udp_send(target_ip: str, port: int = 1337, timeout_s: float = 20.0):
    def send(image: bytes, version: str, img_hash: str) -> None:
        from smpclient import SMPClient
        from smpclient.requests.image_management import (
            ImageErase,
            ImageStatesRead,
            ImageStatesWrite,
        )
        from smpclient.requests.os_management import ResetWrite
        from smpclient.transport.udp import SMPUDPTransport

        async def run():
            print(f"  UDP: connecting to {target_ip}:{port}...", flush=True)
            transport = SMPUDPTransport(mtu=1500)
            client = SMPClient(transport, target_ip)
            try:
                await client.connect(connect_timeout_s=timeout_s)
                img_state = await client.request(ImageStatesRead())
                if any(getattr(img, "slot", None) == 1 for img in getattr(img_state, "images", [])):
                    print("  UDP: slot 1 is occupied; erasing slot 1...", flush=True)
                    try:
                        await client.request(ImageErase(slot=1), timeout_s=40.0)
                    except Exception:  # noqa: BLE001
                        await asyncio.sleep(5.0)
                        await client.connect(connect_timeout_s=timeout_s)

                print(f"  UDP: uploading {len(image)} bytes...", flush=True)
                last_pct = -1
                async for off in client.upload(image, slot=0, first_timeout_s=60.0):
                    pct = int((off / len(image)) * 100)
                    if pct != last_pct and pct % 20 == 0:
                        print(f"  UDP: {off}/{len(image)} bytes ({pct}%)", flush=True)
                        last_pct = pct

                img_state = await client.request(ImageStatesRead())
                uploaded = next((img for img in getattr(img_state, "images", []) if getattr(img, "slot", None) == 1), None)
                if not uploaded:
                    raise UpdateError("uploaded image not found in slot 1")

                target_hash = getattr(uploaded, "hash", None) or bytes.fromhex(img_hash)
                await client.request(ImageStatesWrite(hash=target_hash, confirm=True))
                print("  UDP: marked permanent/confirmed; resetting device...", flush=True)
                with contextlib.suppress(Exception):
                    await client.request(ResetWrite())
            finally:
                with contextlib.suppress(Exception):
                    await client.disconnect()

        try:
            asyncio.run(run())
        except UpdateError:
            raise
        except Exception as err:
            raise UpdateError(f"UDP transfer failed: {err}") from err

    return send


def make_zephyr_ble_send(ble_address: str, timeout_s: float = 30.0):
    def send(image: bytes, version: str, img_hash: str) -> None:
        async def run_native():
            from smpclient import SMPClient
            from smpclient.requests.image_management import (
                ImageErase,
                ImageStatesRead,
                ImageStatesWrite,
            )
            from smpclient.requests.os_management import ResetWrite
            from smpclient.transport.ble import SMPBLETransport

            print(f"  BLE: connecting to {ble_address}...", flush=True)
            transport = SMPBLETransport(winrt={"use_cached_services": False})
            client = SMPClient(transport, ble_address)
            try:
                await client.connect(connect_timeout_s=timeout_s)
                img_state = await client.request(ImageStatesRead())
                if any(getattr(img, "slot", None) == 1 for img in getattr(img_state, "images", [])):
                    print("  BLE: slot 1 is occupied; erasing slot 1...", flush=True)
                    try:
                        await client.request(ImageErase(slot=1), timeout_s=40.0)
                    except Exception:  # noqa: BLE001
                        await asyncio.sleep(5.0)
                        await client.connect(connect_timeout_s=timeout_s)

                print(f"  BLE: uploading {len(image)} bytes...", flush=True)
                last_pct = -1
                async for off in client.upload(image, slot=0, first_timeout_s=60.0):
                    pct = int((off / len(image)) * 100)
                    if pct != last_pct and pct % 20 == 0:
                        print(f"  BLE: {off}/{len(image)} bytes ({pct}%)", flush=True)
                        last_pct = pct

                img_state = await client.request(ImageStatesRead())
                uploaded = next((img for img in getattr(img_state, "images", []) if getattr(img, "slot", None) == 1), None)
                if not uploaded:
                    raise UpdateError("uploaded image not found in slot 1")

                target_hash = getattr(uploaded, "hash", None) or bytes.fromhex(img_hash)
                await client.request(ImageStatesWrite(hash=target_hash, confirm=True))
                print("  BLE: marked permanent/confirmed; resetting device...", flush=True)
                with contextlib.suppress(Exception):
                    await client.request(ResetWrite())
            finally:
                with contextlib.suppress(Exception):
                    await client.disconnect()

        try:
            asyncio.run(run_native())
            return
        except UpdateError:
            raise
        except Exception as native_err:
            # If native BLE fails (e.g. WSL2 without BlueZ) and powershell.exe is available, delegate to Windows
            err_str = str(native_err).lower()
            if shutil.which("powershell.exe") and ("bluez" in err_str or "dbus" in err_str or "not found" in err_str):
                print(f"  BLE native: {native_err}; delegating to Windows host...", flush=True)
                win_stage = Path("/mnt/c/MSA/embedded-OS/bootlab-esp/ble_stage")
                if not win_stage.exists():
                    win_stage = Path(tempfile.gettempdir())
                temp_bin = win_stage / "temp_zephyr_ota.bin"
                temp_bin.write_bytes(image)
                win_path = "C:\\MSA\\embedded-OS\\bootlab-esp\\ble_stage\\temp_zephyr_ota.bin"
                cmd = f"python C:\\MSA\\embedded-OS\\bootlab-esp\\scripts\\zephyr_ble_ota.py {win_path} --mac {ble_address} --timeout {timeout_s}"
                proc = subprocess.run(["powershell.exe", "-Command", cmd], capture_output=True, text=True, check=False)
                if temp_bin.exists():
                    with contextlib.suppress(OSError):
                        temp_bin.unlink()
                if proc.returncode != 0:
                    raise UpdateError(f"BLE transfer via Windows failed: {proc.stderr or proc.stdout}")
                print(proc.stdout)
                return
            raise UpdateError(f"BLE transfer failed: {native_err}") from native_err

    return send


def make_zephyr_smp_snapshot(
    transport_type: str,
    target: str,
    port: int = 1337,
    timeout_s: float = 10.0,
    expected_hash: str | None = None,
    expected_version: str | None = None,
):
    def snap() -> Snapshot:
        from smpclient import SMPClient
        from smpclient.requests.image_management import ImageStatesRead

        async def run_udp():
            from smpclient.transport.udp import SMPUDPTransport
            transport = SMPUDPTransport(mtu=1500)
            client = SMPClient(transport, target)
            try:
                await client.connect(connect_timeout_s=timeout_s)
                return await client.request(ImageStatesRead())
            finally:
                with contextlib.suppress(Exception):
                    await client.disconnect()

        async def run_ble():
            from smpclient.transport.ble import SMPBLETransport
            transport = SMPBLETransport(winrt={"use_cached_services": False})
            client = SMPClient(transport, target)
            try:
                await client.connect(connect_timeout_s=timeout_s)
                return await client.request(ImageStatesRead())
            finally:
                with contextlib.suppress(Exception):
                    await client.disconnect()

        res = None
        if transport_type == "udp":
            try:
                res = asyncio.run(run_udp())
            except Exception as e:
                raise UpdateError(f"SMP UDP query failed: {e}") from e
        else:
            try:
                res = asyncio.run(run_ble())
            except Exception as native_err:
                err_str = str(native_err).lower()
                if shutil.which("powershell.exe") and ("bluez" in err_str or "dbus" in err_str or "not found" in err_str):
                    cmd = f"python C:\\MSA\\embedded-OS\\bootlab-esp\\scripts\\smp_ble_query.py {target} --timeout {timeout_s}"
                    proc = subprocess.run(["powershell.exe", "-Command", cmd], capture_output=True, text=True, check=False)
                    if proc.returncode == 0 and proc.stdout.strip():
                        try:
                            images_data = jsonlib.loads(proc.stdout.strip().splitlines()[-1])
                            active_data = next((img for img in images_data if img.get("slot") == 0), None)
                            if not active_data:
                                raise UpdateError("no active image in SMP list")
                            h = active_data.get("hash", "").lower()
                            v = active_data.get("ver", "")
                            app_str = expected_version if (expected_hash and h == expected_hash.lower() and expected_version) else (v if v and v != "0.0.0" else h)
                            return Snapshot(app=app_str, slot=active_data.get("slot", 0),
                                            confirmed=bool(active_data.get("confirmed", False)),
                                            uid=None, source="smp")
                        except Exception as parse_err:
                            raise UpdateError(f"failed to parse SMP query from Windows: {parse_err}") from parse_err
                    raise UpdateError(f"SMP BLE query via Windows failed: {proc.stderr}")
                raise UpdateError(f"SMP BLE query failed: {native_err}") from native_err

        images = getattr(res, "images", []) if res else []
        active = next((img for img in images if getattr(img, "active", False) or getattr(img, "slot", None) == 0), None)
        if not active:
            raise UpdateError("no active image found in SMP image list")
        h = getattr(active, "hash", b"").hex().lower()
        ver = getattr(active, "version", "")
        if expected_hash and h == expected_hash.lower() and expected_version:
            app_ver = expected_version
        elif ver and ver != "0.0.0":
            app_ver = ver
        else:
            app_ver = h
        return Snapshot(app=app_ver, slot=getattr(active, "slot", 0),
                        confirmed=bool(getattr(active, "confirmed", False)),
                        uid=None, source="smp")

    return snap


def run_update_zephyr(args, image: bytes) -> int:
    if args.transport not in ("ble", "udp"):
        print(f"ERROR: unsupported transport '{args.transport}' for Zephyr (must be 'ble' or 'udp')", file=sys.stderr)
        return 1

    mac = args.board_mac or rig_mac(args.rig, "zephyr")
    expected_uid = mac.replace(":", "").upper() if mac else None

    try:
        image_version, image_hash = check_zephyr_image(image, args.transport)
    except UpdateError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    if args.transport == "udp":
        target_ip = args.board_ip or rig_ip(args.rig, "zephyr")
        if not target_ip:
            print("ERROR: --board-ip or ip in rig.yaml is required for Zephyr UDP transport", file=sys.stderr)
            return 1
        udp_port = args.udp_port or rig_udp_port(args.rig, "zephyr") or 1337
        send_fn = make_zephyr_udp_send(target_ip, udp_port, timeout_s=args.timeout)
        smp_snapshot_fn = make_zephyr_smp_snapshot("udp", target_ip, udp_port, expected_hash=image_hash, expected_version=image_version)
    else:
        # BLE
        ble_mac = args.address or rig_ble_mac(args.rig, "zephyr")
        if not ble_mac:
            print("ERROR: --address or ble_mac in rig.yaml is required for Zephyr BLE transport", file=sys.stderr)
            return 1
        send_fn = make_zephyr_ble_send(ble_mac, timeout_s=args.timeout)
        smp_snapshot_fn = make_zephyr_smp_snapshot("ble", ble_mac, expected_hash=image_hash, expected_version=image_version)

    if args.no_labid:
        snapshot_fn = smp_snapshot_fn
        smp_fn = None
        expected_uid = None
        print("note: --no-labid: identity is NOT verified (SMP carries no uid)", file=sys.stderr)
    else:
        port = args.labid_port
        if not port:
            from labflash.core import BoardResolutionError, resolve_board
            try:
                port = resolve_board("zephyr")
            except BoardResolutionError as err:
                print(f"ERROR: {err} (pass --labid-port COMx, or --no-labid)", file=sys.stderr)
                return 1
        snapshot_fn = labid_snapshot_fn(port)
        smp_fn = smp_snapshot_fn

    print(f"Updating zephyr over {args.transport}: {args.image} ({len(image)} bytes, hash {image_hash[:8]}...)", flush=True)
    try:
        result = update_zephyr(
            image,
            args.transport,
            snapshot_fn=snapshot_fn,
            send_fn=send_fn,
            expected_uid=expected_uid,
            smp_snapshot_fn=smp_fn,
            timeout_s=args.timeout,
            confirm_timeout_s=args.confirm_timeout,
        )
    except UpdateError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"image version {result.version}; before: app={result.pre.app if result.pre else '?'} slot={result.pre.slot if result.pre else '?'}; "
          f"after: app={result.post.app if result.post else '?'} slot={result.post.slot if result.post else '?'}")
    for c in result.checks:
        print(f"[{'PASS' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
    print("UPDATE OK" if result.ok else "UPDATE FAILED")
    return 0 if result.ok else 1


def run_update_idf(args, image: bytes) -> int:
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
            send_fn = make_ble_send(mac, args.address, getattr(args, "scan_timeout", 5.0))

        print(f"Updating {args.board} over {args.transport}: {args.image} ({len(image)} bytes)", flush=True)
        try:
            result = update_idf(image, args.transport, snapshot_fn=snapshot_fn, send_fn=send_fn,
                                expected_uid=expected_uid, https_snapshot_fn=https_fn, timeout_s=args.timeout,
                                confirm_timeout_s=getattr(args, "confirm_timeout", 30.0))
        except UpdateError as err:
            if server is not None:
                print(f"host served: {server.served} (image was {len(image)} bytes)", file=sys.stderr)
            print(f"ERROR: {err}", file=sys.stderr)
            return 1
        if server is not None:
            print(f"host served: {server.served} (image was {len(image)} bytes)", flush=True)
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


def run_update(args) -> int:
    try:
        image = Path(args.image).read_bytes()
    except OSError as err:
        print(f"ERROR: cannot read the image: {err}", file=sys.stderr)
        return 1

    if args.board == "zephyr":
        return run_update_zephyr(args, image)
    elif args.board == "idf":
        return run_update_idf(args, image)
    else:
        print(f"ERROR: unsupported board '{args.board}'", file=sys.stderr)
        return 1
