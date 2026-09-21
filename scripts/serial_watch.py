#!/usr/bin/env python3
"""Reconnecting serial monitor for the ESP32-S3 USB-Serial-JTAG console.

Waits for the port to appear, prints everything the board sends (including
the boot log after a replug), and reopens the port whenever it disappears.
DTR/RTS are forced inactive BEFORE opening so the open itself does not
toggle the reset/boot lines. Exit with Ctrl+C.

Usage (Windows PowerShell):  python serial_watch.py COM14
"""
import sys
import time

import serial

BAUD = 115200
RETRY_S = 0.3
READ_TIMEOUT_S = 0.2


def open_port(name):
    ser = serial.Serial()
    ser.port = name
    ser.baudrate = BAUD
    ser.timeout = READ_TIMEOUT_S
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def stream(ser):
    while True:
        data = ser.read(ser.in_waiting or 1)
        if data:
            sys.stdout.write(data.decode("utf-8", errors="replace"))
            sys.stdout.flush()


def main(name):
    waiting = False
    while True:
        try:
            ser = open_port(name)
        except (serial.SerialException, OSError):
            if not waiting:
                print(f"--- waiting for {name} ---", flush=True)
                waiting = True
            time.sleep(RETRY_S)
            continue
        waiting = False
        print(f"--- {name} connected ---", flush=True)
        try:
            stream(ser)
        except (serial.SerialException, OSError):
            print(f"\n--- {name} disconnected ---", flush=True)
        finally:
            ser.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: serial_watch.py COMx")
    try:
        main(sys.argv[1])
    except KeyboardInterrupt:
        print("\n--- exit ---")
