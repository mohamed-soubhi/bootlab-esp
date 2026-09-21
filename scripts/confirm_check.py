#!/usr/bin/env python3
r"""BL-023 live acceptance check for image self-test & confirmation on the ESP-IDF board.

Run NATIVELY on the host that owns the serial port (Windows, or the RPi4) --
not over usbipd, which resets the board on open (PLAN R14):

    python scripts\confirm_check.py COM14 v1
    python scripts\confirm_check.py COM14 no_confirm

Start it, then press RST on the board (or unplug/replug).
Checks the BL-023 acceptance criteria:
  AC1: VER? confirmed=1 after 5 s (for v1)
  AC2: no_confirm stays confirmed=0 (for no_confirm)

Exit code 0 only if all checks pass.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "host"))
from labflash.identify import SerialLineTransport, _read_frame  # noqa: E402

BAUD = 115200
ANNOUNCE_WAIT_S = 4.0
REPLY_TIMEOUT_S = 0.5
TARGET_UPTIME_MS = 5500
PRE_CONFIRM_MAX_UPTIME_MS = 4000

results = []


def record(name, ok, detail):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def port_exists(port_name: str) -> bool:
    try:
        tr = SerialLineTransport(port_name, BAUD)
        tr.close()
        return True
    except Exception:
        return False


def open_for_announce(port: str):
    if port_exists(port):
        print(f"--- {port} is connected. Please press RST on the board (or replug) now ---", flush=True)
        while port_exists(port):
            time.sleep(0.1)
        print(f"--- board reset detected; waiting for {port} to reconnect ---", flush=True)
    else:
        print(f"--- waiting for {port} to connect ---", flush=True)

    while not port_exists(port):
        time.sleep(0.1)

    time.sleep(0.15)  # allow Windows driver to settle after device arrival
    while True:
        try:
            tr = SerialLineTransport(port, BAUD)
            print(f"--- {port} connected, listening for boot ANNOUNCE ---", flush=True)
            return tr
        except Exception:
            time.sleep(0.1)


def roundtrip(tr, request: bytes):
    """Send raw bytes, return (elapsed_ms, frame_type, fields) or (None, None, {})."""
    t0 = time.perf_counter()
    tr.write(request)
    got = _read_frame(tr, time.monotonic() + REPLY_TIMEOUT_S)
    ms = (time.perf_counter() - t0) * 1000.0
    return (ms, got[0], got[1]) if got else (None, None, {})


def wait_announce(tr):
    deadline = time.monotonic() + ANNOUNCE_WAIT_S
    while time.monotonic() < deadline:
        got = _read_frame(tr, deadline)
        if got and got[0] == "ANNOUNCE":
            return time.monotonic(), got[1]
    return None, {}


def check_confirmation(tr, expected_variant: str):
    # 1. Catch boot ANNOUNCE
    t_seen, announce_fields = wait_announce(tr)
    if t_seen is not None:
        print(f"--- ANNOUNCE received: board={announce_fields.get('board')} uid={announce_fields.get('uid')} ---")
    else:
        print("--- warning: boot ANNOUNCE missed, querying directly ---")

    # 2. Check early state (< 4s uptime)
    ms, ftype, st = roundtrip(tr, b"$LAB,STATE?\n")
    if ftype != "STATE":
        record("Early STATE?", False, f"expected STATE, got {ftype}")
        return

    uptime_ms = int(st.get("uptime_ms", 999999))
    if uptime_ms > PRE_CONFIRM_MAX_UPTIME_MS:
        record("Early window check", False,
               f"board uptime is already {uptime_ms} ms (> {PRE_CONFIRM_MAX_UPTIME_MS} ms); replug/reset board faster")
        return

    ms, ftype, ver = roundtrip(tr, b"$LAB,VER?\n")
    if ftype != "VER":
        record("Early VER?", False, f"expected VER, got {ftype}")
        return

    variant = ver.get("variant", "")
    confirmed = ver.get("confirmed", "")
    variant_ok = (variant == expected_variant)
    early_conf_ok = (confirmed == "0")

    record(f"Early variant check ({expected_variant})", variant_ok,
           f"got variant={variant} (expected {expected_variant})")
    record("Early unconfirmed check (t < 4 s)", early_conf_ok,
           f"got confirmed={confirmed} (expected 0) at uptime {uptime_ms} ms")

    # 3. Wait until uptime >= TARGET_UPTIME_MS (5.5 s)
    print(f"--- waiting for uptime >= {TARGET_UPTIME_MS} ms (currently {uptime_ms} ms) ---", flush=True)
    while uptime_ms < TARGET_UPTIME_MS:
        time.sleep(0.5)
        ms, ftype, st = roundtrip(tr, b"$LAB,STATE?\n")
        if ftype == "STATE":
            uptime_ms = int(st.get("uptime_ms", 0))

    toggles = st.get("toggles", "unknown")
    ms, ftype, ver = roundtrip(tr, b"$LAB,VER?\n")
    if ftype != "VER":
        record("Post-5s VER?", False, f"expected VER, got {ftype}")
        return

    confirmed_post = ver.get("confirmed", "")

    if expected_variant == "no_confirm":
        # AC2: no_confirm stays confirmed=0
        ac2_pass = (confirmed_post == "0")
        record("AC2 no_confirm stays confirmed=0", ac2_pass,
               f"confirmed={confirmed_post} at uptime {uptime_ms} ms, toggles={toggles}")
    else:
        # AC1: VER? confirmed=1 after 5 s
        ac1_pass = (confirmed_post == "1")
        record("AC1 VER? confirmed=1 after 5 s", ac1_pass,
               f"confirmed={confirmed_post} at uptime {uptime_ms} ms, toggles={toggles}")


def main(port: str, expected_variant: str = "v1"):
    print(f"=== BL-023 Confirmation Check for '{expected_variant}' on {port} ===")
    tr = open_for_announce(port)
    try:
        check_confirmation(tr, expected_variant)
    finally:
        tr.close()

    all_ok = len(results) > 0 and all(results)
    print("ALL PASS" if all_ok else "FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: confirm_check.py COMx [v1|no_confirm]")
    var = sys.argv[2] if len(sys.argv) > 2 else "v1"
    sys.exit(main(sys.argv[1], var))
