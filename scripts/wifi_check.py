#!/usr/bin/env python3
r"""BL-024 live acceptance check for WiFi & token provisioning on the ESP-IDF board.

Run NATIVELY on the host that owns the serial port (Windows, or the RPi4):

    python scripts\wifi_check.py COM14

Checks the BL-024 acceptance criteria:
  AC1: Board joins WiFi after reboot (receives IP via DHCP)
  AC2: No credentials in source or logs (zero occurrences of PSK/token)

Exit code 0 only if all checks pass.
"""
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "host"))
from labflash.identify import SerialLineTransport  # noqa: E402
from labflash.provision import load_credentials_from_env  # noqa: E402

BAUD = 115200
WIFI_CONNECT_TIMEOUT_S = 20.0
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

results = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def port_exists(port_name: str) -> bool:
    try:
        tr = SerialLineTransport(port_name, BAUD)
        tr.close()
        return True
    except Exception:
        return False


def open_for_reboot(port: str):
    if port_exists(port):
        print(f"--- {port} is connected. Please press RST on the board now ---", flush=True)
        while port_exists(port):
            time.sleep(0.1)
        print(f"--- board reset detected; waiting for {port} to reconnect ---", flush=True)
    else:
        print(f"--- waiting for {port} to connect ---", flush=True)

    while not port_exists(port):
        time.sleep(0.1)

    time.sleep(0.15)
    while True:
        try:
            tr = SerialLineTransport(port, BAUD)
            print(f"--- {port} connected, observing boot logs ---", flush=True)
            return tr
        except Exception:
            time.sleep(0.1)


def read_line(tr, deadline: float) -> str:
    buf = bytearray()
    while time.monotonic() < deadline:
        try:
            b = tr.read1()
        except Exception:
            break
        if not b:
            time.sleep(0.005)
            continue
        buf.extend(b)
        if b"\n" in b:
            return buf.decode(errors="replace").strip()
    return buf.decode(errors="replace").strip()


def check_wifi_join(tr, psk: str, token: str) -> tuple[bool, str, list[str]]:
    deadline = time.monotonic() + WIFI_CONNECT_TIMEOUT_S
    captured_logs: list[str] = []
    got_ip: str = ""

    while time.monotonic() < deadline:
        line = read_line(tr, deadline)
        if not line:
            continue
        captured_logs.append(line)
        print(f"  | {line}")

        if "WiFi connected: IP=" in line:
            parts = line.split("WiFi connected: IP=")
            got_ip = parts[1].split()[0] if len(parts) > 1 else "unknown"
            break
        if "WiFi unprovisioned" in line:
            break

    ac1_pass = bool(got_ip and got_ip != "0.0.0.0")
    record("AC1 Board joins WiFi after reboot", ac1_pass,
           f"assigned IP: {got_ip}" if ac1_pass else "timed out waiting for WiFi IP")

    # Check for secret leakage in captured logs
    leak_in_logs = False
    if psk and psk in "\n".join(captured_logs):
        leak_in_logs = True
    if token and token in "\n".join(captured_logs):
        leak_in_logs = True

    return ac1_pass, got_ip, captured_logs


def check_git_credentials(psk: str, token: str) -> bool:
    """Ensure no secret credentials exist anywhere in git tracked source files."""
    for secret_name, secret_val in [("PSK", psk), ("token", token)]:
        if not secret_val or len(secret_val) < 4:
            continue
        res = subprocess.run(
            ["git", "grep", "-F", secret_val],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip():
            record("AC2 No credentials in source", False,
                   f"secret {secret_name} found in tracked files: {res.stdout.strip()[:100]}")
            return False

    record("AC2 No credentials in source", True, "git grep confirms zero secrets in tracked repo files")
    return True


def main(port: str, env_file: str = "credentials.env") -> int:
    env_path = REPO_ROOT / env_file
    if not env_path.exists():
        print(f"Error: {env_path} not found. Please create credentials.env.", file=sys.stderr)
        return 1

    creds = load_credentials_from_env(env_path)
    psk = creds.get("psk", "")
    token = creds.get("token", "")

    print(f"=== BL-024 WiFi Acceptance Check on {port} ===")

    tr = open_for_reboot(port)
    try:
        ac1_ok, ip, logs = check_wifi_join(tr, psk, token)
    finally:
        tr.close()

    # AC2 checks
    log_leak = False
    if psk and psk in "\n".join(logs):
        log_leak = True
    if token and token in "\n".join(logs):
        log_leak = True

    record("AC2 No credentials in logs", not log_leak,
           "no PSK or token leaked to serial console" if not log_leak else "PSK or token found in serial logs!")

    src_ok = check_git_credentials(psk, token)

    all_pass = ac1_ok and (not log_leak) and src_ok
    print("ALL PASS" if all_pass else "FAILED")
    return 0 if all_pass else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: wifi_check.py COMx [credentials.env]")
    env_f = sys.argv[2] if len(sys.argv) > 2 else "credentials.env"
    sys.exit(main(sys.argv[1], env_f))
