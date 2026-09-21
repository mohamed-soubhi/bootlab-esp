#!/usr/bin/env python3
"""BL-026 live acceptance check: IDF WiFi OTA pull (esp_https_ota).

  AC1  v1 -> v2 over WiFi: version flips, slot flips, confirmed=true after the
       health check (the 4 Hz blink is checked separately over LABID).
  AC2  bad_sig images are refused and the running image keeps running.

Serves the OTA images itself over HTTPS (signed by the Lab Root CA, pinned in
the firmware). The board must be able to reach --host-ip:--port; from WSL2
that needs scripts/tcp_forwarder.py running on the Windows host.

  python3 scripts/ota_check.py --ip 192.168.1.152 --host-ip 192.168.1.134 \
      --stage <dir with v1.bin v2.bin bad_sig_tamper.bin bad_sig_key.bin>

A refusal only counts if the board really downloaded the whole image first, so
the server records bytes served per file.
"""
import argparse
import http.server
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
POLL_S = 0.5
OTA_TIMEOUT_S = 150.0
CONFIRM_TIMEOUT_S = 20.0
REFUSE_WINDOW_S = 60.0
REBOOT_POLLS = 4            # consecutive failed polls (~2 s) that mean "rebooted"
BAD_IMAGES = ("bad_sig_tamper.bin", "bad_sig_key.bin")
results: list[bool] = []
served: dict[str, int] = {}


def record(name: str, ok: bool, detail: str) -> bool:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return ok


def load_token() -> str | None:
    path = os.path.join(ROOT, "credentials.env")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(("OTA_TOKEN=", "LAB_TOKEN=")):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # keep output readable
        return

    def copyfile(self, source, outputfile) -> None:
        name = os.path.basename(self.path)
        try:
            while chunk := source.read(16384):
                outputfile.write(chunk)
                served[name] = served.get(name, 0) + len(chunk)
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            pass


def start_server(stage: str, port: int) -> http.server.ThreadingHTTPServer:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(os.path.join(ROOT, "keys", "server_cert.pem"),
                        os.path.join(ROOT, "keys", "server_key.pem"))
    handler = lambda *a, **k: Handler(*a, directory=stage, **k)  # noqa: E731
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Board:
    def __init__(self, ip: str, token: str, ca: str) -> None:
        self.base = f"https://{ip}"
        self.token = token
        self.ctx = ssl.create_default_context(cafile=ca)
        self.ctx.check_hostname = False

    def version(self, timeout: float = 2.0) -> dict | None:
        try:
            with urllib.request.urlopen(f"{self.base}/version", context=self.ctx, timeout=timeout) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def ota(self, url: str, version: str) -> int:
        req = urllib.request.Request(
            f"{self.base}/ota", data=json.dumps({"url": url, "version": version}).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as err:
            return err.code

    def wait_for(self, pred, timeout: float) -> dict | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            v = self.version()
            if v is not None and pred(v):
                return v
            time.sleep(POLL_S)
        return None


def check_upgrade(b: Board, base_url: str, want_app: str) -> None:
    pre = b.version()
    if not pre:
        record("AC1 precondition", False, "board unreachable")
        return
    print(f"before: {pre}", flush=True)
    status = b.ota(f"{base_url}/v2.bin", want_app)
    if not record("AC1 POST /ota accepted", status == 202, f"HTTP {status}"):
        return
    post = b.wait_for(lambda v: v["app"] == want_app, OTA_TIMEOUT_S)
    record("AC1 board runs v2", post is not None, f"after: {post}")
    if not post:
        return
    record("AC1 slot flipped", post["slot"] != pre["slot"], f"slot {pre['slot']} -> {post['slot']}")
    done = b.wait_for(lambda v: v["confirmed"] is True, CONFIRM_TIMEOUT_S)
    record("AC1 confirmed after health check", done is not None, f"{done}")


def check_refused(b: Board, base_url: str, name: str, size: int) -> None:
    pre = b.version()
    if not pre:
        record(f"AC2 {name} precondition", False, "board unreachable")
        return
    served.pop(name, None)
    status = b.ota(f"{base_url}/{name}", "9.9.9")
    if not record(f"AC2 {name} POST accepted", status == 202, f"HTTP {status}"):
        return
    end, bad_polls, worst = time.monotonic() + REFUSE_WINDOW_S, 0, 0
    while time.monotonic() < end:
        bad_polls = 0 if b.version(1.0) else bad_polls + 1
        worst = max(worst, bad_polls)
        time.sleep(POLL_S)
    post = b.version()
    fetched = served.get(name, 0)
    record(f"AC2 {name} fully downloaded (refusal is not a network error)", fetched >= size,
           f"{fetched}/{size} bytes served")
    same = post is not None and (post["app"], post["slot"], post["confirmed"]) == \
        (pre["app"], pre["slot"], pre["confirmed"])
    record(f"AC2 {name} refused, running image unchanged", same, f"before {pre} after {post}")
    record(f"AC2 {name} board did not reboot", worst < REBOOT_POLLS, f"max {worst} consecutive failed polls")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", required=True, help="board IP")
    ap.add_argument("--host-ip", required=True, help="IP the board uses to reach this server")
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--stage", required=True, help="dir holding v1.bin v2.bin and the bad_sig images")
    ap.add_argument("--ca-cert", default=os.path.join(ROOT, "keys", "ca.pem"))
    ap.add_argument("--token", default=None)
    ap.add_argument("--want-app", default="2.0.0")
    ap.add_argument("--no-restore", action="store_true", help="leave the board on v2")
    args = ap.parse_args()
    token = args.token or load_token()
    if not token:
        sys.exit("no token: pass --token or set OTA_TOKEN in credentials.env")

    start_server(args.stage, args.port)
    base_url = f"https://{args.host_ip}:{args.port}"
    board = Board(args.ip, token, args.ca_cert)
    check_upgrade(board, base_url, args.want_app)
    for name in BAD_IMAGES:
        check_refused(board, base_url, name, os.path.getsize(os.path.join(args.stage, name)))
    if not args.no_restore:
        status = board.ota(f"{base_url}/v1.bin", "1.0.0")
        back = board.wait_for(lambda v: v["app"] == "1.0.0", OTA_TIMEOUT_S) if status == 202 else None
        record("restore v1", back is not None, f"HTTP {status}, now {back}")
    print("ALL PASS" if all(results) else "FAILED", flush=True)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
