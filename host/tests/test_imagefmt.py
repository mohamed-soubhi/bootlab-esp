"""BL-069: signed-image geometry, trailer, device-signature check. Owner: Claude."""
import subprocess
from pathlib import Path

import pytest
from labflash import build as bld
from labflash import imagefmt as fmt

V1_END = 1_245_184          # v1 image data end (facts pinned in the plan)
V1_FILE = 1_249_280         # 305 sectors


def test_constants():
    assert fmt.SECTOR == 4096
    assert fmt.SLOT_SIZE == 4 * 1024 * 1024


@pytest.mark.parametrize("n,want", [(0, 0), (1, 4096), (4096, 4096), (4097, 8192), (V1_END, V1_END)])
def test_align_up(n, want):
    assert fmt.align_up(n) == want


def test_sig_block_offset_and_signed_len():
    assert fmt.sig_block_offset(V1_END) == V1_END
    assert fmt.sig_block_offset(V1_END + 1) == V1_END + 4096
    assert fmt.signed_len_from_data_end(V1_END) == V1_FILE


def test_fits_slot_boundary():
    assert fmt.fits_slot(4_190_208)          # file == slot size exactly
    assert not fmt.fits_slot(4_190_209)
    assert fmt.fits_slot(V1_END)


def test_append_trailer_properties():
    signed = b"\xE9" * 8192
    out = fmt.append_trailer(signed, 100, seed=7)
    assert len(out) == 8192 + 100 and out[:8192] == signed
    assert out == fmt.append_trailer(signed, 100, seed=7)
    assert out != fmt.append_trailer(signed, 100, seed=8)
    assert fmt.append_trailer(signed, 0, seed=7) == signed


@pytest.mark.parametrize("n", [-1, 4096, 8192])
def test_append_trailer_rejects_bad_length(n):
    with pytest.raises(ValueError):
        fmt.append_trailer(b"\0" * 4096, n, seed=1)


def test_append_trailer_rejects_unaligned_input():
    with pytest.raises(ValueError):
        fmt.append_trailer(b"\0" * 4097, 5, seed=1)


def test_strip_trailer():
    signed = b"A" * 8192
    assert fmt.strip_trailer(signed + b"tail", 8192) == signed
    with pytest.raises(ValueError):
        fmt.strip_trailer(signed, 8193)          # not a sector multiple
    with pytest.raises(ValueError):
        fmt.strip_trailer(signed, 12288)         # longer than the image


def test_verify_device_signature_hands_espsecure_only_the_signed_part(tmp_path):
    signed = b"S" * 8192
    image = signed + b"TRAILER"
    seen = {}

    def runner(cmd, cwd=None):
        seen["cmd"] = list(cmd)
        seen["bytes"] = Path(cmd[-1]).read_bytes()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    key = tmp_path / "k.pem"
    key.write_text("K")
    assert fmt.verify_device_signature(image, 8192, key, runner=runner) is True
    assert seen["bytes"] == signed
    assert str(key) in seen["cmd"] and "-v" in seen["cmd"] and "2" in seen["cmd"]


def test_verify_device_signature_false_when_espsecure_fails(tmp_path):
    key = tmp_path / "k.pem"
    key.write_text("K")
    runner = lambda cmd, cwd=None: subprocess.CompletedProcess(cmd, 1, "", "bad")
    assert fmt.verify_device_signature(b"S" * 4096, 4096, key, runner=runner) is False


def test_trailer_module_reuses_build_verify(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(bld, "verify_signature", lambda p, k, runner=None: called.setdefault("ok", True))
    key = tmp_path / "k.pem"
    key.write_text("K")
    assert fmt.verify_device_signature(b"S" * 4096, 4096, key) is True
    assert called
