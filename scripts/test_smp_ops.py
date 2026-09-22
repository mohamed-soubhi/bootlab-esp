"""Test SMP Echo and Image State over BLE on Windows."""
import asyncio
import sys
from smpclient import SMPClient
from smpclient.transport.ble import SMPBLETransport
from smpclient.requests.os_management import EchoWrite
from smpclient.requests.image_management import ImageStatesRead

BLE_ADDRESS = "AC:A7:04:2C:3B:06"


async def main():
    print(f"Connecting to {BLE_ADDRESS} via SMPBLETransport (uncached)...")
    transport = SMPBLETransport(winrt={"use_cached_services": False})
    client = SMPClient(transport, BLE_ADDRESS)

    try:
        await client.connect(connect_timeout_s=15.0)
        print("Connected! Sending EchoWrite...")
        
        echo_resp = await client.request(EchoWrite(d="hello from bootlab!"))
        print(f"Echo response: {echo_resp}")

        print("Sending ImageStatesRead...")
        img_resp = await client.request(ImageStatesRead())
        print(f"Image states response: {img_resp}")
        print(f"Images: {getattr(img_resp, 'images', None)}")

    except Exception as e:
        print(f"ERROR during SMP operation: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            await client.disconnect()
            print("Disconnected.")
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
