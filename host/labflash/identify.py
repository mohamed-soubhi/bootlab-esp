"""labflash identify — LABID discovery, ID/VER/STATE queries, toggle-rate
measurement, and cross-check against rig.yaml (BL-041).

Protocol per PLAN.md Sec 7.3. This module is transport-agnostic: any
object exposing read1()/write(bytes) works, so it can be driven by a
real serial.Serial or a mock for testing without live firmware.
"""
from __future__ import annotations

import time
from typing import Protocol

from labflash.labid import ERROR, FRAME, Parser

ANNOUNCE_WINDOW_S = 2.0     # protocol: device announces once per boot, <= 2s
QUERY_TIMEOUT_S = 0.5       # protocol: response <= 100ms; generous margin for host overhead


class LabidError(RuntimeError):
    """Raised on a LABID-level failure (timeout, ERR frame, cross-check mismatch)."""


class Transport(Protocol):
    def read1(self) -> bytes: ...   # one byte, or b"" if none available right now
    def write(self, data: bytes) -> None: ...


class SerialLineTransport:
    """Real Transport backed by a pyserial connection to a resolved board port.

    Untested against real hardware as of BL-041 -- no board runs LABID
    firmware yet (see BL-020/BL-022). Provided so the real path exists
    once that firmware lands, rather than only having a mock.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.02):
        import serial
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = timeout
        # Hold DTR/RTS inactive BEFORE opening: on the ESP32-S3 USB-Serial-JTAG
        # an asserting open can toggle reset/boot lines (PLAN R14).
        ser.dtr = False
        ser.rts = False
        ser.open()
        self._ser = ser
        self._buf = bytearray()

    def read1(self) -> bytes:
        if not self._buf:
            waiting = getattr(self._ser, "in_waiting", 0)
            n = waiting if isinstance(waiting, int) and waiting > 0 else 1
            chunk = self._ser.read(n)
            if chunk:
                self._buf.extend(chunk)
        if self._buf:
            return bytes([self._buf.pop(0)])
        return b""

    def write(self, data: bytes) -> None:
        self._ser.write(data)
        self._ser.flush()

    def close(self) -> None:
        self._ser.close()


def _parse_fields(parser: Parser) -> dict:
    """Extract all key=value pairs from the parser's currently-held frame."""
    b = bytes(parser.buf)
    if not b.startswith(b"LAB,"):
        return {}
    rest = b[4:]
    comma = rest.find(b",")
    pairs = rest[comma + 1:].split(b",") if comma >= 0 else []
    out = {}
    for p in pairs:
        if b"=" in p:
            k, v = p.split(b"=", 1)
            out[k.decode()] = v.decode()
    return out


def _read_frame(transport: Transport, deadline: float) -> tuple[str, dict] | None:
    """Read bytes until one full frame is parsed, or the deadline passes."""
    parser = Parser()
    while time.monotonic() < deadline:
        try:
            b = transport.read1()
        except Exception:  # noqa: BLE001
            return None
        if not b:
            time.sleep(0.005)
            continue
        rc = parser.feed(b)
        if rc == FRAME:
            ft = parser.frame_type()
            if ft is not None:
                return ft, _parse_fields(parser)
        if rc == ERROR:
            parser.reset()
    return None


def wait_for_announce(transport: Transport, timeout: float = ANNOUNCE_WINDOW_S) -> dict:
    """Wait for the device's boot-time ANNOUNCE frame. Raises LabidError on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _read_frame(transport, deadline)
        if result is None:
            break
        frame_type, fields = result
        if frame_type == "ANNOUNCE":
            return fields
    raise LabidError(f"no ANNOUNCE frame within {timeout:.1f}s")


def query(transport: Transport, request: str, timeout: float = QUERY_TIMEOUT_S) -> dict:
    """Send a host->device request (e.g. 'ID?') and return the response fields.

    Raises LabidError on timeout or if the device responds with ERR.
    """
    transport.write(f"$LAB,{request}\n".encode())
    deadline = time.monotonic() + timeout
    result = _read_frame(transport, deadline)
    if result is None:
        raise LabidError(f"no response to {request!r} within {timeout:.1f}s")
    frame_type, fields = result
    if frame_type == "ERR":
        raise LabidError(f"device returned ERR for {request!r}: {fields}")
    return fields


def identify(transport: Transport) -> dict:
    return query(transport, "ID?")


def get_version(transport: Transport) -> dict:
    return query(transport, "VER?")


def get_state(transport: Transport) -> dict:
    return query(transport, "STATE?")


def cross_check_identity(id_fields: dict, expected: dict) -> None:
    """Raise LabidError if the device's self-reported ID doesn't match rig.yaml.

    expected: {"mac": "...", "board_name": "..."} from rig.yaml's board entry.
    ID.uid is 12 hex chars with no separators; rig.yaml's mac has colons.
    """
    expected_uid = str(expected.get("mac", "")).replace(":", "").lower()
    actual_uid = str(id_fields.get("uid", "")).lower()
    if actual_uid != expected_uid:
        raise LabidError(
            f"identity mismatch: device reports uid={actual_uid!r}, "
            f"rig.yaml expects {expected_uid!r} for this board"
        )


def query_info(transport: Transport) -> dict:
    """Query ID, VER, and STATE, returning combined dictionary."""
    id_fields = identify(transport)
    ver_fields = get_version(transport)
    state_fields = get_state(transport)
    return {
        "id": id_fields,
        "version": ver_fields,
        "state": state_fields,
    }


def map_board_by_id(transport: Transport, rig: dict | None = None) -> tuple[str, dict]:
    """Identify the board on this transport and match it against rig.yaml.

    Returns (board_key, id_fields).
    """
    from labflash.core import load_rig_config
    rig = rig if rig is not None else load_rig_config()
    id_fields = identify(transport)
    actual_uid = str(id_fields.get("uid", "")).replace(":", "").lower()

    for board_key, bcfg in rig.get("boards", {}).items():
        expected_uid = str(bcfg.get("mac", "")).replace(":", "").lower()
        if actual_uid == expected_uid:
            return board_key, id_fields

    raise LabidError(f"Device reports uid {actual_uid}, which matches no board in rig.yaml")


def measure(
    transport: Transport,
    duration_s: float = 5.0,
    expect_hz: float | None = None,
    tolerance_toggles: int = 1,
) -> tuple[int, float, bool]:
    """Measure toggle delta over duration_s and compute frequency.

    Returns (toggle_delta, measured_hz, passed).
    """
    t0 = time.monotonic()
    s0 = get_state(transport)
    start_toggles = int(s0["toggles"])
    time.sleep(duration_s)
    t1 = time.monotonic()
    s1 = get_state(transport)
    end_toggles = int(s1["toggles"])

    elapsed = t1 - t0
    delta = end_toggles - start_toggles
    hz = (delta / elapsed) / 2.0 if elapsed > 0 else 0.0

    passed = True
    if expect_hz is not None:
        expected_toggles = round(expect_hz * elapsed * 2.0)
        passed = abs(delta - expected_toggles) <= tolerance_toggles

    return delta, hz, passed
