#!/usr/bin/env python3
"""BL-022 live acceptance check for LABID on the ESP-IDF board.

Run NATIVELY on the host that owns the serial port (Windows, or the RPi4) --
not over usbipd, which resets the board on open (PLAN R14):

    python scripts\\labid_check.py COM14

Start it, then unplug/replug the board so the boot-time ANNOUNCE is caught.
Checks the BL-022 acceptance criteria:
  AC1  ANNOUNCE <= 2 s after reset
  AC2  ID? / VER? / STATE? answered <= 100 ms
  AC3  garbage input -> ERR frame, and the board does not reset
Exit code 0 only if every check passes.
"""
import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "host"))
from labflash.identify import SerialLineTransport, _read_frame  # noqa: E402

BAUD = 115200
ANNOUNCE_WAIT_S = 4.0       # wait for a boot ANNOUNCE after the port opens
ANNOUNCE_MAX_MS = 2000
ROUNDTRIP_MAX_MS = 100
ROUNDTRIP_RUNS = 20
REPLY_TIMEOUT_S = 0.5
OVERSIZE_BYTES = 250
GARBAGE = [  # (raw request, expected ERR code)
    (b"$garbage\n", "syntax"),
    (b"$LAB,BOGUS\n", "unknown"),
    (b"$LAB,ID?*0000\n", "crc"),
    (b"$" + b"A" * OVERSIZE_BYTES + b"\n", "len"),
]
results = []


def record(name, ok, detail):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


import serial.tools.list_ports


RECONNECT_POLL_S = 0.05


def _try_open(port: str):
    try:
        return SerialLineTransport(port, BAUD)
    except Exception:
        return None


def open_for_announce(port: str):
    """Open the port and hold it; the boot's own ANNOUNCE frame is the reset signal.

    A software reset (esp_restart: OTA reboot, watchdog panic) does NOT drop the ESP32-S3's
    USB-Serial-JTAG, so 'wait for the port to disappear' never fires -- and polling by
    open/close raced the physical replug and kept the port busy. Any reset type works here:
    RST button, replug, OTA, watchdog. It only has to happen within --wait seconds.
    """
    announced = False
    while True:
        tr = _try_open(port)
        if tr is not None:
            print(f"--- {port} open; waiting up to {ANNOUNCE_WAIT_S:.0f} s for a boot ANNOUNCE "
                  "(reset the board: RST, replug, OTA, ...) ---", flush=True)
            return tr
        if not announced:
            print(f"--- waiting for {port} to connect ---", flush=True)
            announced = True
        time.sleep(RECONNECT_POLL_S)


def roundtrip(tr, request):
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


def check_announce(tr):
    t_seen, fields = wait_announce(tr)
    if t_seen is None:
        record("AC1 ANNOUNCE <= 2 s", False, "no ANNOUNCE (board already running? replug and rerun)")
        return
    ms, ftype, st = roundtrip(tr, b"$LAB,STATE?\n")
    if ftype != "STATE":
        record("AC1 ANNOUNCE <= 2 s", False, "STATE? unanswered after ANNOUNCE")
        return
    age_ms = (time.monotonic() - t_seen) * 1000.0
    at_ms = int(st["uptime_ms"]) - age_ms
    record("AC1 ANNOUNCE <= 2 s", at_ms <= ANNOUNCE_MAX_MS,
           f"announced at ~{at_ms:.0f} ms uptime, board={fields.get('board')} uid={fields.get('uid')}")


def check_latency(tr):
    for req, want in ((b"$LAB,ID?\n", "ID"), (b"$LAB,VER?\n", "VER"), (b"$LAB,STATE?\n", "STATE")):
        times, ok = [], True
        for _ in range(ROUNDTRIP_RUNS):
            ms, ftype, _ = roundtrip(tr, req)
            ok = ok and ftype == want and ms is not None
            times.append(ms if ms is not None else float("inf"))
        worst = max(times)
        record(f"AC2 {req[5:-1].decode()} <= {ROUNDTRIP_MAX_MS} ms", ok and worst <= ROUNDTRIP_MAX_MS,
               f"{ROUNDTRIP_RUNS} runs, median {sorted(times)[len(times) // 2]:.1f} ms, max {worst:.1f} ms")


def check_garbage(tr):
    _, _, before = roundtrip(tr, b"$LAB,STATE?\n")
    for raw, code in GARBAGE:
        _, ftype, f = roundtrip(tr, raw)
        record(f"AC3 garbage {raw[:14]!r} -> ERR {code}", ftype == "ERR" and f.get("code") == code,
               f"got {ftype} {f}")
    _, ftype, after = roundtrip(tr, b"$LAB,STATE?\n")
    alive = (ftype == "STATE" and int(after["uptime_ms"]) > int(before["uptime_ms"])
             and after["reset"] == before["reset"])
    record("AC3 no reset after garbage", alive,
           f"uptime {before.get('uptime_ms')} -> {after.get('uptime_ms')} ms, "
           f"reset={after.get('reset')}, rx_err={after.get('rx_err')}")


def main(port):
    tr = open_for_announce(port)
    try:
        check_announce(tr)
        check_latency(tr)
        check_garbage(tr)
    finally:
        tr.close()
    print("ALL PASS" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--wait", type=float, default=ANNOUNCE_WAIT_S,
                    help="seconds to wait for a boot ANNOUNCE (raise it when an OTA triggers the reset)")
    cli = ap.parse_args()
    ANNOUNCE_WAIT_S = cli.wait
    sys.exit(main(cli.port))
