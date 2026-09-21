"""Unit tests for host/labflash/labid.py (BL-013 / BL-046)."""
from pathlib import Path

import pytest
from labflash import labid


def test_build_frame_valid():
    frame = labid.build_frame("ANNOUNCE", {"uid": "112233445566", "board": "idf"})
    assert frame.startswith("$LAB,ANNOUNCE,")
    assert "*\n" not in frame
    assert frame.endswith("\n")


def test_build_frame_invalid_key():
    with pytest.raises(ValueError, match="invalid key"):
        labid.build_frame("ANNOUNCE", {"invalid key!": "val"})


def test_build_frame_invalid_val():
    with pytest.raises(ValueError, match="invalid value"):
        labid.build_frame("ANNOUNCE", {"key": "val,with,comma"})


def test_parser_with_shared_vectors():
    vec_path = Path(__file__).resolve().parents[2] / "common" / "labid" / "test_vectors.json"
    if not vec_path.exists():
        pytest.skip("common/labid/test_vectors.json not found")
    vec = labid.load_vectors(str(vec_path))

    for frame in vec["valid"]:
        p = labid.Parser()
        res = p.feed(frame)
        assert res == labid.FRAME
        assert p.crc_valid() is True
        assert p.frame_type() is not None

    for frame in vec["bad_crc"]:
        p = labid.Parser()
        res = p.feed(frame)
        assert res == labid.ERROR

    for frame in vec["too_long"]:
        p = labid.Parser()
        res = p.feed(frame)
        assert res == labid.ERROR


def test_parser_feed_int_and_str():
    p = labid.Parser()
    valid_frame = labid.build_frame("ID", {"uid": "1234"})
    assert p.feed(ord(valid_frame[0])) == labid.IGNORED
    assert p.feed(valid_frame[1:]) == labid.FRAME
    assert p.get("uid") == "1234"
    assert p.get("missing") is None


def test_parser_frame_type_edge_cases():
    p = labid.Parser()
    p.buf = bytearray(b"NOT_LAB")
    assert p.frame_type() is None
    assert p.get("uid") is None

    p.buf = bytearray(b"LAB,SIMPLE")
    assert p.frame_type() == "SIMPLE"
    assert p.get("uid") is None


def test_parser_crc_edge_cases():
    p = labid.Parser()
    assert p.feed(b"$LAB,ID*12\n") == labid.ERROR

    p.reset()
    assert p.feed(b"$LAB,ID*ZZZZ\n") == labid.ERROR


def test_load_vectors_default():
    vec = labid.load_vectors()
    assert "valid" in vec
