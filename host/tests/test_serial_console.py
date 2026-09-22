"""Unit tests for labflash.serial_console.SharedConsolePort (BL-060 follow-up).

No hardware: serial.Serial is mocked. Verifies the reader thread tees every raw line (including
non-LABID ESP_LOG console text) to console.log while still forwarding the same bytes through
read1() for the LABID frame parser, that write() passes through to the mocked port, and that
close() is a no-op while shutdown() actually releases the port.
"""
from unittest.mock import MagicMock, patch

from labflash.serial_console import SharedConsolePort


def _mock_serial(chunks: list[bytes]):
    """A serial.Serial double that yields `chunks` once each, then raises (simulating the port
    disappearing) so the reader thread's loop exits on its own without a test-time sleep/timeout."""
    mock_ser = MagicMock()
    mock_ser.in_waiting = 0
    remaining = list(chunks)

    def fake_read(_n):
        if remaining:
            return remaining.pop(0)
        raise OSError("port gone")

    mock_ser.read.side_effect = fake_read
    return mock_ser


def test_tees_console_lines_and_forwards_bytes_via_read1(tmp_path):
    console_log = tmp_path / "console.log"
    mock_ser = _mock_serial([b"I (1234) wifi: connected\n", b"$LAB,VER?*AB\n"])
    with patch("serial.Serial", return_value=mock_ser):
        port = SharedConsolePort("/dev/ttyACM0", console_log=console_log)
        port._thread.join(timeout=2.0)
        assert not port._thread.is_alive()

        collected = bytearray()
        while True:
            b = port.read1()
            if not b:
                break
            collected.extend(b)
        assert collected == b"I (1234) wifi: connected\n$LAB,VER?*AB\n"

    text = console_log.read_text(encoding="utf-8")
    assert "I (1234) wifi: connected" in text
    assert "$LAB,VER?*AB" in text
    # timestamped: "[HH:MM:SS.mmm] ..."
    assert text.splitlines()[0].startswith("[")


def test_write_passes_through_to_serial(tmp_path):
    mock_ser = _mock_serial([])
    with patch("serial.Serial", return_value=mock_ser):
        port = SharedConsolePort("/dev/ttyACM0", console_log=tmp_path / "console.log")
        port._thread.join(timeout=2.0)
        port.write(b"$LAB,ID?*00\n")
    mock_ser.write.assert_called_once_with(b"$LAB,ID?*00\n")
    mock_ser.flush.assert_called_once()


def test_close_is_a_noop_shutdown_actually_releases(tmp_path):
    mock_ser = _mock_serial([])
    with patch("serial.Serial", return_value=mock_ser):
        port = SharedConsolePort("/dev/ttyACM0", console_log=tmp_path / "console.log")
        port._thread.join(timeout=2.0)

        port.close()
        mock_ser.close.assert_not_called()

        port.shutdown()
        mock_ser.close.assert_called_once()


def test_no_console_log_disables_tee_but_still_forwards_bytes(tmp_path):
    mock_ser = _mock_serial([b"hello\n"])
    with patch("serial.Serial", return_value=mock_ser):
        port = SharedConsolePort("/dev/ttyACM0")   # console_log=None
        port._thread.join(timeout=2.0)
        collected = bytearray()
        while True:
            b = port.read1()
            if not b:
                break
            collected.extend(b)
        assert collected == b"hello\n"
        port.shutdown()
