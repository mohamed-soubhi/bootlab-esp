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


def test_hard_reset_toggles_the_lines_on_the_already_open_handle(tmp_path):
    """A second open of the same COM port is refused on Windows, so a reset must reuse the shared handle."""
    events = []

    class Recorder:
        in_waiting = 0

        def read(self, _n):
            raise OSError("port gone")

        def __setattr__(self, name, value):
            if name in ("dtr", "rts"):
                events.append((name, value))
            object.__setattr__(self, name, value)

    rec = Recorder()
    with patch("serial.Serial", return_value=MagicMock(read=rec.read, in_waiting=0)) as factory:
        port = SharedConsolePort("COM14", console_log=tmp_path / "c.log")
        port._thread.join(timeout=2.0)
        port._ser = rec
        opens_before = factory.call_count
        slept = []
        port.hard_reset(hold_s=0.2, sleep=slept.append)
        assert factory.call_count == opens_before                     # no new serial.Serial was constructed
    assert events == [("dtr", True), ("rts", False), ("dtr", False), ("rts", True), ("dtr", False), ("rts", False)]
    assert slept == [0.2, 0.2, 0.1]
