"""Unit tests for host/labflash/identify.py and CLI handlers (BL-041)."""
import pytest
from labflash import identify as idf
from labflash.labid import build_frame


class MockTransport:
    """Mock serial transport for LABID protocol tests."""

    def __init__(self, responses: dict[str, tuple[str, dict[str, str]]] | None = None):
        self.responses = responses or {}
        self.write_buf = bytearray()
        self.read_buf = bytearray()

    def write(self, data: bytes) -> None:
        self.write_buf.extend(data)
        for req, (f_type, items) in self.responses.items():
            if req.encode() in data:
                frame = build_frame(f_type, items)
                self.read_buf.extend(frame.encode())

    def read1(self) -> bytes:
        if self.read_buf:
            b = self.read_buf[0:1]
            del self.read_buf[0:1]
            return bytes(b)
        return b""

    def close(self) -> None:
        pass


def test_identify_query():
    t = MockTransport({"ID?": ("ID", {"board": "idf", "uid": "e072a1aa2390", "chip": "esp32s3", "mac": "e0:72:a1:aa:23:90"})})
    fields = idf.identify(t)
    assert fields["board"] == "idf"
    assert fields["uid"] == "e072a1aa2390"
    assert fields["chip"] == "esp32s3"


def test_get_version_query():
    t = MockTransport({"VER?": ("VER", {"app": "1.0.0", "git": "1.0.0", "slot": "0", "confirmed": "true"})})
    fields = idf.get_version(t)
    assert fields["app"] == "1.0.0"
    assert fields["slot"] == "0"
    assert fields["confirmed"] == "true"


def test_get_state_query():
    t = MockTransport({"STATE?": ("STATE", {"state": "RUN", "toggles": "120", "blink_hz": "1.0", "color": "green"})})
    fields = idf.get_state(t)
    assert fields["state"] == "RUN"
    assert fields["toggles"] == "120"
    assert fields["blink_hz"] == "1.0"


def test_query_info():
    t = MockTransport({
        "ID?": ("ID", {"board": "idf", "uid": "e072a1aa2390", "chip": "esp32s3"}),
        "VER?": ("VER", {"app": "1.0.0", "slot": "0", "confirmed": "true"}),
        "STATE?": ("STATE", {"state": "RUN", "toggles": "50", "blink_hz": "1.0"}),
    })
    info = idf.query_info(t)
    assert info["id"]["uid"] == "e072a1aa2390"
    assert info["version"]["app"] == "1.0.0"
    assert info["state"]["toggles"] == "50"


def test_cross_check_identity():
    # Pass case
    idf.cross_check_identity({"uid": "e072a1aa2390"}, {"mac": "e0:72:a1:aa:23:90"})
    # Fail case
    with pytest.raises(idf.LabidError, match="identity mismatch"):
        idf.cross_check_identity({"uid": "e072a1aa2390"}, {"mac": "ac:a7:04:2c:3b:04"})


def test_map_board_by_id():
    rig = {
        "boards": {
            "idf": {"mac": "E0:72:A1:AA:23:90"},
            "zephyr": {"mac": "AC:A7:04:2C:3B:04"},
        }
    }
    t = MockTransport({"ID?": ("ID", {"board": "idf", "uid": "e072a1aa2390"})})
    bname, fields = idf.map_board_by_id(t, rig=rig)
    assert bname == "idf"
    assert fields["uid"] == "e072a1aa2390"

    t_unknown = MockTransport({"ID?": ("ID", {"board": "unknown", "uid": "112233445566"})})
    with pytest.raises(idf.LabidError, match="matches no board in rig.yaml"):
        idf.map_board_by_id(t_unknown, rig=rig)


def test_measure(monkeypatch):
    class StepTransport:
        def close(self): pass

    toggles = [100, 110]
    times = [10.0, 15.0]

    monkeypatch.setattr(idf, "get_state", lambda t: {"toggles": str(toggles.pop(0))})
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("time.monotonic", lambda: times.pop(0))

    delta, hz, ok = idf.measure(StepTransport(), duration_s=5.0, expect_hz=1.0, tolerance_toggles=1)
    assert delta == 10
    assert hz == 1.0
    assert ok is True


def test_serial_line_transport():
    from unittest.mock import MagicMock, patch
    mock_ser = MagicMock()
    mock_ser.read.return_value = b"X"
    with patch("serial.Serial", return_value=mock_ser):
        trans = idf.SerialLineTransport("/dev/ttyACM0")
        assert trans.read1() == b"X"
        trans.write(b"ABC")
        mock_ser.write.assert_called_once_with(b"ABC")
        trans.close()
        mock_ser.close.assert_called_once()


def test_wait_for_announce():
    t = MockTransport()
    t.read_buf.extend(build_frame("ANNOUNCE", {"uid": "1234", "board": "idf"}).encode())
    ann = idf.wait_for_announce(t, timeout=0.1)
    assert ann["uid"] == "1234"


def test_wait_for_announce_timeout():
    t = MockTransport()
    with pytest.raises(idf.LabidError, match="no ANNOUNCE frame"):
        idf.wait_for_announce(t, timeout=0.05)


def test_query_error_response():
    t = MockTransport({"BAD?": ("ERR", {"reason": "bad_command"})})
    with pytest.raises(idf.LabidError, match="device returned ERR"):
        idf.query(t, "BAD?", timeout=0.1)


def test_query_timeout():
    t = MockTransport()
    with pytest.raises(idf.LabidError, match="no response"):
        idf.query(t, "NOOP?", timeout=0.05)

