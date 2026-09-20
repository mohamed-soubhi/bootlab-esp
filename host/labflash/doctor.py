"""labflash doctor — environment check (BL-007 stub).

Reports:
  - 2 ESP USB devices (Espressif VID 303a) — hard requirement everywhere,
    the actual thing this project cares about testing.
  - BT adapter presence — hard requirement where the host has BT capability
    at all; reported N/A (does not fail the run) on a host with no BT
    stack reachable (e.g. WSL2 with no BT-over-usbipd passthrough set up).
  - WiFi interface — same host-aware treatment as BT.
Exits non-zero only if a testable, required item is genuinely missing.
No board writes — read-only host check.
"""
import shutil
import subprocess
import sys

REQUIRED_ESP_DEVICES = 2


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:
        return None


def check_esp_usb():
    """Count Espressif USB devices (VID 0x303A) via pyserial.

    Does not depend on lsusb being installed — enumerates directly via
    the OS device list, which works the same on a stock Linux host, an
    RPi4, or a WSL2 image with boards attached through usbipd.
    """
    import serial.tools.list_ports as list_ports
    count = sum(1 for p in list_ports.comports() if p.vid == 0x303A)
    return count, ""


def check_bt():
    """BT adapter present. Returns (status, testable).

    testable=False means no BT stack is reachable on this host at all
    (neither hciconfig nor bluetoothctl exist) — that's a host-capability
    gap, not a failed check, so it must not count against the exit code.
    """
    if shutil.which("hciconfig") is None and shutil.which("bluetoothctl") is None:
        return False, False
    r = _run(["hciconfig"])
    if r is not None and r.stdout.strip():
        return True, True
    r2 = _run(["bluetoothctl", "show"])
    return bool(r2 and "Controller" in r2.stdout), True


def check_wifi():
    """WiFi interface present. Returns (status, testable).

    testable=False means this host has no wireless stack reachable at all
    (no nmcli, and no wlan* interface in /sys/class/net) — a host-capability
    gap (e.g. WSL2's virtualized network has no native WiFi iface), not a
    failed check.
    """
    import os
    has_nmcli = shutil.which("nmcli") is not None
    has_wlan_iface = False
    try:
        has_wlan_iface = any(name.startswith("wlan") for name in os.listdir("/sys/class/net"))
    except OSError:
        pass
    if not has_nmcli and not has_wlan_iface:
        return False, False
    if has_wlan_iface:
        return True, True
    r = _run(["nmcli", "-t", "-f", "TYPE,DEVICE", "device"])
    return bool(r and "wifi" in r.stdout.lower()), True


def _fmt(status, testable):
    if not testable:
        return "N/A  (not testable on this host)"
    return "OK" if status else "MISSING"


def main():
    esp_count, _ = check_esp_usb()
    bt_status, bt_testable = check_bt()
    wifi_status, wifi_testable = check_wifi()

    ok = True
    print("== labflash doctor ==")
    print(f"ESP USB devices : {esp_count}/2  {'OK' if esp_count >= REQUIRED_ESP_DEVICES else 'MISSING'}")
    if esp_count < REQUIRED_ESP_DEVICES:
        ok = False
    print(f"Bluetooth       : {_fmt(bt_status, bt_testable)}")
    if bt_testable and not bt_status:
        ok = False
    print(f"WiFi            : {_fmt(wifi_status, wifi_testable)}")
    if wifi_testable and not wifi_status:
        ok = False
    print("Result: " + ("ALL OK" if ok else "MISSING ITEMS"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
