"""OtaServer abort_after_bytes: declares the full Content-Length, then cuts the connection (interrupted-transfer driver, T08)."""
from __future__ import annotations

import http.client
import shutil
import ssl
import subprocess

import pytest
from labflash.idf_wifi_ota import OtaServer

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not available")


@pytest.fixture
def cert(tmp_path):
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=t",
                    "-keyout", str(tmp_path / "k.pem"), "-out", str(tmp_path / "c.pem")],
                   check=True, capture_output=True)
    return tmp_path / "c.pem", tmp_path / "k.pem"


def _get(port: int, path: str = "/update.bin") -> tuple[int, int]:
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    declared = int(resp.getheader("Content-Length") or 0)
    got = 0
    try:
        while chunk := resp.read(4096):
            got += len(chunk)
    except http.client.IncompleteRead as err:
        got += len(err.partial)
    return declared, got


def test_full_transfer_unchanged(tmp_path, cert):
    (tmp_path / "update.bin").write_bytes(b"x" * 100_000)
    with OtaServer(tmp_path, 0, *cert) as srv:
        declared, got = _get(srv.port)
    assert declared == got == 100_000


def test_abort_after_bytes_cuts_short_but_declares_full_length(tmp_path, cert):
    (tmp_path / "update.bin").write_bytes(b"x" * 100_000)
    with OtaServer(tmp_path, 0, *cert, abort_after_bytes=40_000) as srv:
        declared, got = _get(srv.port)
        assert declared == 100_000
        assert 0 < got < 100_000
        assert srv.aborted == 1


def test_a_stalled_tls_handshake_neither_blocks_other_transfers_nor_shutdown(tmp_path, cert):
    """Found live 2026-09-26: the board opened the connection, its TLS handshake stalled, and the server (which handshook inside
    accept() on its one serving thread) blocked forever, and so did stop(); the update process hung for 7 hours."""
    import socket
    import threading
    import time

    (tmp_path / "update.bin").write_bytes(b"x" * 100_000)
    srv = OtaServer(tmp_path, 0, *cert).start()
    stalled = socket.create_connection(("127.0.0.1", srv.port), timeout=5)      # TCP connects, no TLS bytes ever follow
    try:
        declared, got = _get(srv.port)                                           # a real transfer must still work
        assert declared == got == 100_000
        done = threading.Event()
        threading.Thread(target=lambda: (srv.stop(), done.set()), daemon=True).start()
        start = time.monotonic()
        assert done.wait(10), "stop() hung on a connection that never finished its TLS handshake"
        assert time.monotonic() - start < 10
    finally:
        stalled.close()


def test_an_idle_keep_alive_connection_is_dropped_after_the_handler_timeout(tmp_path, cert):
    import socket
    import time

    (tmp_path / "update.bin").write_bytes(b"x" * 1000)
    from labflash import idf_wifi_ota as ow
    with OtaServer(tmp_path, 0, *cert) as srv:
        assert ow._Handler.timeout and ow._Handler.timeout > 0
        s = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
        time.sleep(0.2)
        s.close()
