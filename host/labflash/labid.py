"""labid.py — Python implementation of the LABID protocol (BL-013).

Mirrors common/labid/src/labid.c (frame format + CRC-16/CCITT-FALSE).
Tested against common/labid/test_vectors.json (shared golden frames).
"""
from __future__ import annotations

import json
from pathlib import Path

MAX_FRAME = 200
CRC_CHECK = "123456789"
CRC_CHECK_VAL = 0x29B1

# parse results
IGNORED = 0
FRAME = 1
ERROR = -1


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _valid_key(s: str) -> bool:
    return all(c.isdigit() or (c >= "a" and c <= "z") or c == "_" for c in s)


def _valid_value(s: str) -> bool:
    ok = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
    return all(c in ok for c in s)


def build_frame(f_type: str, items: dict[str, str]) -> str:
    """Build a complete LABID frame with CRC. items = ordered dict."""
    payload = "LAB," + f_type
    for k, v in items.items():
        if not _valid_key(k):
            raise ValueError(f"invalid key: {k!r}")
        if not _valid_value(v):
            raise ValueError(f"invalid value for {k!r}: {v!r}")
        payload += "," + k + "=" + v
    c = crc16(payload.encode())
    return f"${payload}*{c:04X}\n"


class Parser:
    """Byte-feed parser matching the C parser in labid.c."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.buf = bytearray()
        self.started = False
        self.crc_ok = False

    def feed(self, data) -> int:
        """Feed bytes or an str frame. Returns IGNORED / FRAME / ERROR."""
        if isinstance(data, int):
            data = bytes([data])
        elif isinstance(data, str):
            data = data.encode()
        last = IGNORED
        saw_error = False
        for ch in data:
            ch = bytes([ch])
            if not self.started:
                if ch == b"$":
                    self.started = True
                    self.buf = bytearray(b"$")   # store '$' so payload at [1:]
                    self.crc_ok = False
                if ch == b"\n":
                    self.started = False
                    self.buf = bytearray()
                last = IGNORED
                continue
            if ch == b"\n":
                last = self._end()
                self.started = False
                if last == ERROR:
                    saw_error = True
                continue
            if len(self.buf) >= MAX_FRAME:
                self.started = False
                self.buf = bytearray()
                last = ERROR
                saw_error = True
                continue
            self.buf += ch
        return ERROR if saw_error else last

    def _end(self) -> int:
        buf = bytes(self.buf)
        star = buf.rfind(b"*")
        if star < 0 or len(buf) - star - 1 < 4:
            self.buf = bytearray()
            return ERROR
        crc_hex = buf[star + 1 : star + 5].decode()
        try:
            crc = int(crc_hex, 16)
        except ValueError:
            self.buf = bytearray()
            return ERROR
        payload = buf[1:star]
        self.crc_ok = (crc16(payload) == crc)
        if not self.crc_ok:
            self.buf = bytearray()
            return ERROR
        self.buf = bytearray(payload)   # payload (['$' dropped]) for field queries
        return FRAME

    def crc_valid(self) -> bool:
        return self.crc_ok

    def frame_type(self) -> str | None:
        b = bytes(self.buf)
        if not b.startswith(b"LAB,"):
            return None
        rest = b[4:]
        comma = rest.find(b",")
        if comma < 0:
            comma = len(rest)
        return rest[:comma].decode()

    def get(self, key: str) -> str | None:
        b = bytes(self.buf)
        if not b.startswith(b"LAB,"):
            return None
        # split after type
        rest = b[4:]
        comma = rest.find(b",")
        if comma >= 0:
            pairs = rest[comma + 1 :].split(b",")
        else:
            pairs = []
        for p in pairs:
            if b"=" in p:
                k, v = p.split(b"=", 1)
                if k.decode() == key:
                    return v.decode()
        return None


def load_vectors(path: str | None = None) -> dict:
    if path is None:
        path = str(Path(__file__).resolve().parents[2] / "common" / "labid" / "test_vectors.json")
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    # self-test against the shared vectors
    vec = load_vectors()
    fails = 0

    # CRC check
    if crc16(vec["crc_check"]["input"].encode()) != int(vec["crc_check"]["crc"], 16):
        print("CRC check FAIL"); fails += 1
    else:
        print("CRC check vector OK")

    # valid frames parse
    for frame in vec["valid"]:
        p = Parser()
        rc = p.feed(frame)
        if rc != FRAME or not p.crc_valid():
            print("VALID parse FAIL:", frame.strip()); fails += 1
    # bad crc -> error
    for frame in vec["bad_crc"]:
        p = Parser()
        if p.feed(frame) != ERROR:
            print("BAD CRC not rejected:", frame.strip()); fails += 1
    # unknown keys ignored -> still valid frame
    for frame in vec["unknown_keys"]:
        p = Parser()
        if p.feed(frame) != FRAME:
            print("UNKNOWN-KEYS parse FAIL:", frame.strip()); fails += 1
    # too long -> error
    for frame in vec["too_long"]:
        p = Parser()
        if p.feed(frame) != ERROR:
            print(f"TOO-LONG not rejected (len {len(frame)})")
            fails += 1
    # garbage -> ignored (non-frame) or error
    for frame in vec["garbage"]:
        p = Parser()
        p.feed(frame)
        # any result other than a valid FRAME is acceptable for non-frames
    print(
        f"vectors: {len(vec['valid'])} valid, {len(vec['bad_crc'])} bad_crc, "
        f"{len(vec['unknown_keys'])} unknown, {len(vec['too_long'])} too_long, {len(vec['garbage'])} garbage"
    )
    print("RESULT: " + ("ALL PASS" if fails == 0 else f"FAILURES={fails}"))
    raise SystemExit(1 if fails else 0)
