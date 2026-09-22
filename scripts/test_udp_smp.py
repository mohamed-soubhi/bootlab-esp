#!/usr/bin/env python3
"""Test SMP operations over UDP on port 1337."""
import asyncio
import sys

from smpclient import SMPClient
from smpclient.requests.image_management import ImageStatesRead
from smpclient.requests.os_management import EchoWrite
from smpclient.transport.udp import SMPUDPTransport

DEFAULT_IP = "192.168.1.153"

async def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IP
    print(f"Connecting to {ip}:1337 via SMPUDPTransport...")
    transport = SMPUDPTransport(mtu=1500)
    client = SMPClient(transport, ip)

    try:
        await client.connect(connect_timeout_s=5.0)
        print("Connected via UDP SMP!")

        echo_resp = await client.request(EchoWrite(d="hello from UDP SMP!"))
        print(f"Echo response: {echo_resp}")

        img_resp = await client.request(ImageStatesRead())
        print(f"Image states response: {img_resp.images}")

    except Exception as e:
        print(f"ERROR during UDP SMP: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
