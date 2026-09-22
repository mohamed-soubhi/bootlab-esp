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


def test_wifi_board_version_and_trigger(tmp_path):
    from unittest.mock import MagicMock, patch

    from labflash.idf_wifi_ota import WifiBoard

    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("FAKE CA")

    with patch("ssl.create_default_context") as mock_ssl:
        mock_ctx = MagicMock()
        mock_ssl.return_value = mock_ctx
        wb = WifiBoard("192.168.1.152", token="test-token", ca_cert=ca_file)

        # Mock version success
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"app": "1.0.0", "slot": 0, "confirmed": true}'
        mock_resp.__enter__.return_value = mock_resp
        with patch("urllib.request.urlopen", return_value=mock_resp):
            v = wb.version(timeout=1.0)
            assert v == {"app": "1.0.0", "slot": 0, "confirmed": True}

        # Mock version error
        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            assert wb.version(timeout=1.0) is None

        # Mock trigger success
        mock_trigger_resp = MagicMock()
        mock_trigger_resp.status = 202
        mock_trigger_resp.__enter__.return_value = mock_trigger_resp
        with patch("urllib.request.urlopen", return_value=mock_trigger_resp):
            status = wb.trigger("https://192.168.1.134:8443/fw.bin", "2.0.0")
            assert status == 202

        # Mock trigger HTTPError
        http_err = urllib.error.HTTPError("url", 409, "Conflict", {}, None)  # type: ignore[arg-type]
        with patch("urllib.request.urlopen", side_effect=http_err):
            assert wb.trigger("https://192.168.1.134:8443/fw.bin", "2.0.0") == 409


# ---------------------------------------------------------------- Zephyr unit tests (BL-044)
def make_zephyr_image(version="2.0.0", size=1024, embedded_string=False):
    import struct
    parts = [int(p) for p in version.split(".")[:3]]
    hdr_size = 32
    img_size = size - hdr_size
    ver_maj, ver_min, ver_rev = (0, 0, 0) if embedded_string else (parts[0], parts[1], parts[2])
    hdr = (
        struct.pack("<IIHHI", up.MCUBOOT_IMAGE_MAGIC, 0, hdr_size, 0, img_size)
        + bytes(4)
        + struct.pack("<BBHI", ver_maj, ver_min, ver_rev, 0)
        + bytes(4)
    )
    body = version.encode() if embedded_string else b""
    return (hdr + body).ljust(size, b"\x00")


def test_read_zephyr_image_info_valid():
    img = make_zephyr_image("2.0.0")
    ver, h = up.read_zephyr_image_info(img)
    assert ver == "2.0.0"
    assert len(h) == 64


def test_read_zephyr_image_info_embedded_string():
    img = make_zephyr_image("2.0.0", embedded_string=True)
    ver, _ = up.read_zephyr_image_info(img)
    assert ver == "2.0.0"

    img_v1 = make_zephyr_image("1.0.0", embedded_string=True)
    ver1, _ = up.read_zephyr_image_info(img_v1)
    assert ver1 == "1.0.0"


def test_read_zephyr_image_info_invalid():
    with pytest.raises(up.UpdateError, match="too small"):
        up.read_zephyr_image_info(b"short")

    with pytest.raises(up.UpdateError, match="magic"):
        up.read_zephyr_image_info(b"\x00" * 64)


def test_check_zephyr_image_transports():
    img = make_zephyr_image("2.0.0")
    assert up.check_zephyr_image(img, "udp")[0] == "2.0.0"
    assert up.check_zephyr_image(img, "ble")[0] == "2.0.0"

    with pytest.raises(up.UpdateError, match="invalid transport"):
        up.check_zephyr_image(img, "wifi")


def test_evaluate_zephyr_all_pass():
    pre = snap("1.0.0", 0, True, "ACA7042C3B04")
    post = snap("2.0.0", 0, True, "ACA7042C3B04")
    smp = up.Snapshot("2.0.0", 0, True, None, "smp")
    checks = up.evaluate_zephyr(pre, post, "2.0.0", expected_uid="ACA7042C3B04", smp=smp, expected_hash="dummyhash")
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_evaluate_zephyr_failures():
    pre = snap("1.0.0", 0, True, "ACA7042C3B04")

    # 1. Post version wrong
    post_bad_ver = snap("1.0.0", 0, True, "ACA7042C3B04")
    res = names(up.evaluate_zephyr(pre, post_bad_ver, "2.0.0"))
    assert not res["running the new image"]

    # 2. Unconfirmed
    post_unconfirmed = snap("2.0.0", 0, False, "ACA7042C3B04")
    res = names(up.evaluate_zephyr(pre, post_unconfirmed, "2.0.0"))
    assert not res["confirmed"]

    # 3. UID mismatch
    post_bad_uid = snap("2.0.0", 0, True, "WRONGUID1234")
    res = names(up.evaluate_zephyr(pre, post_bad_uid, "2.0.0", expected_uid="ACA7042C3B04"))
    assert not res["identity (uid)"]

    # 4. SMP mismatch (slot or confirmed)
    post = snap("2.0.0", 0, True, "ACA7042C3B04")
    smp_unconfirmed = up.Snapshot("2.0.0", 0, False, None, "smp")
    res = names(up.evaluate_zephyr(pre, post, "2.0.0", smp=smp_unconfirmed))
    assert not res["SMP status == LABID status"]

    # 5. SMP hash mismatch
    smp_wrong_hash = up.Snapshot("wronghash123", 0, True, None, "smp")
    res = names(up.evaluate_zephyr(pre, post, "2.0.0", smp=smp_wrong_hash, expected_hash="expectedhash"))
    assert not res["SMP image matches"]


class ZephyrFake:
    def __init__(self, pre, post, smp=None, fail_send=False):
        self.state = pre
        self.post = post
        self.smp = smp
        self.fail_send = fail_send
        self.sent = []

    def snapshot(self):
        return self.state

    def smp_snapshot(self):
        return self.smp

    def send(self, image, version, img_hash):
        if self.fail_send:
            raise up.UpdateError("zephyr transfer failed")
        self.sent.append((len(image), version, img_hash))
        self.state = self.post


def test_update_zephyr_orchestration_success():
    fake = ZephyrFake(
        snap("1.0.0", 0, True, "ACA7042C3B04"),
        snap("2.0.0", 0, True, "ACA7042C3B04"),
        smp=up.Snapshot("2.0.0", 0, True, None, "smp"),
    )
    img = make_zephyr_image("2.0.0")
    res = up.update_zephyr(
        img,
        "udp",
        snapshot_fn=fake.snapshot,
        send_fn=fake.send,
        expected_uid="ACA7042C3B04",
        smp_snapshot_fn=fake.smp_snapshot,
        sleep_fn=lambda s: None,
        timeout_s=5,
        poll_s=0.01,
    )
    assert res.ok
    assert len(fake.sent) == 1
    assert fake.sent[0][1] == "2.0.0"


def test_update_zephyr_refuses_wrong_uid_before_send():
    fake = ZephyrFake(
        snap("1.0.0", 0, True, "WRONGUID0000"),
        snap("2.0.0", 0, True, "WRONGUID0000"),
    )
    img = make_zephyr_image("2.0.0")
    with pytest.raises(up.UpdateError, match="identity mismatch"):
        up.update_zephyr(
            img,
            "udp",
            snapshot_fn=fake.snapshot,
            send_fn=fake.send,
            expected_uid="ACA7042C3B04",
            sleep_fn=lambda s: None,
        )
    assert fake.sent == []


def test_update_zephyr_reports_send_failure():
    fake = ZephyrFake(
        snap("1.0.0", 0, True, "ACA7042C3B04"),
        snap("2.0.0", 0, True, "ACA7042C3B04"),
        fail_send=True,
    )
    img = make_zephyr_image("2.0.0")
    with pytest.raises(up.UpdateError, match="zephyr transfer failed"):
        up.update_zephyr(
            img,
            "udp",
            snapshot_fn=fake.snapshot,
            send_fn=fake.send,
            expected_uid="ACA7042C3B04",
            sleep_fn=lambda s: None,
        )


def test_update_zephyr_a_board_that_never_switches_fails():
    fake = ZephyrFake(
        snap("1.0.0", 0, True, "ACA7042C3B04"),
        snap("1.0.0", 0, True, "ACA7042C3B04"),
    )
    img = make_zephyr_image("2.0.0")
    result = up.update_zephyr(
        img,
        "udp",
        snapshot_fn=fake.snapshot,
        send_fn=fake.send,
        expected_uid="ACA7042C3B04",
        sleep_fn=lambda s: None,
        timeout_s=0.05,
        poll_s=0.01,
    )
    assert not result.ok
    assert any(c.name == "running the new image" and not c.ok for c in result.checks)


def test_update_zephyr_board_never_answers_raises():
    calls = 0

    def snap_after_send():
        nonlocal calls
        calls += 1
        if calls == 1:
            return snap("1.0.0", 0, True, "ACA7042C3B04")
        raise up.UpdateError("board offline")

    img = make_zephyr_image("2.0.0")
    with pytest.raises(up.UpdateError, match="never answered"):
        up.update_zephyr(
            img,
            "udp",
            snapshot_fn=snap_after_send,
            send_fn=lambda *a: None,
            expected_uid="ACA7042C3B04",
            sleep_fn=lambda s: None,
            timeout_s=0.05,
            poll_s=0.01,
        )


