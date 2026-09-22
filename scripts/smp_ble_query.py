#!/usr/bin/env python3
"""Query SMP image states over BLE and print JSON."""
import argparse
import asyncio
import json
import sys

from smpclient import SMPClient
from smpclient.requests.image_management import ImageStatesRead
from smpclient.transport.ble import SMPBLETransport


async def query(mac: str, timeout_s: float):
    transport = SMPBLETransport(winrt={"use_cached_services": False})
    client = SMPClient(transport, mac)
    try:
        await client.connect(connect_timeout_s=timeout_s)
        res = await client.request(ImageStatesRead())
        images = [
            {
                "slot": img.slot,
                "confirmed": bool(img.confirmed),
                "hash": img.hash.hex(),
                "ver": getattr(img, "version", "") or "",
                "active": bool(getattr(img, "active", False)),
            }
            for img in getattr(res, "images", [])
        ]
        print(json.dumps(images))
        return 0
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mac", help="BLE MAC address")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    return asyncio.run(query(args.mac, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
