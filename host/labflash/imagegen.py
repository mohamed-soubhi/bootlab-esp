"""BL-069: deterministic generator for the image pool (AC1, AC6).

Every parameter comes from a SHAKE-256 stream keyed by the seed, so a pool reproduces byte for byte on any Python
version and the tests can pin exact bytes. Nothing here draws from `random`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from labflash import imagefmt
from labflash.pinpolicy import SAFE_OUTPUT_PINS, check_pins

MAX_VALID_PAD = 2_500_000
ROLES = ("valid", "unaligned_trailer", "near_limit", "too_big")

BLINK_RANGE = (100, 1000)
TRAILER_RANGE = (1, 4095)
LED_MAX = 255
LED_FLOOR = 8                           # the firmware scales each channel /8, so a lower peak would read as off

_POOL_ROLES: tuple[str, ...] = (
    "valid", "valid", "valid", "unaligned_trailer", "valid", "valid",
    "near_limit", "valid", "valid", "unaligned_trailer", "valid", "valid", "too_big",
)
_POOL_MIN = len(_POOL_ROLES)
_SLICE = 8
_STREAM_LEN = 64

_OFF_PAD = 0
_OFF_BLINK = 8
_OFF_LED = 16
_OFF_PIN_A = 40
_OFF_PIN_B = 48
_OFF_TRAILER = 56


@dataclass(frozen=True)
class Variant:
    """One generated image: its padding, LED/pin parameters and target geometry."""

    seed: int
    role: str
    version: str
    pad_bytes: int
    blink_ms: int
    led_rgb: tuple[int, int, int]
    pins: tuple[int, int]
    trailer_len: int
    target_len: int | None


def pad_blob(seed: int, n: int) -> bytes:
    """n deterministic padding bytes; the stream ignores n, so a shorter result is a prefix of a longer one."""
    return hashlib.shake_256(f"pad:{seed}".encode()).digest(n)


def seed_for(seed_base: str, index: int) -> int:
    """The per-index seed a pool base implies."""
    return int.from_bytes(hashlib.sha256(f"{seed_base}:{index}".encode()).digest()[:8], "big")


def _stream(seed: int) -> bytes:
    """One stream per seed, sliced at fixed offsets so the fields stay independent."""
    return hashlib.shake_256(f"variant:{seed}".encode()).digest(_STREAM_LEN)


def _draw(stream: bytes, offset: int, lo: int, hi: int) -> int:
    return lo + int.from_bytes(stream[offset:offset + _SLICE], "big") % (hi - lo + 1)


def _draw_led(stream: bytes) -> tuple[int, int, int]:
    rgb = (
        _draw(stream, _OFF_LED, 0, LED_MAX),
        _draw(stream, _OFF_LED + _SLICE, 0, LED_MAX),
        _draw(stream, _OFF_LED + 2 * _SLICE, 0, LED_MAX),
    )
    return rgb if max(rgb) >= LED_FLOOR else (LED_FLOOR, LED_FLOOR, LED_FLOOR)


def _draw_pins(stream: bytes) -> tuple[int, int]:
    """Two distinct safe pins, in draw order."""
    pool = sorted(SAFE_OUTPUT_PINS)
    a = _draw(stream, _OFF_PIN_A, 0, len(pool) - 1)
    b = _draw(stream, _OFF_PIN_B, 0, len(pool) - 2)
    return pool[a], pool[b + 1 if b >= a else b]


def _target_len(role: str) -> int | None:
    if role == "near_limit":
        return imagefmt.SLOT_SIZE
    if role == "too_big":
        return imagefmt.SLOT_SIZE + imagefmt.SECTOR
    return None


def gen_variant(seed: int, role: str = "valid") -> Variant:
    """The variant a seed and role imply; the same pair always yields the same Variant."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}, expected one of {ROLES}")
    stream = _stream(seed)
    return Variant(
        seed=seed,
        role=role,
        version="gen-" + hashlib.sha256(str(seed).encode()).hexdigest()[:8],
        pad_bytes=_draw(stream, _OFF_PAD, 0, MAX_VALID_PAD) if role in {"valid", "unaligned_trailer"} else 0,
        blink_ms=_draw(stream, _OFF_BLINK, *BLINK_RANGE),
        led_rgb=_draw_led(stream),
        pins=_draw_pins(stream),
        trailer_len=_draw(stream, _OFF_TRAILER, *TRAILER_RANGE) if role == "unaligned_trailer" else 0,
        target_len=_target_len(role),
    )


def blink_hz(blink_ms: int) -> str:
    """The rate LABID reports: the LED toggles every blink_ms, so a full blink is 2 * blink_ms."""
    return f"{500 / blink_ms:.3f}"


def defaults_text(v: Variant) -> str:
    """The sdkconfig.defaults body for a variant: whitelisted keys only, no protected subsystem touched."""
    r, g, b = v.led_rgb
    pin_a, pin_b = check_pins(v.pins)
    return (
        "CONFIG_APP_GEN_POOL=y\n"
        "CONFIG_APP_REPRODUCIBLE_BUILD=y\n"
        f"CONFIG_APP_GEN_PAD_BYTES={v.pad_bytes}\n"
        f"CONFIG_APP_GEN_BLINK_MS={v.blink_ms}\n"
        f'CONFIG_APP_GEN_BLINK_HZ="{blink_hz(v.blink_ms)}"\n'
        f"CONFIG_APP_GEN_LED_R={r}\n"
        f"CONFIG_APP_GEN_LED_G={g}\n"
        f"CONFIG_APP_GEN_LED_B={b}\n"
        f"CONFIG_APP_GEN_PIN_A={pin_a}\n"
        f"CONFIG_APP_GEN_PIN_B={pin_b}\n"
    )


def gen_pool(seed_base: str, n: int = 13) -> list[Variant]:
    """n variants for seed_base; images beyond the 13 minimum are valid ones inserted before the oversized tail."""
    if n < _POOL_MIN:
        raise ValueError(f"pool size {n} is below the minimum of {_POOL_MIN}")
    roles = _POOL_ROLES[:-1] + ("valid",) * (n - _POOL_MIN) + (_POOL_ROLES[-1],)
    return [gen_variant(seed_for(seed_base, i), role) for i, role in enumerate(roles)]
