#!/usr/bin/env python3
"""
scripts/https_check.py — BL-025 Acceptance Criteria Checker.

Tests the ESP-IDF HTTPS control server:
  AC1: GET /version matches LABID VER.app
  AC2: Wrong token -> 401 (and missing token -> 401; valid token -> 202)

Usage:
  python scripts/https_check.py [--ip <IP>] [--port 443] [--ca-cert keys/ca.pem] [--token <token>] [--com <COM_PORT>]
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

try:
    import serial  # optional for LABID serial check
except ImportError:
    serial = None


def load_env_credentials():
    """Load token from credentials.env if present."""
    creds_file = os.path.join(os.path.dirname(__file__), "..", "credentials.env")
    token = None
    if os.path.exists(creds_file):
        with open(creds_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OTA_TOKEN=") or line.startswith("LAB_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
    return token


def query_labid_ver(port):
    """Query LABID VER? over serial port if specified."""
    if not serial:
        return None
    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = 115200
        ser.timeout = 1.0
        ser.dtr = False
        ser.rts = False
        ser.open()
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.write(b"$LAB,VER?\n")
        ser.flush()

        deadline = time.time() + 2.0
        while time.time() < deadline:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if line.startswith("$LAB,VER"):
                # Extract fields
                fields = {}
                parts = line.split("*")[0].split(",")
                for p in parts[2:]:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        fields[k] = v
                ser.close()
                return fields
        ser.close()
    except Exception as e:
        print(f"[WARN] Serial query failed: {e}")
    return None


def make_ssl_context(ca_cert_path):
    """Create SSL context with custom CA certificate pinned."""
    ctx = ssl.create_default_context(cafile=ca_cert_path)
    # Allow connection to IP directly while validating certificate against CA
    ctx.check_hostname = False
    return ctx


def http_get(url, ctx):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, context=ctx, timeout=5.0) as resp:
        return resp.status, resp.read().decode("utf-8")


def http_post(url, ctx, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method="POST")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if body and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5.0) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="BL-025 HTTPS Control Server Checker")
    parser.add_argument("--ip", default="192.168.1.152", help="Device IP address")
    parser.add_argument("--port", type=int, default=443, help="HTTPS port (default 443)")
    parser.add_argument("--ca-cert", default=None, help="Path to Lab CA certificate (keys/ca.pem)")
    parser.add_argument("--token", default=None, help="Bearer token (default: from credentials.env)")
    parser.add_argument("--com", default=None, help="Serial port (e.g. COM14 or /dev/lab-esp-idf)")
    args = parser.parse_args()

    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ca_cert = args.ca_cert or os.path.join(repo_dir, "keys", "ca.pem")
    token = args.token or load_env_credentials()

    if not os.path.exists(ca_cert):
        print(f"[FAIL] CA certificate not found: {ca_cert}")
        sys.exit(1)

    print(f"=== BL-025 HTTPS Checker for https://{args.ip}:{args.port} ===")
    print(f"CA Cert: {ca_cert}")
    print(f"Token:   {'*' * len(token) if token else '(none)'}")

    ctx = make_ssl_context(ca_cert)
    base_url = f"https://{args.ip}:{args.port}"

    # Query LABID VER? over serial if COM port provided
    labid_app_ver = None
    if args.com:
        print(f"--- Querying LABID over {args.com} ---")
        ver_fields = query_labid_ver(args.com)
        if ver_fields and "app" in ver_fields:
            labid_app_ver = ver_fields["app"]
            print(f"LABID VER.app = '{labid_app_ver}'")

    # 1. AC1: GET /version
    print(f"--- AC1: GET {base_url}/version ---")
    try:
        status, body = http_get(f"{base_url}/version", ctx)
        if status != 200:
            print(f"[FAIL] Expected status 200, got {status}")
            sys.exit(1)
        data = json.loads(body)
        print(f"Response: {data}")
        app_val = data.get("app")
        if not app_val:
            print("[FAIL] Missing 'app' field in /version response")
            sys.exit(1)
        if labid_app_ver and app_val != labid_app_ver:
            print(f"[FAIL] /version app '{app_val}' != LABID VER.app '{labid_app_ver}'")
            sys.exit(1)
        print(f"[PASS] AC1: GET /version returned app='{app_val}', git='{data.get('git')}', "
              f"slot={data.get('slot')}, confirmed={data.get('confirmed')}")
    except Exception as e:
        print(f"[FAIL] AC1 request error: {e}")
        sys.exit(1)

    # 2. AC2: Wrong token -> 401
    print(f"--- AC2: POST {base_url}/ota (Wrong / Missing Token) ---")

    # Test 2a: Missing token
    status, body = http_post(f"{base_url}/ota", ctx, body={"url": "https://lab.local/v2.bin", "version": "2.0.0"})
    if status == 401:
        print(f"[PASS] AC2 (missing token): got status 401 Unauthorized")
    else:
        print(f"[FAIL] AC2 (missing token): expected 401, got {status} ({body})")
        sys.exit(1)

    # Test 2b: Wrong token
    wrong_headers = {"Authorization": "Bearer wrong_token_deadbeef"}
    status, body = http_post(f"{base_url}/ota", ctx, headers=wrong_headers,
                             body={"url": "https://lab.local/v2.bin", "version": "2.0.0"})
    if status == 401:
        print(f"[PASS] AC2 (wrong token): got status 401 Unauthorized")
    else:
        print(f"[FAIL] AC2 (wrong token): expected 401, got {status} ({body})")
        sys.exit(1)

    # 3. Test Valid token -> 202 Accepted
    if token:
        print(f"--- POST {base_url}/ota (Valid Token) ---")
        valid_headers = {"Authorization": f"Bearer {token}"}
        status, body = http_post(f"{base_url}/ota", ctx, headers=valid_headers,
                                 body={"url": "https://lab.local/v2.bin", "version": "2.0.0"})
        if status == 202:
            print(f"[PASS] Valid token: got status 202 Accepted ({body.strip()})")
        else:
            print(f"[FAIL] Valid token: expected 202, got {status} ({body})")
            sys.exit(1)
    else:
        print("[WARN] Skipping valid token test: no token provided or found in credentials.env")

    print("\nALL AC PASS")


if __name__ == "__main__":
    main()
