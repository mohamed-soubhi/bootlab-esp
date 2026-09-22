#!/usr/bin/env python3
"""Probe subnet for Zephyr MCUmgr SMP on UDP port 1337."""
import socket
import time

from smpclient.requests.os_management import EchoWrite


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.05)
    req = EchoWrite(d="ping").BYTES

    print("Probing 192.168.1.1 to 192.168.1.254 on UDP port 1337...")
    for i in range(1, 255):
        ip = f"192.168.1.{i}"
        try:
            sock.sendto(req, (ip, 1337))
        except Exception:
            pass

    t0 = time.time()
    found = []
    while time.time() - t0 < 3.0:
        try:
            data, addr = sock.recvfrom(1024)
            print(f"DISCOVERED SMP UDP on {addr[0]}:{addr[1]}! (response: {len(data)} bytes)")
            found.append(addr[0])
        except (TimeoutError, ConnectionResetError):
            pass

    if not found:
        print("No UDP SMP response on port 1337 in subnet.")
        return 1
    return 0

if __name__ == "__main__":
    main()
