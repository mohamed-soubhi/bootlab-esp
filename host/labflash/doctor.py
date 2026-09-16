"""labflash doctor — environment check (BL-007 stub).

Reports:
  - 2 ESP USB devices (Espressif VID 303a over lsusb)
  - BT adapter presence
  - WiFi interface
Exits non-zero if any required item is missing.
No board writes — read-only host check.
"""
import subprocess
import sys
from pathlib import Path

REQUIRED_ESP_DEVICES = 2


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:
        return None


def check_esp_usb():
    """Count Espressif USB devices via lsusb (VID 303a)."""
    r = _run(["lsusb"])
    if r is None:
        return 0, "lsusb failed"
    # Match Espressif Devices (303a:xxxx) — any Espressif product counts.
    count = sum(1 for line in r.stdout.splitlines() if "303a" in line or "Espressif" in line)
    return count, ""


def check_bt():
    """BT adapter present."""
    r = _run(["hciconfig"])          # lists hci* controllers (if any)
    if r is not None and r.stdout.strip():
        return True
    r2 = _run(["bluetoothctl", "show"])
    return bool(r2 and "Controller" in r2.stdout)


def check_wifi():
    """WiFi interface present."""
    r = _run(["nmcli", "-t", "-f", "TYPE,DEVICE", "device"])
    if r and "wifi" in r.stdout.lower():
        return True
    r2 = _run(["ls", "/sys/class/net"])
    return bool(r2 and "wlan" in r2.stdout)


def main():
    esp_count, err = check_esp_usb()
    bt = check_bt()
    wifi = check_wifi()

    ok = True
    print("== labflash doctor ==")
    print(f"ESP USB devices : {esp_count}/2  {'OK' if esp_count >= REQUIRED_ESP_DEVICES else 'MISSING'}")
    if esp_count < REQUIRED_ESP_DEVICES:
        ok = False
    print(f"Bluetooth       : {'OK' if bt else 'MISSING'}")
    if not bt:
        ok = False
    print(f"WiFi            : {'OK' if wifi else 'MISSING'}")
    if not wifi:
        ok = False
    print("Result: " + ("ALL OK" if ok else "MISSING ITEMS"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
