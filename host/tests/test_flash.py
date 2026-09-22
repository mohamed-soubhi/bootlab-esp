"""Unit tests for host/labflash/flash.py (BL-042)."""
import subprocess

import pytest
from labflash import flash as fl


def test_normalize_mac():
    assert fl.normalize_mac("E0:72:A1:AA:23:90") == "e072a1aa2390"
    assert fl.normalize_mac("e0-72-a1-aa-23-90") == "e072a1aa2390"
    assert fl.normalize_mac("E072A1AA2390") == "e072a1aa2390"


def test_unknown_board_rejected():
    with pytest.raises(fl.FlashError, match="Unknown board 'invalid'"):
        fl.flash_board("invalid")


def test_identity_mismatch_refuses_write():
    rig = {
        "boards": {
            "idf": {"mac": "E0:72:A1:AA:23:90"},
            "zephyr": {"mac": "AC:A7:04:2C:3B:04"},
        }
    }

    # Simulate runner where chip reports zephyr's MAC when flashing idf
    def mock_runner_mismatch(cmd, cwd=None):
        if "read-mac" in cmd or "read_mac" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="MAC: ac:a7:04:2c:3b:04", stderr="")
        raise AssertionError("Write command must NOT be executed on identity mismatch!")

    with pytest.raises(fl.FlashIdentityError, match="Write REFUSED"):
        fl.check_identity_before_write("idf", "/dev/fake-port", rig=rig, runner=mock_runner_mismatch)

    # Simulate runner where chip reports idf's MAC when flashing zephyr
    def mock_runner_mismatch_zephyr(cmd, cwd=None):
        if "read-mac" in cmd or "read_mac" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="MAC: e0:72:a1:aa:23:90", stderr="")
        raise AssertionError("Write command must NOT be executed on identity mismatch!")

    with pytest.raises(fl.FlashIdentityError, match="Write REFUSED"):
        fl.check_identity_before_write("zephyr", "/dev/fake-port", rig=rig, runner=mock_runner_mismatch_zephyr)


def test_factory_flash_assembly(tmp_path):
    # Set up mock build tree
    esp_idf = tmp_path / "esp_idf" / "build"
    esp_idf.mkdir(parents=True)
    (esp_idf / "bootloader").mkdir()
    (esp_idf / "partition_table").mkdir()

    (esp_idf / "bootloader" / "bootloader.bin").write_bytes(b"\x01" * 100)
    (esp_idf / "partition_table" / "partition-table.bin").write_bytes(b"\x02" * 100)
    (esp_idf / "ota_data_initial.bin").write_bytes(b"\x03" * 100)
    (esp_idf / "bootlab_idf_blink.bin").write_bytes(b"\x04" * 100)

    executed_cmds = []

    def mock_runner(cmd, cwd=None):
        executed_cmds.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Wrote 100 bytes", stderr="")

    fl.factory_flash_idf("/dev/fake-port", repo_root=tmp_path, runner=mock_runner)
    assert len(executed_cmds) == 1
    cmd = executed_cmds[0]
    assert "esptool" in cmd[0]
    assert "write-flash" in cmd
    assert "0x0" in cmd
    assert "0x8000" in cmd
    assert "0xf000" in cmd
    assert "0x20000" in cmd


def test_recover_erases_first(tmp_path):
    esp_idf = tmp_path / "esp_idf" / "build"
    esp_idf.mkdir(parents=True)
    (esp_idf / "bootloader").mkdir()
    (esp_idf / "partition_table").mkdir()

    (esp_idf / "bootloader" / "bootloader.bin").write_bytes(b"\x01" * 100)
    (esp_idf / "partition_table" / "partition-table.bin").write_bytes(b"\x02" * 100)
    (esp_idf / "ota_data_initial.bin").write_bytes(b"\x03" * 100)
    (esp_idf / "bootlab_idf_blink.bin").write_bytes(b"\x04" * 100)

    executed_cmds = []

    def mock_runner(cmd, cwd=None):
        executed_cmds.append(list(cmd))
        if "read-mac" in cmd or "read_mac" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="MAC: e0:72:a1:aa:23:90", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

    # Mock get_port_serial_number to return None so it falls back to runner read_mac
    fl.flash_board("idf", port="/dev/fake-port", recover=True, repo_root=tmp_path, runner=mock_runner)

    # First command is read-mac, second is erase-flash, third is write-flash
    op_cmds = [c for c in executed_cmds if "erase-flash" in c or "write-flash" in c]
    assert len(op_cmds) == 2
    assert "erase-flash" in op_cmds[0]
    assert "write-flash" in op_cmds[1]


def test_factory_flash_zephyr_assembly(tmp_path):
    build_dir = tmp_path / "esp_zephyr" / "app" / "build_v1"
    (build_dir / "mcuboot" / "zephyr").mkdir(parents=True)
    (build_dir / "app" / "zephyr").mkdir(parents=True)

    (build_dir / "mcuboot" / "zephyr" / "zephyr.bin").write_bytes(b"\x01" * 100)
    (build_dir / "app" / "zephyr" / "zephyr.signed.bin").write_bytes(b"\x02" * 100)

    executed_cmds = []

    def mock_runner(cmd, cwd=None):
        executed_cmds.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Wrote 100 bytes", stderr="")

    fl.factory_flash_zephyr("/dev/fake-port", repo_root=tmp_path, runner=mock_runner)
    assert len(executed_cmds) == 1
    cmd = executed_cmds[0]
    assert "esptool" in cmd[0]
    assert "write-flash" in cmd
    assert "0x0" in cmd
    assert "0x20000" in cmd


def test_recover_zephyr_erases_first(tmp_path):
    build_dir = tmp_path / "esp_zephyr" / "app" / "build_v1"
    (build_dir / "mcuboot" / "zephyr").mkdir(parents=True)
    (build_dir / "app" / "zephyr").mkdir(parents=True)

    (build_dir / "mcuboot" / "zephyr" / "zephyr.bin").write_bytes(b"\x01" * 100)
    (build_dir / "app" / "zephyr" / "zephyr.signed.bin").write_bytes(b"\x02" * 100)

    executed_cmds = []

    def mock_runner(cmd, cwd=None):
        executed_cmds.append(list(cmd))
        if "read-mac" in cmd or "read_mac" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="MAC: ac:a7:04:2c:3b:04", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

    fl.flash_board("zephyr", port="/dev/fake-port", recover=True, repo_root=tmp_path, runner=mock_runner)

    op_cmds = [c for c in executed_cmds if "erase-flash" in c or "write-flash" in c]
    assert len(op_cmds) == 2
    assert "erase-flash" in op_cmds[0]
    assert "write-flash" in op_cmds[1]
