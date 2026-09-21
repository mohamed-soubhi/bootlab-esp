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
    declared = int(resp.getheader("Content-Length"))
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
