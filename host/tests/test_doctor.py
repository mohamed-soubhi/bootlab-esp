"""Unit tests for host/labflash/doctor.py (BL-007 / BL-046)."""
from unittest.mock import MagicMock, patch

from labflash import doctor


def test_check_esp_usb():
    p1 = MagicMock(vid=0x303A)
    p2 = MagicMock(vid=0x1234)
    p3 = MagicMock(vid=0x303A)
    with patch("serial.tools.list_ports.comports", return_value=[p1, p2, p3]):
        count, extra = doctor.check_esp_usb()
        assert count == 2
        assert extra == ""


def test_check_bt_not_testable():
    with patch("shutil.which", return_value=None):
        status, testable = doctor.check_bt()
        assert status is False
        assert testable is False


def test_check_bt_hciconfig():
    def fake_which(cmd):
        return "/usr/bin/" + cmd if cmd == "hciconfig" else None

    proc = MagicMock(stdout="hci0: Type: Primary Bus: USB\n")
    with patch("shutil.which", side_effect=fake_which), patch("subprocess.run", return_value=proc):
        status, testable = doctor.check_bt()
        assert status is True
        assert testable is True


def test_check_bt_bluetoothctl():
    def fake_which(cmd):
        return "/usr/bin/" + cmd if cmd == "bluetoothctl" else None

    proc_hci = MagicMock(stdout="")
    proc_bt = MagicMock(stdout="Controller 00:11:22:33:44:55 name [default]\n")
    with patch("shutil.which", side_effect=fake_which), patch("subprocess.run", side_effect=[proc_hci, proc_bt]):
        status, testable = doctor.check_bt()
        assert status is True
        assert testable is True


def test_check_wifi_wlan_iface():
    with patch("shutil.which", return_value=None), patch("os.listdir", return_value=["lo", "eth0", "wlan0"]):
        status, testable = doctor.check_wifi()
        assert status is True
        assert testable is True


def test_check_wifi_nmcli():
    with patch("shutil.which", return_value="/usr/bin/nmcli"), patch("os.listdir", side_effect=OSError):
        proc = MagicMock(stdout="wifi:wlan0\n")
        with patch("subprocess.run", return_value=proc):
            status, testable = doctor.check_wifi()
            assert status is True
            assert testable is True


def test_check_wifi_not_testable():
    with patch("shutil.which", return_value=None), patch("os.listdir", return_value=["lo", "eth0"]):
        status, testable = doctor.check_wifi()
        assert status is False
        assert testable is False


def test_fmt():
    assert doctor._fmt(True, True) == "OK"
    assert doctor._fmt(False, True) == "MISSING"
    assert "not testable" in doctor._fmt(False, False)


def test_main_all_ok(capsys):
    with patch("labflash.doctor.check_esp_usb", return_value=(2, "")), \
         patch("labflash.doctor.check_bt", return_value=(True, True)), \
         patch("labflash.doctor.check_wifi", return_value=(True, True)):
        rc = doctor.main()
        out = capsys.readouterr().out
        assert rc == 0
        assert "ALL OK" in out


def test_main_missing_esp(capsys):
    with patch("labflash.doctor.check_esp_usb", return_value=(1, "")), \
         patch("labflash.doctor.check_bt", return_value=(False, False)), \
         patch("labflash.doctor.check_wifi", return_value=(False, False)):
        rc = doctor.main()
        out = capsys.readouterr().out
        assert rc == 1
        assert "MISSING ITEMS" in out
