"""Unit tests for host/labflash/update_cli.py (BL-043 / BL-046)."""
import argparse
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

