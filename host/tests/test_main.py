"""Unit tests for host/labflash/__main__.py CLI dispatcher (BL-046)."""
from unittest.mock import MagicMock, patch

from labflash.__main__ import main


def test_main_doctor():
    with patch("labflash.doctor.main", return_value=0) as mock_doc:
        rc = main(["doctor"])
        assert rc == 0
        mock_doc.assert_called_once()


def test_main_resolve():
    with patch("labflash.core.resolve_all_boards", return_value={"idf": "/dev/ttyACM0"}):
        rc = main(["resolve"])
        assert rc == 0

    with patch("labflash.core.resolve_all_boards", return_value={"idf": "/dev/ttyACM0"}):
        rc = main(["resolve", "--json"])
        assert rc == 0


def test_main_provision():
    with patch("labflash.provision.provision_idf") as mock_prov:
        rc = main(["provision", "idf", "--ssid", "MyWiFi", "--psk", "secret123", "--token", "test-token", "--port", "/dev/ttyACM0"])
        assert rc == 0
        mock_prov.assert_called_once_with(port="/dev/ttyACM0", ssid="MyWiFi", psk="secret123", token="test-token")


def test_main_identify():
    mock_trans = MagicMock()
    with patch("labflash.identify.SerialLineTransport", return_value=mock_trans), \
         patch("labflash.identify.map_board_by_id", return_value=("idf", {"uid": "E072A1AA2390", "mcu": "esp32s3", "board": "devkit"})):
        rc = main(["identify", "--port", "/dev/ttyACM0"])
        assert rc == 0

        rc_json = main(["identify", "--port", "/dev/ttyACM0", "--json"])
        assert rc_json == 0


def test_main_info():
    mock_trans = MagicMock()
    info_dict = {
        "id": {"uid": "E072A1AA2390", "mcu": "esp32s3", "hw": "devkit", "os": "idf", "flash_kb": "16384"},
        "version": {"app": "1.0.0", "git": "1.0.0", "slot": "0", "confirmed": "1", "variant": "v1"},
        "state": {"toggles": "10", "blink_hz": "1.0", "uptime_ms": "1000", "reset": "power_on"},
    }
    with patch("labflash.identify.SerialLineTransport", return_value=mock_trans), \
         patch("labflash.identify.query_info", return_value=info_dict):
        rc = main(["info", "idf", "--port", "/dev/ttyACM0"])
        assert rc == 0

        rc_json = main(["info", "idf", "--port", "/dev/ttyACM0", "--json"])
        assert rc_json == 0


def test_main_measure():
    mock_trans = MagicMock()
    with patch("labflash.identify.SerialLineTransport", return_value=mock_trans), \
         patch("labflash.identify.measure", return_value=(10, 1.0, True)):
        rc = main(["measure", "idf", "--port", "/dev/ttyACM0", "--seconds", "1.0", "--expect-hz", "1.0"])
        assert rc == 0


def test_main_flash_and_recover():
    with patch("labflash.flash.flash_board") as mock_flash:
        rc = main(["flash", "idf", "--port", "/dev/ttyACM0"])
        assert rc == 0
        mock_flash.assert_called_once_with("idf", port="/dev/ttyACM0", recover=False)

    with patch("labflash.flash.flash_board") as mock_recover:
        rc = main(["recover", "idf", "--port", "/dev/ttyACM0"])
        assert rc == 0
        mock_recover.assert_called_once_with("idf", port="/dev/ttyACM0", recover=True)


def test_main_build():
    from pathlib import Path

    from labflash.build import BuildResult
    res = BuildResult("idf", "v1", Path("/tmp/b"), Path("/tmp/b/app.bin"), 1000, "1.0.0", True, True)
    with patch("labflash.build.build_board", return_value={"v1": res}):
        rc = main(["build", "idf", "--variant", "v1"])
        assert rc == 0


def test_main_update():
    with patch("labflash.update_cli.run_update", return_value=0) as mock_upd:
        rc = main(["update", "idf", "--image", "/tmp/app.bin", "--transport", "wifi", "--board-ip", "192.168.1.152"])
        assert rc == 0
        mock_upd.assert_called_once()


def test_main_no_args():
    import pytest
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2


def test_main_resolve_errors():
    from labflash.core import BoardResolutionError
    with patch("labflash.core.resolve_all_boards", side_effect=BoardResolutionError("no boards")):
        rc = main(["resolve"])
        assert rc == 1
        rc_json = main(["resolve", "--json"])
        assert rc_json == 1


def test_main_provision_branches(tmp_path, monkeypatch):
    from labflash.core import BoardResolutionError
    monkeypatch.delenv("WIFI_SSID", raising=False)
    # Missing SSID
    rc = main(["provision", "idf", "--port", "/dev/ttyACM0", "--env-file", str(tmp_path / "empty.env")])
    assert rc == 1

    # PSK from psk_file
    psk_f = tmp_path / "psk.txt"
    psk_f.write_text("file_password\n")
    with patch("labflash.provision.provision_idf") as mock_prov:
        rc = main(["provision", "idf", "--ssid", "TestSSID", "--psk-file", str(psk_f), "--port", "/dev/ttyACM0"])
        assert rc == 0
        assert mock_prov.call_args.kwargs["psk"] == "file_password"

    # Resolve board failure
    with patch("labflash.core.resolve_board", side_effect=BoardResolutionError("no port")):
        rc = main(["provision", "idf", "--ssid", "TestSSID", "--psk", "secret"])
        assert rc == 1

    # Provision exception
    with patch("labflash.provision.provision_idf", side_effect=RuntimeError("nvs error")):
        rc = main(["provision", "idf", "--ssid", "TestSSID", "--psk", "secret", "--port", "/dev/ttyACM0"])
        assert rc == 1


def test_main_build_errors():
    from labflash.build import BuildError, ZephyrGatedError
    with patch("labflash.build.build_board", side_effect=ZephyrGatedError("zephyr gate blocked")):
        rc = main(["build", "zephyr"])
        assert rc == 2

    with patch("labflash.build.build_board", side_effect=BuildError("compiler error")):
        rc = main(["build", "idf"])
        assert rc == 1


def test_main_flash_errors():
    from labflash.flash import FlashError, ZephyrGatedError
    with patch("labflash.flash.flash_board", side_effect=ZephyrGatedError("gate blocked")):
        rc = main(["flash", "zephyr"])
        assert rc == 2

    with patch("labflash.flash.flash_board", side_effect=FlashError("write failed")):
        rc = main(["flash", "idf", "--port", "/dev/ttyACM0"])
        assert rc == 1


def test_main_identify_errors():
    from labflash.core import BoardResolutionError
    # 1. Resolve board error
    with patch("labflash.core.resolve_board", side_effect=BoardResolutionError("not found")):
        rc = main(["identify", "--board", "idf"])
        assert rc == 1

    # 2. No boards resolved from rig
    with patch("labflash.core.load_rig_config", return_value={"boards": {}}):
        rc = main(["identify"])
        assert rc == 1

    # 3. Transport exception on specified port
    with patch("labflash.identify.SerialLineTransport", side_effect=RuntimeError("open error")):
        rc = main(["identify", "--port", "/dev/ttyACM0"])
        assert rc == 1


def test_main_info_errors():
    from labflash.core import BoardResolutionError
    with patch("labflash.core.resolve_board", side_effect=BoardResolutionError("no board")):
        rc = main(["info", "idf"])
        assert rc == 1

    with patch("labflash.core.resolve_board", return_value="/dev/ttyACM0"), \
         patch("labflash.identify.SerialLineTransport", side_effect=RuntimeError("serial error")):
        rc = main(["info", "idf"])
        assert rc == 1


def test_main_measure_errors():
    from labflash.core import BoardResolutionError
    with patch("labflash.core.resolve_board", side_effect=BoardResolutionError("no board")):
        rc = main(["measure", "idf"])
        assert rc == 1

    with patch("labflash.core.resolve_board", return_value="/dev/ttyACM0"), \
         patch("labflash.identify.SerialLineTransport", side_effect=RuntimeError("measure error")):
        rc = main(["measure", "idf"])
        assert rc == 1

