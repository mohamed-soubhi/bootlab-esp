"""BL-069: which ESP32-S3 GPIOs a generated image may drive (AC4).

Source: the Espressif ESP32-S3-DevKitC-1 user guide pin tables (rig boards are unmodified DevKitC-1 v1.0,
N16R8: 16 MB quad flash, 8 MB octal PSRAM). Safe pins are header-only GPIOs with no on-board function.

Generated images toggle two spare output pins. Every GPIO is either in SAFE_OUTPUT_PINS or in exactly one
EXCLUDED_PIN_GROUPS entry with the reason it is off limits; the generator refuses anything else. The ESP32-S3 has
GPIO0-21 and GPIO26-48 (22-25 do not exist). Keep docs/BL069_IMAGE_POOL.md in step (a test enforces it).
"""
from __future__ import annotations

from collections.abc import Iterable

SAFE_OUTPUT_PINS: frozenset[int] = frozenset({1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 47})

EXCLUDED_PIN_GROUPS: dict[str, tuple[frozenset[int], str]] = {
    "strapping": (frozenset({0, 3, 45, 46}),
                  ("sampled at reset: boot mode (GPIO0, GPIO46), JTAG source (GPIO3), VDD_SPI voltage (GPIO45); "
                  "an external load can change how the board boots")),
    "usb_serial_jtag": (frozenset({19, 20}),
                        "USB D-/D+ pins carrying the LABID serial console and USB-Serial-JTAG; driving them drops the link"),
    "uart0_console": (frozenset({43, 44}),
                      "UART0 TX/RX: ROM boot log and download-mode console"),
    "status_led": (frozenset({48}),
                   "on-board WS2812 status LED driven by the application itself"),
    "spi_flash_psram": (frozenset(range(26, 38)),
                        ("GPIO26-32 are the SPI flash/PSRAM bus, GPIO33-37 the octal flash/PSRAM lines on some modules; "
                        "driving them corrupts code fetch")),
    "jtag_mtxx": (frozenset({39, 40, 41, 42}),
                  "MTCK/MTDO/MTDI/MTMS pad group: the JTAG pins, kept free for a debugger"),
    "rgb_led_alt": (frozenset({38}),
                    ("WS2812 status LED on GPIO38 in DevKitC-1 v1.1 (GPIO48 in v1.0, which this rig is); "
                     "kept off so the allowlist holds for either revision")),
}


class PinNotAllowedError(ValueError):
    """A pin outside SAFE_OUTPUT_PINS was requested."""


def _reason(pin: int) -> str:
    for name, (pins, why) in EXCLUDED_PIN_GROUPS.items():
        if pin in pins:
            return f"group {name}: {why}"
    return "not an ESP32-S3 GPIO"


def check_pins(pins: Iterable[int]) -> tuple[int, ...]:
    """Return the pins as a tuple, or raise PinNotAllowedError naming the first offender and why."""
    out = tuple(pins)
    for pin in out:
        if pin not in SAFE_OUTPUT_PINS:
            raise PinNotAllowedError(f"GPIO{pin} refused: {_reason(pin)}")
    return out
