#!/usr/bin/env python3
"""Send one LABID request and print the device's reply (and its parsed fields).

Self-contained (pyserial only) so it runs from a bare Windows Python. DTR/RTS are held
inactive before open so the open cannot reset the board (PLAN R14). The reply CRC is
verified (CRC-16/CCITT-FALSE, PLAN 7.3.1).

    python scripts\\labid_query.py COM14 VER?        # also: ID?  STATE?  HELLO
Exit code 0 only if a reply with a valid CRC arrived.
"""
import argparse
import sys
import time

import serial

BAUD = 115200
REPLY_TIMEOUT_S = 3.0
CRC_INIT = 0xFFFF
CRC_POLY = 0x1021


def crc16_ccitt_false(data: bytes) -> int:
    crc = CRC_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ CRC_POLY) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def parse_frame(line: str) -> tuple[str, dict[str, str], bool]:
    """'$LAB,TYPE,k=v,...*CRC' -> (type, fields, crc_ok)."""
    body, _, crc = line.strip().lstrip("$").rpartition("*")
    parts = body.split(",")
    fields = dict(p.split("=", 1) for p in parts[2:] if "=" in p)
    ok = len(crc) == 4 and int(crc, 16) == crc16_ccitt_false(body.encode())
    return (parts[1] if len(parts) > 1 else ""), fields, ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("request", nargs="?", default="VER?")
    args = ap.parse_args()

    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = args.port, BAUD, 0.2
    ser.dtr = False
    ser.rts = False
    ser.open()
    try:
        ser.reset_input_buffer()
        ser.write(f"$LAB,{args.request}\n".encode())
        deadline = time.monotonic() + REPLY_TIMEOUT_S
        while time.monotonic() < deadline:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if line.startswith("$LAB,") and not line.startswith(f"$LAB,{args.request}"):
                ftype, fields, ok = parse_frame(line)
                print(line)
                print(f"type={ftype} crc_ok={ok} fields={fields}")
                return 0 if ok else 1
    finally:
        ser.close()
    print(f"no reply to {args.request} within {REPLY_TIMEOUT_S:.0f} s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
