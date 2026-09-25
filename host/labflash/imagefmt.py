"""BL-069: signed ESP-IDF app image geometry, the post-signature trailer, and the device-side signature check.

espsecure pads the data to a 4096 multiple and appends one whole 4096-byte signature sector, so a signed image is
always sector-aligned. The bootloader reads only [:ALIGN_UP(end)) plus the signature block, so bytes appended after
the signature sector are never read: a trailer is the only way to make a valid image whose size is not a 4096
multiple. `espsecure verify-signature` refuses such a file, so the trailer is stripped before verifying.
"""
from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from pathlib import Path

from labflash import build

SECTOR = 4096
SLOT_SIZE = 4 * 1024 * 1024
SIG_BLOCK_LEN = 1216        # bytes of the signature block the bootloader checks fit (esp_image_format.c)


def align_up(n: int, to: int = SECTOR) -> int:
    return -(-n // to) * to


def sig_block_offset(data_end: int) -> int:
    """Offset of the signature sector for an image whose data ends at data_end."""
    return align_up(data_end)


def signed_len_from_data_end(data_end: int) -> int:
    return sig_block_offset(data_end) + SECTOR


def fits_slot(data_end: int, slot_size: int = SLOT_SIZE) -> bool:
    """The bootloader's acceptance rule: ALIGN_UP(end) + signature block <= partition length."""
    return align_up(data_end) + SIG_BLOCK_LEN <= slot_size


def append_trailer(signed: bytes, n: int, seed: int) -> bytes:
    """Append n deterministic bytes after the signature sector (n must not be a sector multiple)."""
    if len(signed) % SECTOR:
        raise ValueError(f"signed image length {len(signed)} is not a multiple of {SECTOR}")
    if n < 0 or (n and n % SECTOR == 0):
        raise ValueError(f"trailer length {n} must be >= 0 and not a multiple of {SECTOR}")
    if n == 0:
        return signed
    return signed + hashlib.shake_256(f"trailer:{seed}".encode()).digest(n)


def strip_trailer(image: bytes, signed_len: int) -> bytes:
    if signed_len % SECTOR or signed_len > len(image):
        raise ValueError(f"signed_len {signed_len} invalid for a {len(image)}-byte image")
    return image[:signed_len]


def verify_device_signature(image: bytes, signed_len: int, key_path: Path,
                            runner: Callable | None = None) -> bool:
    """True if the signed part of image verifies against key_path, ignoring any trailer (what the device sees)."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "signed.bin"
        f.write_bytes(strip_trailer(image, signed_len))
        return build.verify_signature(f, key_path, runner=runner)
