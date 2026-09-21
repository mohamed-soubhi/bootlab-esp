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
