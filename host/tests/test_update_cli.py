"""Unit tests for host/labflash/update_cli.py (BL-043 / BL-046)."""
import argparse
import types
from unittest.mock import MagicMock, patch

import pytest
from labflash import update_cli
from labflash.update import Check, Snapshot, UpdateError, UpdateResult


def test_guess_host_ip():
    mock_sock = MagicMock()
    mock_sock.getsockname.return_value = ("192.168.1.100", 12345)
    mock_sock.__enter__.return_value = mock_sock

    with patch("socket.socket", return_value=mock_sock):
        ip = update_cli.guess_host_ip("192.168.1.1")
        assert ip == "192.168.1.100"


def test_read_token(tmp_path, monkeypatch):
    # 1. Explicit token
    assert update_cli.read_token(None, "explicit-token") == "explicit-token"

    # 2. Environment variable
    monkeypatch.setenv("OTA_TOKEN", "env-token")
    assert update_cli.read_token(None, None) == "env-token"
    monkeypatch.delenv("OTA_TOKEN")

    # 3. From env file
    env_file = tmp_path / "creds.env"
    env_file.write_text("OTHER=foo\nOTA_TOKEN=file-token\n")
    assert update_cli.read_token(str(env_file), None) == "file-token"

    # 4. Default fallback
    assert update_cli.read_token(str(tmp_path / "nonexistent.env"), None) == update_cli.DEFAULT_TOKEN


def test_rig_mac():
    rig = {"boards": {"idf": {"mac": "E0:72:A1:AA:23:90"}}}
    with patch("labflash.core.load_rig_config", return_value=rig):
        assert update_cli.rig_mac(None, "idf") == "E0:72:A1:AA:23:90"
        assert update_cli.rig_mac(None, "zephyr") is None

    with patch("labflash.core.load_rig_config", side_effect=Exception("error")):
        assert update_cli.rig_mac(None, "idf") is None


def test_labid_snapshot_fn():
    with patch("labflash.identify.SerialLineTransport"), \
         patch("labflash.identify.get_version", return_value={"app": "1.0.0", "slot": "0", "confirmed": "1"}), \
         patch("labflash.identify.identify", return_value={"uid": "E072A1AA2390"}):
        snap_fn = update_cli.labid_snapshot_fn("/dev/ttyACM0")
        snap = snap_fn()
        assert snap.app == "1.0.0"
        assert snap.slot == 0
        assert snap.confirmed is True
        assert snap.uid == "E072A1AA2390"
        assert snap.source == "labid"


def test_https_snapshot_fn():
    board = MagicMock()
    board.version.return_value = {"app": "2.0.0", "slot": 1, "confirmed": True}
    snap_fn = update_cli.https_snapshot_fn(board)
    snap = snap_fn()
    assert snap.app == "2.0.0"
    assert snap.slot == 1
    assert snap.confirmed is True
    assert snap.source == "https"

    board.version.return_value = None
    with pytest.raises(UpdateError, match="the board did not answer"):
        snap_fn()


def test_make_wifi_send(tmp_path):
    board = MagicMock()
    board.trigger.return_value = 202
    server = MagicMock(port=8443)

    send = update_cli.make_wifi_send(board, server, "192.168.1.134", tmp_path)
    send(b"IMAGE_BYTES", "2.0.0")
    assert (tmp_path / "update.bin").read_bytes() == b"IMAGE_BYTES"
    board.trigger.assert_called_once_with("https://192.168.1.134:8443/update.bin", "2.0.0")

    board.trigger.return_value = 409
    with pytest.raises(UpdateError, match="the board refused POST /ota: HTTP 409"):
        send(b"IMAGE_BYTES", "2.0.0")


def test_run_update_nonexistent_image(capsys):
    args = argparse.Namespace(image="/nonexistent/path/fw.bin")
    rc = update_cli.run_update(args)
    assert rc == 1
    assert "cannot read the image" in capsys.readouterr().err


def test_run_update_success(tmp_path):
    img = tmp_path / "v2.bin"
    img.write_bytes(b"dummy image bytes")

    args = argparse.Namespace(
        image=str(img),
        board="idf",
        board_mac="E0:72:A1:AA:23:90",
        rig=None,
        transport="wifi",
        board_ip="192.168.1.152",
        host_ip="192.168.1.134",
        http_port=8443,
        keys=str(tmp_path),
        server_cert=None,
        server_key=None,
        ca_cert=None,
        address=None,
        scan_timeout=10.0,
        env_file=None,
        token=None,
        labid_port=None,
        no_labid=True,
        timeout=10.0,
        poll=1.0,
        post_confirm=False,
    )

    (tmp_path / "ca.pem").write_text("ca")
    (tmp_path / "server_cert.pem").write_text("cert")
    (tmp_path / "server_key.pem").write_text("key")

    mock_res = UpdateResult(
        ok=True,
        checks=[Check("running the new image", True, "2.0.0")],
        version="2.0.0",
        pre=Snapshot("1.0.0", 0, True, None, "https"),
        post=Snapshot("2.0.0", 1, True, None, "https"),
    )

    with patch("labflash.idf_wifi_ota.OtaServer"), \
         patch("labflash.idf_wifi_ota.WifiBoard"), \
         patch("labflash.update_cli.update_idf", return_value=mock_res):
        rc = update_cli.run_update(args)
        assert rc == 0


def test_make_ble_send():
    mock_dev = MagicMock(name="nimble-ble-ota", address="AA:BB:CC:DD:EE:FF")

    async def fake_find_device(*args, **kwargs):
        return mock_dev

    async def fake_upload(*args, **kwargs):
        return {"ok": True}

    with patch("labflash.idf_ble_ota.find_device", side_effect=fake_find_device), \
         patch("labflash.idf_ble_ota.upload", side_effect=fake_upload):
        send = update_cli.make_ble_send("E0:72:A1:AA:23:90", None, 5.0)
        send(b"IMAGE", "1.0.0")


def test_run_update_missing_board_ip(tmp_path, capsys):
    img = tmp_path / "v1.bin"
    img.write_bytes(b"image")
    args = argparse.Namespace(
        image=str(img),
        board="idf",
        board_mac="E0:72:A1:AA:23:90",
        rig=None,
        transport="wifi",
        board_ip=None,
        keys=str(tmp_path),
    )
    rc = update_cli.run_update(args)
    assert rc == 1
    assert "--board-ip is required" in capsys.readouterr().err


def test_run_update_update_error(tmp_path, capsys):
    img = tmp_path / "v1.bin"
    img.write_bytes(b"image")
    args = argparse.Namespace(
        image=str(img),
        board="idf",
        board_mac="E0:72:A1:AA:23:90",
        rig=None,
        transport="wifi",
        board_ip="192.168.1.152",
        host_ip="192.168.1.134",
        http_port=8443,
        keys=str(tmp_path),
        server_cert=None,
        server_key=None,
        ca_cert=None,
        address=None,
        scan_timeout=10.0,
        env_file=None,
        token=None,
        labid_port=None,
        no_labid=True,
        timeout=10.0,
        poll=1.0,
        post_confirm=False,
    )
    with patch("labflash.idf_wifi_ota.OtaServer"), \
         patch("labflash.idf_wifi_ota.WifiBoard"), \
         patch("labflash.update_cli.update_idf", side_effect=UpdateError("simulated failure")):
        rc = update_cli.run_update(args)
        assert rc == 1
        assert "simulated failure" in capsys.readouterr().err


# ---------------------------------------------------------------- Zephyr CLI tests (BL-044)
def test_rig_board_info():
    rig = {
        "boards": {
            "zephyr": {
                "mac": "AC:A7:04:2C:3B:04",
                "ble_mac": "AC:A7:04:2C:3B:06",
                "ip": "192.168.1.153",
                "udp_port": 1337,
            }
        }
    }
    with patch("labflash.core.load_rig_config", return_value=rig):
        assert update_cli.rig_mac(None, "zephyr") == "AC:A7:04:2C:3B:04"
        assert update_cli.rig_ble_mac(None, "zephyr") == "AC:A7:04:2C:3B:06"
        assert update_cli.rig_ip(None, "zephyr") == "192.168.1.153"
        assert update_cli.rig_udp_port(None, "zephyr") == 1337

    with patch("labflash.core.load_rig_config", side_effect=Exception("no rig")):
        assert update_cli.rig_ble_mac(None, "zephyr") is None
        assert update_cli.rig_ip(None, "zephyr") is None
        assert update_cli.rig_udp_port(None, "zephyr") is None


def test_make_zephyr_udp_send():
    mock_client = MagicMock()

    class FakeImg:
        def __init__(self, slot, hash_bytes):
            self.slot = slot
            self.hash = hash_bytes

    class FakeImgState:
        def __init__(self):
            self.images = [FakeImg(1, b"\xaa" * 32)]

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    async def fake_request(req):
        return FakeImgState()

    async def fake_upload(image, slot=0, first_timeout_s=60.0):
        yield len(image)

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.request = fake_request
    mock_client.upload = fake_upload

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.udp.SMPUDPTransport"):
        send = update_cli.make_zephyr_udp_send("192.168.1.153", 1337)
        send(b"PAYLOAD", "2.0.0", "aa" * 32)


def test_make_zephyr_ble_send_powershell_fallback(tmp_path):
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "BLE OTA complete"

    with patch("smpclient.transport.ble.SMPBLETransport", side_effect=Exception("bluez service unknown")), \
         patch("shutil.which", return_value="powershell.exe"), \
         patch("subprocess.run", return_value=mock_proc) as mock_sub:
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        send(b"PAYLOAD", "2.0.0", "aa" * 32)
        assert mock_sub.called


def test_make_zephyr_smp_snapshot():
    class FakeImg:
        def __init__(self, slot, confirmed, hash_bytes):
            self.slot = slot
            self.confirmed = confirmed
            self.hash = hash_bytes
            self.active = True
            self.version = "2.0.0"

    class FakeImgState:
        def __init__(self):
            self.images = [FakeImg(0, True, bytes.fromhex("ba6245db" * 8))]

    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    async def fake_request(req):
        return FakeImgState()

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.udp.SMPUDPTransport"):
        snap_fn = update_cli.make_zephyr_smp_snapshot(
            "udp", "192.168.1.153", 1337, expected_hash="ba6245db" * 8, expected_version="2.0.0"
        )
        snap = snap_fn()
        assert snap.app == "2.0.0"
        assert snap.slot == 0
        assert snap.confirmed is True


def test_run_update_zephyr_udp_success(tmp_path):
    img = tmp_path / "zephyr_v2.bin"
    img.write_bytes(b"dummy")

    args = argparse.Namespace(
        image=str(img),
        board="zephyr",
        board_mac="AC:A7:04:2C:3B:04",
        rig=None,
        transport="udp",
        board_ip="192.168.1.153",
        udp_port=1337,
        address=None,
        labid_port=None,
        no_labid=True,
        timeout=10.0,
        confirm_timeout=30.0,
    )

    mock_res = UpdateResult(
        ok=True,
        checks=[
            Check("running the new image", True, "2.0.0"),
            Check("active in slot 0", True, "slot 0"),
            Check("confirmed", True, "confirmed"),
        ],
        version="2.0.0",
        pre=Snapshot("1.0.0", 0, True, None, "smp"),
        post=Snapshot("2.0.0", 0, True, None, "smp"),
    )

    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "ba6245db" * 8)), \
         patch("labflash.update_cli.make_zephyr_udp_send"), \
         patch("labflash.update_cli.make_zephyr_smp_snapshot"), \
         patch("labflash.update_cli.update_zephyr", return_value=mock_res):
        rc = update_cli.run_update(args)
        assert rc == 0


def test_run_update_zephyr_ble_success(tmp_path):
    img = tmp_path / "zephyr_v2.bin"
    img.write_bytes(b"dummy")

    args = argparse.Namespace(
        image=str(img),
        board="zephyr",
        board_mac="AC:A7:04:2C:3B:04",
        rig=None,
        transport="ble",
        board_ip=None,
        udp_port=1337,
        address="AC:A7:04:2C:3B:06",
        labid_port=None,
        no_labid=True,
        timeout=10.0,
        confirm_timeout=30.0,
    )

    mock_res = UpdateResult(
        ok=True,
        checks=[
            Check("running the new image", True, "2.0.0"),
            Check("active in slot 0", True, "slot 0"),
            Check("confirmed", True, "confirmed"),
        ],
        version="2.0.0",
        pre=Snapshot("1.0.0", 0, True, None, "smp"),
        post=Snapshot("2.0.0", 0, True, None, "smp"),
    )

    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "ba6245db" * 8)), \
         patch("labflash.update_cli.make_zephyr_ble_send"), \
         patch("labflash.update_cli.make_zephyr_smp_snapshot"), \
         patch("labflash.update_cli.update_zephyr", return_value=mock_res):
        rc = update_cli.run_update(args)
        assert rc == 0


def test_run_update_zephyr_invalid_transport(tmp_path, capsys):
    img = tmp_path / "zephyr_v2.bin"
    img.write_bytes(b"dummy")

    args = argparse.Namespace(
        image=str(img),
        board="zephyr",
        board_mac="AC:A7:04:2C:3B:04",
        rig=None,
        transport="wifi",
    )

    rc = update_cli.run_update(args)
    assert rc == 1
    assert "unsupported transport 'wifi'" in capsys.readouterr().err


def test_run_update_zephyr_missing_ip(tmp_path, capsys):
    img = tmp_path / "zephyr_v2.bin"
    img.write_bytes(b"dummy")

    args = argparse.Namespace(
        image=str(img),
        board="zephyr",
        board_mac="AC:A7:04:2C:3B:04",
        rig=None,
        transport="udp",
        board_ip=None,
    )

    with patch("labflash.update_cli.rig_ip", return_value=None), \
         patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "ba6245db" * 8)):
        rc = update_cli.run_update(args)
        assert rc == 1
        assert "--board-ip or ip in rig.yaml is required" in capsys.readouterr().err


def test_make_wifi_send_timeout(tmp_path):
    board = MagicMock()
    board.trigger.return_value = -1
    server = MagicMock(port=8443)
    send = update_cli.make_wifi_send(board, server, "192.168.1.134", tmp_path)
    with pytest.raises(UpdateError, match="the board never answered POST /ota"):
        send(b"IMAGE", "2.0.0")


def test_make_ble_send_error():
    from labflash.idf_ble_ota import BleOtaError
    with patch("labflash.idf_ble_ota.find_device", side_effect=BleOtaError("ble device lost")):
        send = update_cli.make_ble_send("AA:BB:CC:DD:EE:FF", None, 5.0)
        with pytest.raises(UpdateError, match="BLE transfer failed"):
            send(b"IMAGE", "2.0.0")


def test_make_zephyr_udp_send_uploaded_not_in_slot1():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    async def fake_upload(*a, **kw):
        yield 100

    async def fake_request(req):
        return types.SimpleNamespace(images=[])

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.upload = fake_upload
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.udp.SMPUDPTransport"):
        send = update_cli.make_zephyr_udp_send("192.168.1.153", 1337)
        with pytest.raises(UpdateError, match="uploaded image not found in slot 1"):
            send(b"X" * 100, "2.0.0", "ab" * 32)


def test_make_zephyr_udp_send_generic_exception():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        raise RuntimeError("socket error")

    async def fake_disconnect():
        pass

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.udp.SMPUDPTransport"):
        send = update_cli.make_zephyr_udp_send("192.168.1.153", 1337)
        with pytest.raises(UpdateError, match="UDP transfer failed: socket error"):
            send(b"X" * 100, "2.0.0", "ab" * 32)


def test_make_zephyr_ble_send_native_success():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    async def fake_upload(*a, **kw):
        yield 100

    img = types.SimpleNamespace(slot=1, hash=b"\xba" * 32)

    async def fake_request(req):
        return types.SimpleNamespace(images=[img])

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.upload = fake_upload
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.ble.SMPBLETransport"):
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        send(b"X" * 100, "2.0.0", "ba" * 32)


def test_make_zephyr_ble_send_native_slot1_occupied_retry():
    mock_client = MagicMock()
    connect_calls = 0

    async def fake_connect(*a, **kw):
        nonlocal connect_calls
        connect_calls += 1

    async def fake_disconnect():
        pass

    async def fake_upload(*a, **kw):
        yield 100

    img = types.SimpleNamespace(slot=1, hash=b"\xba" * 32)
    erase_called = False

    async def fake_request(req):
        nonlocal erase_called
        from smpclient.requests.image_management import ImageErase
        if isinstance(req, ImageErase) and not erase_called:
            erase_called = True
            raise RuntimeError("erase timeout")
        return types.SimpleNamespace(images=[img])

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.upload = fake_upload
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.ble.SMPBLETransport"), \
         patch("asyncio.sleep"):
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        send(b"X" * 100, "2.0.0", "ba" * 32)
        assert connect_calls == 2


def test_make_zephyr_ble_send_native_uploaded_missing():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    async def fake_upload(*a, **kw):
        yield 100

    async def fake_request(req):
        return types.SimpleNamespace(images=[])

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.upload = fake_upload
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.ble.SMPBLETransport"):
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        with pytest.raises(UpdateError, match="uploaded image not found in slot 1"):
            send(b"X" * 100, "2.0.0", "ba" * 32)


def test_make_zephyr_ble_send_windows_fallback():
    mock_proc = MagicMock(returncode=0, stdout="OK BLE uploaded", stderr="")
    with patch("smpclient.SMPClient", side_effect=Exception("bluez not found")), \
         patch("shutil.which", return_value="/mnt/c/Windows/powershell.exe"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.write_bytes"), \
         patch("pathlib.Path.unlink"), \
         patch("subprocess.run", return_value=mock_proc):
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        send(b"IMAGE", "2.0.0", "ba" * 32)

    # Windows fallback failure
    mock_proc_fail = MagicMock(returncode=1, stdout="", stderr="connection timed out")
    with patch("smpclient.SMPClient", side_effect=Exception("dbus error")), \
         patch("shutil.which", return_value="/mnt/c/Windows/powershell.exe"), \
         patch("pathlib.Path.exists", return_value=False), \
         patch("pathlib.Path.write_bytes"), \
         patch("pathlib.Path.unlink"), \
         patch("subprocess.run", return_value=mock_proc_fail):
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        with pytest.raises(UpdateError, match="BLE transfer via Windows failed"):
            send(b"IMAGE", "2.0.0", "ba" * 32)

    # Powershell not available
    with patch("smpclient.SMPClient", side_effect=Exception("dbus error")), \
         patch("shutil.which", return_value=None):
        send = update_cli.make_zephyr_ble_send("AC:A7:04:2C:3B:06")
        with pytest.raises(UpdateError, match="BLE transfer failed: dbus error"):
            send(b"IMAGE", "2.0.0", "ba" * 32)


def test_make_zephyr_smp_snapshot_native_ble_success():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    img = types.SimpleNamespace(slot=0, version="1.0.0", hash=b"\x11" * 32, confirmed=True, active=True)

    async def fake_request(req):
        return types.SimpleNamespace(images=[img])

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.ble.SMPBLETransport"):
        snap_fn = update_cli.make_zephyr_smp_snapshot("ble", "AC:A7:04:2C:3B:06")
        snap = snap_fn()
        assert snap.app == "1.0.0"
        assert snap.slot == 0
        assert snap.confirmed is True


def test_make_zephyr_smp_snapshot_udp_failure():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        raise RuntimeError("udp conn timeout")

    async def fake_disconnect():
        pass

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.udp.SMPUDPTransport"):
        snap_fn = update_cli.make_zephyr_smp_snapshot("udp", "192.168.1.153")
        with pytest.raises(UpdateError, match="SMP UDP query failed"):
            snap_fn()


def test_make_zephyr_smp_snapshot_windows_fallback():
    # 1. Success with hash & expected_version matching
    json_out = '[{"slot": 0, "ver": "2.0.0", "hash": "aabbcc", "confirmed": true, "active": true}]'
    mock_proc = MagicMock(returncode=0, stdout=json_out, stderr="")
    with patch("smpclient.SMPClient", side_effect=Exception("bluez not found")), \
         patch("shutil.which", return_value="powershell.exe"), \
         patch("subprocess.run", return_value=mock_proc):
        snap_fn = update_cli.make_zephyr_smp_snapshot("ble", "AC:A7:04:2C:3B:06", expected_hash="aabbcc", expected_version="2.0.0")
        snap = snap_fn()
        assert snap.app == "2.0.0"
        assert snap.confirmed is True

    # 2. Windows fallback proc non-zero
    mock_proc_err = MagicMock(returncode=1, stdout="", stderr="ble fail")
    with patch("smpclient.SMPClient", side_effect=Exception("dbus error")), \
         patch("shutil.which", return_value="powershell.exe"), \
         patch("subprocess.run", return_value=mock_proc_err):
        snap_fn = update_cli.make_zephyr_smp_snapshot("ble", "AC:A7:04:2C:3B:06")
        with pytest.raises(UpdateError, match="SMP BLE query via Windows failed"):
            snap_fn()

    # 3. Windows fallback invalid json
    mock_proc_bad = MagicMock(returncode=0, stdout="not-json", stderr="")
    with patch("smpclient.SMPClient", side_effect=Exception("dbus error")), \
         patch("shutil.which", return_value="powershell.exe"), \
         patch("subprocess.run", return_value=mock_proc_bad):
        snap_fn = update_cli.make_zephyr_smp_snapshot("ble", "AC:A7:04:2C:3B:06")
        with pytest.raises(UpdateError, match="failed to parse SMP query from Windows"):
            snap_fn()

    # 4. Windows fallback no active image in json
    mock_proc_empty = MagicMock(returncode=0, stdout='[{"slot": 1}]', stderr="")
    with patch("smpclient.SMPClient", side_effect=Exception("dbus error")), \
         patch("shutil.which", return_value="powershell.exe"), \
         patch("subprocess.run", return_value=mock_proc_empty):
        snap_fn = update_cli.make_zephyr_smp_snapshot("ble", "AC:A7:04:2C:3B:06")
        with pytest.raises(UpdateError, match="no active image in SMP list"):
            snap_fn()


def test_make_zephyr_smp_snapshot_native_no_active_image():
    mock_client = MagicMock()

    async def fake_connect(*a, **kw):
        pass

    async def fake_disconnect():
        pass

    async def fake_request(req):
        return types.SimpleNamespace(images=[])

    mock_client.connect = fake_connect
    mock_client.disconnect = fake_disconnect
    mock_client.request = fake_request

    with patch("smpclient.SMPClient", return_value=mock_client), \
         patch("smpclient.transport.udp.SMPUDPTransport"):
        snap_fn = update_cli.make_zephyr_smp_snapshot("udp", "192.168.1.153")
        with pytest.raises(UpdateError, match="no active image found in SMP image list"):
            snap_fn()


def test_run_update_zephyr_check_image_error(tmp_path, capsys):
    img = tmp_path / "bad.bin"
    img.write_bytes(b"bad")
    args = argparse.Namespace(image=str(img), board="zephyr", transport="udp", board_mac=None, rig=None)
    with patch("labflash.update_cli.check_zephyr_image", side_effect=UpdateError("bad header")):
        rc = update_cli.run_update(args)
        assert rc == 1
        assert "ERROR: bad header" in capsys.readouterr().err


def test_run_update_zephyr_ble_missing_mac(tmp_path, capsys):
    img = tmp_path / "zephyr.bin"
    img.write_bytes(b"dummy")
    args = argparse.Namespace(
        image=str(img), board="zephyr", transport="ble", board_mac=None,
        address=None, rig=None
    )
    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "aabb" * 16)), \
         patch("labflash.update_cli.rig_ble_mac", return_value=None):
        rc = update_cli.run_update(args)
        assert rc == 1
        assert "--address or ble_mac in rig.yaml is required" in capsys.readouterr().err


def test_run_update_zephyr_with_labid_resolution(tmp_path):
    from labflash.core import BoardResolutionError
    img = tmp_path / "zephyr.bin"
    img.write_bytes(b"dummy")
    args = argparse.Namespace(
        image=str(img), board="zephyr", transport="udp", board_mac="AC:A7:04:2C:3B:04",
        board_ip="192.168.1.153", udp_port=1337, labid_port=None, no_labid=False,
        rig=None, timeout=10.0, confirm_timeout=30.0
    )

    # Resolution error
    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "aabb" * 16)), \
         patch("labflash.core.resolve_board", side_effect=BoardResolutionError("no zephyr port")):
        rc = update_cli.run_update(args)
        assert rc == 1

    # Resolution success
    mock_res = UpdateResult(
        ok=True,
        checks=[],
        version="2.0.0",
        pre=Snapshot("1.0.0", 0, True, None, "smp"),
        post=Snapshot("2.0.0", 0, True, None, "smp"),
    )
    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "aabb" * 16)), \
         patch("labflash.core.resolve_board", return_value="/dev/ttyACM0"), \
         patch("labflash.update_cli.labid_snapshot_fn"), \
         patch("labflash.update_cli.update_zephyr", return_value=mock_res):
        rc = update_cli.run_update(args)
        assert rc == 0


def test_run_update_zephyr_update_failed_and_exception(tmp_path, capsys):
    img = tmp_path / "zephyr.bin"
    img.write_bytes(b"dummy")
    args = argparse.Namespace(
        image=str(img), board="zephyr", transport="udp", board_mac="AC:A7:04:2C:3B:04",
        board_ip="192.168.1.153", udp_port=1337, labid_port=None, no_labid=True,
        rig=None, timeout=10.0, confirm_timeout=30.0
    )

    # update_zephyr raises UpdateError
    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "aabb" * 16)), \
         patch("labflash.update_cli.make_zephyr_udp_send"), \
         patch("labflash.update_cli.make_zephyr_smp_snapshot"), \
         patch("labflash.update_cli.update_zephyr", side_effect=UpdateError("transfer timed out")):
        rc = update_cli.run_update(args)
        assert rc == 1
        assert "ERROR: transfer timed out" in capsys.readouterr().err

    # update_zephyr returns ok=False
    mock_res_fail = UpdateResult(
        ok=False,
        checks=[],
        version="2.0.0",
        pre=Snapshot("1.0.0", 0, True, None, "smp"),
        post=Snapshot("1.0.0", 0, True, None, "smp"),
    )
    with patch("labflash.update_cli.check_zephyr_image", return_value=("2.0.0", "aabb" * 16)), \
         patch("labflash.update_cli.make_zephyr_udp_send"), \
         patch("labflash.update_cli.make_zephyr_smp_snapshot"), \
         patch("labflash.update_cli.update_zephyr", return_value=mock_res_fail):
        rc = update_cli.run_update(args)
        assert rc == 1


def test_run_update_idf_branches(tmp_path, capsys):
    from labflash.core import BoardResolutionError
    img = tmp_path / "idf.bin"
    img.write_bytes(b"dummy")

    # 1. no-labid without https_fn (e.g. transport=ble, no board_ip)
    args_no_ip = argparse.Namespace(
        image=str(img), board="idf", transport="ble", board_ip=None,
        board_mac="E0:72:A1:AA:23:90", address="E0:72:A1:AA:23:90",
        no_labid=True, keys=None, env_file=None, token=None, ca_cert=None, rig=None
    )
    rc = update_cli.run_update(args_no_ip)
    assert rc == 1
    assert "--no-labid needs --board-ip" in capsys.readouterr().err

    # 2. not no-labid: resolve_board failure
    args_resolve_fail = argparse.Namespace(
        image=str(img), board="idf", transport="ble", board_ip=None,
        board_mac="E0:72:A1:AA:23:90", address="E0:72:A1:AA:23:90",
        no_labid=False, labid_port=None, keys=None, env_file=None, token=None, ca_cert=None, rig=None
    )
    with patch("labflash.core.resolve_board", side_effect=BoardResolutionError("no idf port")):
        rc = update_cli.run_update(args_resolve_fail)
        assert rc == 1

    # 3. update_idf raises UpdateError
    args_ok = argparse.Namespace(
        image=str(img), board="idf", transport="ble", board_ip=None,
        board_mac="E0:72:A1:AA:23:90", address="E0:72:A1:AA:23:90",
        no_labid=False, labid_port="/dev/ttyACM0", keys=None, env_file=None, token=None, ca_cert=None, rig=None,
        timeout=10.0, confirm_timeout=30.0
    )
    with patch("labflash.update_cli.make_ble_send"), \
         patch("labflash.update_cli.labid_snapshot_fn"), \
         patch("labflash.update_cli.update_idf", side_effect=UpdateError("idf fail")):
        rc = update_cli.run_update(args_ok)
        assert rc == 1
        assert "ERROR: idf fail" in capsys.readouterr().err

    # 4. update returns ok=False
    mock_res_fail = UpdateResult(
        ok=False,
        checks=[],
        version="2.0.0",
        pre=Snapshot("1.0.0", 0, True, None, "labid"),
        post=Snapshot("1.0.0", 0, True, None, "labid"),
    )
    with patch("labflash.update_cli.make_ble_send"), \
         patch("labflash.update_cli.labid_snapshot_fn"), \
         patch("labflash.update_cli.update_idf", return_value=mock_res_fail):
        rc = update_cli.run_update(args_ok)
        assert rc == 1



