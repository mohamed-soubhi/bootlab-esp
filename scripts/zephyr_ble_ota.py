"""Orchestrate Zephyr OTA over BLE using smpclient."""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from smpclient import SMPClient
from smpclient.transport.ble import SMPBLETransport
from smpclient.requests.image_management import (
    ImageStatesRead,
    ImageStatesWrite,
    ImageErase,
)
from smpclient.requests.os_management import ResetWrite

DEFAULT_BLE_MAC = "AC:A7:04:2C:3B:06"


async def async_main(args):
    bin_path = Path(args.binary)
    if not bin_path.exists():
        print(f"Error: binary not found at {bin_path}")
        return 1

    image_bytes = bin_path.read_bytes()
    print(f"Loaded {bin_path} ({len(image_bytes)} bytes)")

    print(f"Connecting to {args.mac} via SMP BLE (uncached)...")
    transport = SMPBLETransport(winrt={"use_cached_services": False})
    client = SMPClient(transport, args.mac)

    try:
        await client.connect(connect_timeout_s=args.timeout)
        print("Connected!")

        # 1. Read current state
        print("Querying current image state...")
        img_state = await client.request(ImageStatesRead())
        print(f"Current images: {img_state.images}")

        # If slot 1 has an image, erase it upfront with a dedicated timeout
        if any(getattr(img, "slot", None) == 1 for img in img_state.images):
            print("Slot 1 is occupied. Erasing slot 1...")
            try:
                erase_res = await client.request(ImageErase(slot=1), timeout_s=40.0)
                print(f"Erase result: {erase_res}")
            except Exception as e:
                print(
                    f"Note: BLE dropped during flash erase ({e}). Waiting 5s for erase completion..."
                )
                await asyncio.sleep(5.0)
                print("Reconnecting after flash erase...")
                await client.connect(connect_timeout_s=args.timeout)
                print("Reconnected!")

        # 2. Upload image
        print(f"Uploading {len(image_bytes)} bytes (slot {args.slot})...")
        t0 = time.time()
        last_pct = -1
        async for off in client.upload(
            image_bytes, slot=args.slot, first_timeout_s=60.0
        ):
            pct = int((off / len(image_bytes)) * 100)
            if pct != last_pct and pct % 10 == 0:
                print(f"  Upload progress: {off}/{len(image_bytes)} bytes ({pct}%)")
                last_pct = pct
        elapsed = time.time() - t0
        speed_kbps = (len(image_bytes) / 1024) / max(elapsed, 0.001)
        print(f"Upload complete in {elapsed:.1f}s ({speed_kbps:.1f} KB/s)")

        # 3. Query state after upload
        img_state = await client.request(ImageStatesRead())
        print(f"Images after upload: {img_state.images}")

        # Find the uploaded image (secondary slot)
        uploaded = None
        for img in img_state.images:
            if img.slot == 1:
                uploaded = img
                break

        if not uploaded:
            print("ERROR: Uploaded image not found in slot 1!")
            return 2

        print(f"Slot 1 image hash: {uploaded.hash.hex()}")

        # 4. Mark image state
        if args.confirm:
            print("Marking image as permanently confirmed...")
            res = await client.request(
                ImageStatesWrite(hash=uploaded.hash, confirm=True)
            )
            print(f"ImageStatesWrite response: {res}")
        else:
            print("Marking image for test boot (confirm=False)...")
            res = await client.request(
                ImageStatesWrite(hash=uploaded.hash, confirm=False)
            )
            print(f"ImageStatesWrite response: {res}")

        # 5. Reset device
        if args.reset:
            print("Issuing SMP Reset command...")
            try:
                await client.request(ResetWrite())
                print("Reset command sent successfully")
            except Exception as e:
                # Disconnection during reset is normal
                print(f"Reset issued (connection dropped as expected: {e})")

        print("[SUCCESS] BLE OTA workflow completed.")
        return 0

    except Exception as e:
        print(f"ERROR during BLE OTA: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Zephyr BLE OTA Update")
    parser.add_argument("binary", help="Path to signed binary (e.g. zephyr.signed.bin)")
    parser.add_argument(
        "--mac",
        default=DEFAULT_BLE_MAC,
        help=f"BLE MAC address (default: {DEFAULT_BLE_MAC})",
    )
    parser.add_argument("--slot", type=int, default=0, help="Image index (default: 0)")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Permanently confirm image instead of test boot",
    )
    parser.add_argument(
        "--reset", action="store_true", default=True, help="Reset device after upload"
    )
    parser.add_argument(
        "--timeout", type=float, default=15.0, help="Connection timeout in seconds"
    )
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    sys.exit(main())
