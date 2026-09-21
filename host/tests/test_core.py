"""Unit tests for host/labflash/core.py (BL-040/BL-046)."""
from unittest.mock import MagicMock, patch

import pytest
import yaml
from labflash import core


def test_load_rig_config_valid(tmp_path):
    rig_file = tmp_path / "rig.yaml"
    data = {
        "boards": {
            "idf": {"usb_serial": "E0:72:A1:AA:23:90", "mac": "E0:72:A1:AA:23:90"},
            "zephyr": {"usb_serial": "AC:A7:04:2C:3B:04", "mac": "AC:A7:04:2C:3B:04"},
        }
    }
    rig_file.write_text(yaml.safe_dump(data))
    loaded = core.load_rig_config(rig_file)
    assert "boards" in loaded
    assert "idf" in loaded["boards"]


def test_load_rig_config_invalid_no_boards(tmp_path):
    rig_file = tmp_path / "rig.yaml"
    rig_file.write_text("other: foo\n")
    with pytest.raises(core.BoardResolutionError, match="no 'boards' section"):
        core.load_rig_config(rig_file)


def test_live_serials_mocked():
    p1 = MagicMock()
    p1.device = "/dev/ttyACM0"
    p1.serial_number = "e072a1aa2390"

    p2 = MagicMock()
    p2.device = "/dev/ttyACM1"
    p2.serial_number = None

    p3 = MagicMock()
    p3.device = "/dev/ttyUSB0"
    p3.serial_number = "aca7042c3b04"

    with patch("labflash.core.list_ports.comports", return_value=[p1, p2, p3]):
        live = core._live_serials()
        assert live == {
            "E072A1AA2390": "/dev/ttyACM0",
            "ACA7042C3B04": "/dev/ttyUSB0",
        }


def test_resolve_board_success():
    rig = {
        "boards": {
            "idf": {"usb_serial": "E072A1AA2390"},
        }
    }
    p = MagicMock()
    p.device = "/dev/ttyACM0"
    p.serial_number = "E072A1AA2390"

    with patch("labflash.core.list_ports.comports", return_value=[p]):
        port = core.resolve_board("idf", rig=rig, wait_s=0.1)
        assert port == "/dev/ttyACM0"


def test_resolve_board_unknown_key():
    rig = {"boards": {"idf": {"usb_serial": "1234"}}}
    with pytest.raises(core.BoardResolutionError, match="unknown board key 'missing'"):
        core.resolve_board("missing", rig=rig, wait_s=0.1)


def test_resolve_board_timeout():
    rig = {
        "boards": {
            "idf": {"usb_serial": "E072A1AA2390"},
        }
    }
    p = MagicMock()
    p.device = "/dev/ttyACM1"
    p.serial_number = "DIFFERENT"

    with patch("labflash.core.list_ports.comports", return_value=[p]), \
         pytest.raises(core.BoardResolutionError, match="not found after 0.1s. Devices present: DIFFERENT"):
        core.resolve_board("idf", rig=rig, wait_s=0.1)


def test_resolve_all_boards():
    rig = {
        "boards": {
            "idf": {"usb_serial": "E072A1AA2390"},
            "zephyr": {"usb_serial": "ACA7042C3B04"},
        }
    }
    p1 = MagicMock(device="/dev/ttyACM0", serial_number="E072A1AA2390")
    p2 = MagicMock(device="/dev/ttyACM1", serial_number="ACA7042C3B04")

    with patch("labflash.core.list_ports.comports", return_value=[p1, p2]):
        all_resolved = core.resolve_all_boards(rig=rig, wait_s=0.1)
        assert all_resolved == {
            "idf": "/dev/ttyACM0",
            "zephyr": "/dev/ttyACM1",
        }
