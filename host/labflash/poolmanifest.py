"""BL-069: the pool manifest — one JSON file describing every built image and what each transport must do (AC3).

A manifest is the run's contract: the index, the seed, the geometry and the expected verdicts for both transports.
`validate_manifest` re-checks that contract before a run trusts it, so a corrupt pool fails loudly instead of
quietly producing a false pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from labflash.imagefmt import SECTOR, SLOT_SIZE, fits_slot
from labflash.imagegen import Variant

SCHEMA = 1

_HEX = "0123456789abcdef"
_HEX_LEN = 64
_MIN_DISTINCT_SIZES = 8
_ACCEPT_ONLY_IF_ALIGNED = ("valid", "near_limit")
_TRANSPORTS = ("wifi", "ble")


class ManifestError(ValueError):
    """A manifest is malformed, inconsistent, or claims an outcome the image cannot have."""


def _verdict(accept: bool, reason: str) -> dict:
    return {"accept": accept, "reason": reason}


def expected_outcomes(role: str, trailer_len: int) -> dict:
    """What the device and the host each do with a role; every verdict carries a reason for the report."""
    if role == "valid":
        reason = "sector-aligned image fits the slot"
        return {"wifi": _verdict(True, reason), "ble": _verdict(True, reason)}
    if role == "near_limit":
        reason = "image within 64 KiB of the slot limit and still fits"
        return {"wifi": _verdict(True, reason), "ble": _verdict(True, reason)}
    if role == "unaligned_trailer":
        return {
            "wifi": _verdict(True, "bootloader never reads the bytes after the signature sector"),
            "ble": _verdict(False, f"{trailer_len}-byte trailer leaves the image not 4096-aligned"),
        }
    if role == "too_big":
        reason = "image is larger than the slot"
        return {"wifi": _verdict(False, reason), "ble": _verdict(False, reason)}
    raise ManifestError(f"unknown role {role!r}")


def make_entry(index: int, variant: Variant, file: str, data: bytes, signed_len: int) -> dict:
    """One manifest entry for a built image; its trailer must be the one the variant promised."""
    size = len(data)
    trailer_len = size - signed_len
    if trailer_len != variant.trailer_len:
        raise ManifestError(
            f"image {file} has a {trailer_len}-byte trailer, variant {variant.version} promises {variant.trailer_len}"
        )
    return {
        "index": index,
        "seed": variant.seed,
        "role": variant.role,
        "version": variant.version,
        "file": file,
        "size": size,
        "signed_len": signed_len,
        "trailer_len": trailer_len,
        "sha256": hashlib.sha256(data).hexdigest(),
        # RSA-PSS signatures are salted, so a rebuild differs inside the signature sector only; this hash covers
        # everything before it and is what "same seed, same image" means.
        "content_sha256": hashlib.sha256(data[: signed_len - SECTOR]).hexdigest(),
        "params": {
            "pad_bytes": variant.pad_bytes,
            "blink_ms": variant.blink_ms,
            "led_rgb": list(variant.led_rgb),
            "pins": list(variant.pins),
        },
        "expected": expected_outcomes(variant.role, trailer_len),
    }


def make_manifest(seed_base: str, entries: list[dict]) -> dict:
    """The manifest envelope for seed_base's pool."""
    return {"schema": SCHEMA, "seed_base": seed_base, "slot_size": SLOT_SIZE, "images": entries}


def _check_unique_field(images: list[dict], key: str) -> None:
    seen: set = set()
    for entry in images:
        value = entry.get(key)
        if value in seen:
            raise ManifestError(f"duplicate {key} {value!r}")
        seen.add(value)


def _check_sha256(entry: dict) -> None:
    for key in ("sha256", "content_sha256"):
        digest = entry.get(key)
        if not isinstance(digest, str) or len(digest) != _HEX_LEN or any(c not in _HEX for c in digest):
            raise ManifestError(f"{key} {digest!r} is not {_HEX_LEN} lowercase hex characters")


def _check_size(entry: dict) -> None:
    size = entry.get("size")
    if not isinstance(size, int) or isinstance(size, bool):
        raise ManifestError(f"size {size!r} is not an int")


def _check_indices(images: list[dict]) -> None:
    for position, entry in enumerate(images):
        if entry.get("index") != position:
            raise ManifestError(f"index {entry.get('index')!r} at position {position} is out of order")


def _check_expected(entry: dict, slot_size: int) -> None:
    role = entry.get("role")
    expected = entry.get("expected", {})
    if role == "too_big":
        if any(expected.get(t, {}).get("accept") for t in _TRANSPORTS):
            raise ManifestError(f"too_big image {entry.get('file')} claims an accept it cannot get")
        if fits_slot(entry["signed_len"] - SECTOR, slot_size):
            raise ManifestError(f"too_big image {entry.get('file')} of size {entry['size']} would fit the slot")
        return
    if role == "unaligned_trailer" and expected.get("ble", {}).get("accept"):
        raise ManifestError(f"unaligned_trailer image {entry.get('file')} claims a ble accept, the host refuses it")
    if role in _ACCEPT_ONLY_IF_ALIGNED and entry["size"] % SECTOR:
        raise ManifestError(
            f"image {entry.get('file')} of role {role} has size {entry['size']} which is not aligned to {SECTOR}"
        )
    if entry["size"] > slot_size:
        raise ManifestError(f"image {entry.get('file')} of size {entry['size']} exceeds the slot of {slot_size}")
    if role == "near_limit" and not fits_slot(entry["signed_len"] - SECTOR, slot_size):
        raise ManifestError(f"near_limit image {entry.get('file')} does not fit the slot")


def validate_manifest(m: dict, min_valid: int = 12) -> None:
    """Raise ManifestError unless m is a manifest a run can trust."""
    if m.get("schema") != SCHEMA:
        raise ManifestError(f"schema {m.get('schema')!r} is not {SCHEMA}")
    images = m.get("images")
    if not isinstance(images, list) or not images:
        raise ManifestError("images must be a non-empty list")
    _check_unique_field(images, "version")
    _check_unique_field(images, "file")
    for entry in images:
        _check_sha256(entry)
        _check_size(entry)
    _check_indices(images)
    slot_size = m.get("slot_size", SLOT_SIZE)
    for entry in images:
        _check_expected(entry, slot_size)
    usable = [e for e in images if e.get("role") != "too_big"]
    if len(usable) < min_valid:
        raise ManifestError(f"manifest has {len(usable)} non-too_big images, fewer than the {min_valid} required")
    distinct = len({e["size"] for e in usable})
    if distinct < _MIN_DISTINCT_SIZES:
        raise ManifestError(f"only {distinct} distinct image sizes among them, need a spread of {_MIN_DISTINCT_SIZES}")


def write_manifest(path: Path, m: dict) -> None:
    """Write a manifest as canonical JSON; an invalid manifest raises before the file exists."""
    validate_manifest(m)
    path.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict:
    """Read a manifest and refuse to return one that does not validate."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest
