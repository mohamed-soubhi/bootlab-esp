#!/usr/bin/env python3
"""Measure the LED blink rate over LABID (self-reported toggle counter).

Two `$LAB,STATE?` queries, --seconds apart; toggles/s / 2 = Hz. Self-contained
(pyserial only) so it runs from a bare Windows Python. DTR/RTS are held inactive
before open so the open cannot reset the board (PLAN R14).

    python scripts\\rate_check.py COM14 --expect-hz 4

Exit code 0 if the measured rate is within --tolerance of --expect-hz.
"""
import argparse
import re
import sys
import time

import serial

BAUD = 115200
REPLY_TIMEOUT_S = 2.0
STATE_RE = re.compile(r"toggles=(\d+)")


def query_toggles(ser: serial.Serial) -> tuple[float, int]:
    """Send STATE?, return (monotonic time of reply, toggles)."""
    ser.reset_input_buffer()
    ser.write(b"$LAB,STATE?\n")
    deadline = time.monotonic() + REPLY_TIMEOUT_S
    while time.monotonic() < deadline:
        line = ser.readline().decode("utf-8", errors="replace")
        if line.startswith("$LAB,STATE"):
            m = STATE_RE.search(line)
            if m:
                return time.monotonic(), int(m.group(1))
    raise SystemExit("no STATE reply within %.0f s" % REPLY_TIMEOUT_S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--expect-hz", type=float, required=True)
    ap.add_argument("--tolerance", type=float, default=0.15, help="fraction, default 15%%")
    args = ap.parse_args()

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, BAUD, 0.2
    ser.dtr = False
    ser.rts = False
    ser.open()
    try:
        t0, n0 = query_toggles(ser)
        time.sleep(args.seconds)
        t1, n1 = query_toggles(ser)
    finally:
        ser.close()
    hz = (n1 - n0) / (t1 - t0) / 2.0
    ok = abs(hz - args.expect_hz) <= args.expect_hz * args.tolerance
    print(f"[{'PASS' if ok else 'FAIL'}] toggles {n0} -> {n1} in {t1 - t0:.2f} s = {hz:.2f} Hz "
          f"(expected {args.expect_hz} Hz +/-{args.tolerance * 100:.0f}%)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
