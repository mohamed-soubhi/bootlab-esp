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
    if len(sys.argv) != 2:
        sys.exit("usage: labid_check.py COMx")
    sys.exit(main(sys.argv[1]))
