"""Inspect GATT services of the Zephyr board over BLE."""
import asyncio
import sys
import bleak

ZEPHYR_BLE_NAME = "lab-esp-zephyr"
SMP_SVC_UUID = "8d53dc1d-1db7-4cd3-868b-8a527460aa84"
SMP_CHR_UUID = "da2e7828-fbce-4e01-ae9e-261174997c48"


async def main():
    print(f"Scanning for BLE device '{ZEPHYR_BLE_NAME}'...")
    device = await bleak.BleakScanner.find_device_by_name(ZEPHYR_BLE_NAME, timeout=10.0)
    if not device:
        print(f"ERROR: Could not find BLE device '{ZEPHYR_BLE_NAME}'")
        return 1

    print(f"Found {device.name} at {device.address}. Connecting...")
    async with bleak.BleakClient(device, winrt={"use_cached_services": False}) as client:
        print(f"Connected: {client.is_connected}")
        found_smp = False
        for svc in client.services:
            print(f"Service: {svc.uuid} ({svc.description})")
            for char in svc.characteristics:
                print(f"  Characteristic: {char.uuid} (props: {char.properties})")
                if char.uuid.lower() == SMP_CHR_UUID:
                    found_smp = True
        if found_smp:
            print("[PASS] MCUboot SMP service and characteristic verified!")
            return 0
        else:
            print("[FAIL] SMP service not found in GATT database")
            return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
