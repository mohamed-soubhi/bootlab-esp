"""BL-043: `labflash update idf` — image validation, identity-before-send, verification,
and the local HTTPS image server. No board needed: transports and the LABID reader are injected."""
import shutil
import ssl
import subprocess
import urllib.request

import pytest

from labflash import update as up
from labflash.idf_wifi_ota import OtaServer

DESC_MAGIC = bytes.fromhex("3254cdab")          # 0xABCD5432, little-endian
SECTOR = 4096


def make_image(version="2.0.0", size=SECTOR * 3, project="bootlab_idf_blink"):
    """Synthetic ESP image: 24-byte header (magic 0xE9), 8-byte segment header, then esp_app_desc_t."""
    header = bytes([0xE9]) + bytes(23)
    seg_header = bytes(8)
    desc = (DESC_MAGIC + bytes(4) + bytes(8) + version.encode().ljust(32, b"\0")
            + project.encode().ljust(32, b"\0"))
    return (header + seg_header + desc).ljust(size, b"\xff")


def snap(app="1.0.0", slot=0, confirmed=True, uid="E072A1AA2390", source="labid"):
    return up.Snapshot(app=app, slot=slot, confirmed=confirmed, uid=uid, source=source)


# ---------------------------------------------------------------- image validation
def test_reads_the_app_version_from_the_image_descriptor():
    assert up.read_app_version(make_image("2.0.0")) == "2.0.0"
    assert up.read_app_version(make_image("1.0.0-noconfirm")) == "1.0.0-noconfirm"


def test_rejects_images_that_are_not_esp_app_images():
    with pytest.raises(up.UpdateError, match="not an ESP image"):
        up.check_image(b"\x00" * SECTOR, "wifi")
    bad = bytearray(make_image())
    bad[0x20:0x24] = b"\x00\x00\x00\x00"
    with pytest.raises(up.UpdateError, match="descriptor"):
        up.check_image(bytes(bad), "wifi")


def test_ble_needs_a_4096_aligned_image_wifi_does_not():
    odd = make_image(size=SECTOR * 2 + 100)
    assert up.check_image(odd, "wifi") == "2.0.0"
    with pytest.raises(up.UpdateError, match="4096"):
        up.check_image(odd, "ble")


# ---------------------------------------------------------------- verification rules
def names(checks):
    return {c.name: c.ok for c in checks}


def test_a_good_update_passes_every_check():
    ok = up.evaluate(snap(), snap(app="2.0.0", slot=1), "2.0.0", expected_uid="E072A1AA2390")
    assert all(c.ok for c in ok), [c for c in ok if not c.ok]


def test_wrong_version_or_no_slot_flip_fails():
    assert not names(up.evaluate(snap(), snap(app="1.0.0", slot=1), "2.0.0"))["running the new image"]
    assert not names(up.evaluate(snap(), snap(app="2.0.0", slot=0), "2.0.0"))["slot flipped"]


def test_unconfirmed_new_image_fails():
    assert not names(up.evaluate(snap(), snap(app="2.0.0", slot=1, confirmed=False), "2.0.0"))["confirmed"]


def test_uid_mismatch_fails_the_identity_check():
    got = names(up.evaluate(snap(), snap(app="2.0.0", slot=1, uid="AAAAAAAAAAAA"), "2.0.0", expected_uid="E072A1AA2390"))
    assert not got["identity (uid)"]


def test_labid_and_https_must_agree_on_the_version():
    https = snap(app="2.0.0", slot=1, source="https")
    assert names(up.evaluate(snap(), snap(app="2.0.0", slot=1), "2.0.0", https=https))["LABID == HTTPS version"]
    lying = snap(app="1.9.9", slot=1, source="https")
    assert not names(up.evaluate(snap(), snap(app="2.0.0", slot=1), "2.0.0", https=lying))["LABID == HTTPS version"]


# ---------------------------------------------------------------- orchestration with fakes
class Fake:
    """A board that reports `pre` until an image is sent, then `post`."""

    def __init__(self, pre, post, fail_send=False):
        self.state, self.post, self.sent, self.fail_send = pre, post, [], fail_send

    def snapshot(self):
        return self.state

    def send(self, image, version):
        if self.fail_send:
            raise up.UpdateError("transfer failed")
        self.sent.append((len(image), version))
        self.state = self.post


def run(fake, image=None, **kw):
    kw.setdefault("expected_uid", "E072A1AA2390")
    return up.update_idf(image or make_image("2.0.0"), "wifi", snapshot_fn=fake.snapshot, send_fn=fake.send,
                         sleep_fn=lambda s: None, timeout_s=5, poll_s=0.01, **kw)


def test_update_sends_once_and_reports_success():
    fake = Fake(snap(), snap(app="2.0.0", slot=1))
    result = run(fake)
    assert result.ok and fake.sent == [(SECTOR * 3, "2.0.0")]


def test_wrong_board_is_refused_before_anything_is_sent():
    fake = Fake(snap(uid="ACA7042C3B04"), snap(app="2.0.0", slot=1, uid="ACA7042C3B04"))
    with pytest.raises(up.UpdateError, match="identity"):
        run(fake)
    assert fake.sent == []


def test_transfer_failure_is_reported_not_swallowed():
    with pytest.raises(up.UpdateError, match="transfer failed"):
        run(Fake(snap(), snap(app="2.0.0", slot=1), fail_send=True))


def test_a_board_that_never_switches_fails_the_run():
    result = run(Fake(snap(), snap()))                  # sent, but still the old image
    assert not result.ok
    assert any(c.name == "running the new image" and not c.ok for c in result.checks)


# ---------------------------------------------------------------- local HTTPS image server
@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl CLI to make a test certificate")
def test_ota_server_serves_the_image_over_https_and_counts_bytes(tmp_path):
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                   check=True, capture_output=True)
    (tmp_path / "fw.bin").write_bytes(make_image("2.0.0"))
    with OtaServer(tmp_path, port=0, certfile=cert, keyfile=key) as srv:
        ctx = ssl.create_default_context(cafile=str(cert))
        with urllib.request.urlopen(f"https://127.0.0.1:{srv.port}/fw.bin", context=ctx, timeout=5) as r:
            body = r.read()
            assert r.headers["Content-Length"] == str(len(body))     # HTTP/1.1 + length: no reliance on close
        assert body == make_image("2.0.0")
        assert srv.served["fw.bin"] == len(body)
