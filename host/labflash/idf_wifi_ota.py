"""labflash idf_wifi_ota — the two halves of a WiFi OTA pull (BL-043, PLAN 7.2).

  * OtaServer  : a local HTTPS server that serves firmware images to the board
                 (HTTP/1.1 with Content-Length, and a per-file counter of bytes it WROTE).
  * WifiBoard  : the board's HTTPS control API: GET /version and POST /ota (bearer token).

Lessons baked in (see PLAN R14/BL-026 evidence):
  - HTTP/1.1 + Content-Length: the board must not depend on how the connection is closed
    (a TCP RST once truncated a 1 MB download).
  - "bytes served" is what the server wrote, NOT what the board received; the caller's proof
    that an update worked is the board's own reported version, never this counter.
  - Do not poll /version densely while the board downloads: its TLS stack is busy and the polls
    starve it. WifiBoard.version() has a short timeout so a busy board costs little.
Standard library only.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION_TIMEOUT_S = 3.0
TRIGGER_TIMEOUT_S = 10.0    # soak evidence 2026-09-22: failures clustered at 5.2-5.6s against the old 5.0s
                            # budget (the board is slower to answer once a real download server is involved
                            # vs. an unreachable URL, which fails fast) -- widened with headroom, plus one retry.
TRIGGER_RETRIES = 2
TRIGGER_RETRY_PAUSE_S = 1.0
COPY_CHUNK = 16384


class _Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # keep the CLI output readable
        return

    def copyfile(self, source, outputfile):
        name = os.path.basename(self.path)
        limit = self.server.abort_after_bytes
        sent = 0
        try:
            while chunk := source.read(COPY_CHUNK):
                if limit is not None and sent + len(chunk) > limit:
                    chunk = chunk[:max(0, limit - sent)]
                outputfile.write(chunk)
                sent += len(chunk)
                self.server.served[name] = self.server.served.get(name, 0) + len(chunk)
                if limit is not None and sent >= limit:
                    # Full Content-Length was already declared: cut the connection so the client sees a short body.
                    self.server.aborted += 1
                    self.close_connection = True
                    outputfile.flush()
                    try:
                        self.connection.shutdown(2)
                    except OSError:
                        pass
                    return
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            pass


class OtaServer:
    """Serve `directory` over HTTPS. port=0 picks a free port (see .port). Use as a context manager."""

    def __init__(self, directory, port, certfile, keyfile, bind="0.0.0.0", abort_after_bytes=None):
        self.directory, self.bind, self._port = Path(directory), bind, port
        self.certfile, self.keyfile = str(certfile), str(keyfile)
        self.served: dict[str, int] = {}
        self.abort_after_bytes = abort_after_bytes   # T08 driver: send only this many bytes, then cut
        self._aborted_final = 0
        self._server = None
        self._thread = None

    @property
    def aborted(self) -> int:
        return self._server.aborted if self._server else self._aborted_final

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else self._port

    def start(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.certfile, self.keyfile)
        handler = functools.partial(_Handler, directory=str(self.directory))
        self._server = http.server.ThreadingHTTPServer((self.bind, self._port), handler)
        self._server.socket = ctx.wrap_socket(self._server.socket, server_side=True)
        self._server.served = self.served
        self._server.abort_after_bytes = self.abort_after_bytes
        self._server.aborted = 0
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server:
            self._aborted_final = self._server.aborted
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


class WifiBoard:
    """The board's HTTPS control API (PLAN 7.2). `ca_cert` is the pinned Lab Root CA."""

    def __init__(self, ip: str, token: str, ca_cert):
        self.base = f"https://{ip}"
        self._token = token
        self._ctx = ssl.create_default_context(cafile=str(ca_cert))
        self._ctx.check_hostname = False     # the firmware's cert is pinned to the CA, not to an IP
        # Python >= 3.13 defaults to VERIFY_X509_STRICT, which rejects the lab Root CA (it has no keyUsage
        # extension). The chain is still verified against the pinned CA (CERT_REQUIRED); only the strict
        # RFC 5280 profile checks are dropped.
        self._ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

    def version(self, timeout: float = VERSION_TIMEOUT_S) -> dict | None:
        """{'app','git','slot','confirmed'} or None if the board does not answer (rebooting, busy)."""
        try:
            with urllib.request.urlopen(f"{self.base}/version", context=self._ctx, timeout=timeout) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def trigger(self, url: str, version: str) -> int:
        """POST /ota {url, version}; returns the HTTP status (202 = accepted), or -1 if the board never
        answered after retrying (a timeout here is not necessarily the board refusing; see TRIGGER_TIMEOUT_S)."""
        req = urllib.request.Request(
            f"{self.base}/ota", data=json.dumps({"url": url, "version": version}).encode(),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"})
        for attempt in range(1, TRIGGER_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, context=self._ctx, timeout=TRIGGER_TIMEOUT_S) as r:
                    return r.status
            except urllib.error.HTTPError as err:
                return err.code
            except urllib.error.URLError:
                if attempt == TRIGGER_RETRIES:
                    return -1
                time.sleep(TRIGGER_RETRY_PAUSE_S)
        return -1
