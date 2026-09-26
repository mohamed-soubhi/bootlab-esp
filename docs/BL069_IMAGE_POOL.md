# BL-069 — signed image pool

## 1. Purpose

BL-067's randomized soak has to show that the board accepts arbitrary code in either OTA slot, not only the two
fixed v1/v2 binaries. BL-069 builds a pool of valid, signed ESP-IDF images whose footprint, LED colour, blink
frequency and toggled pins all differ from v1/v2, so both slots are exercised with images of many sizes.
The pool is built offline in WSL, where the toolchain and the board's signing key live, and never inside a soak
run, so a compile or signing error cannot be mistaken for an OTA failure. The soak consumes the pool only through
the manifest described in section 4.

The generator (`host/labflash/imagegen.py`) takes every parameter from a SHAKE-256 stream keyed by the seed, so the
same seed reproduces the same parameters and the same image sha256; nothing draws from `random`.

## 2. Pin allowlist

Generated images toggle two spare output pins. A pin is usable only if it is in `SAFE_OUTPUT_PINS`
(`host/labflash/pinpolicy.py`); `check_pins` refuses anything else with a `PinNotAllowedError` that names the group
and its reason. Excluded groups, with the reason each pin is off limits:

| Group | GPIOs | Reason |
|-------|-------|--------|
| strapping | GPIO0, GPIO3, GPIO45, GPIO46 | sampled at reset: boot mode (GPIO0, GPIO46), JTAG source (GPIO3), VDD_SPI voltage (GPIO45); an external load can change how the board boots |
| usb_serial_jtag | GPIO19, GPIO20 | USB D-/D+ pins carrying the LABID serial console and USB-Serial-JTAG; driving them drops the link |
| uart0_console | GPIO43, GPIO44 | UART0 TX/RX: ROM boot log and download-mode console |
| status_led | GPIO48 | on-board WS2812 status LED driven by the application itself |
| spi_flash_psram | GPIO26-GPIO37 | GPIO26-32 are the SPI flash/PSRAM bus, GPIO33-37 the octal flash/PSRAM lines on some modules; driving them corrupts code fetch |
| jtag_mtxx | GPIO39, GPIO40, GPIO41, GPIO42 | MTCK/MTDO/MTDI/MTMS pad group: the JTAG pins, kept free for a debugger |
| rgb_led_alt | GPIO38 | WS2812 status LED on GPIO38 in DevKitC-1 v1.1 (GPIO48 in v1.0, which this rig is); kept off so the allowlist holds for either revision |

Safe output pins (header-only GPIOs with no on-board function), drawn from in `sorted` order:
GPIO1, GPIO2, GPIO4, GPIO5, GPIO6, GPIO7, GPIO8, GPIO9, GPIO10, GPIO11, GPIO12, GPIO13, GPIO14, GPIO15, GPIO16,
GPIO17, GPIO18, GPIO21, GPIO47.

The safe list and the excluded groups together partition every ESP32-S3 GPIO: GPIO0-GPIO21 and GPIO26-GPIO48 (GPIO22-GPIO25 do not exist on this
part), and no GPIO is both safe and excluded.

## 3. Pool composition

`gen_pool(seed_base)` returns 13 variants (`n = 13` is the default and the minimum). Every image is a signed,
sector-aligned ESP-IDF app image plus, for two of them, a trailer appended after the signature sector.

| Count | Role | Footprint | WiFi | BLE |
|-------|------|-----------|------|-----|
| 9 | `valid` | sector-aligned image that fits the slot | accept | accept |
| 2 | `unaligned_trailer` | valid image plus a 1-4095 byte trailer after the signature sector, so the file size is not a 4096 multiple | accept | reject |
| 1 | `near_limit` | within 64 KiB below 4 MiB (SLOT_SIZE, 4194304 bytes); flash segments are 64 KiB aligned so an exact size is not reachable | accept | accept |
| 1 | `too_big` | above 4 MiB, at most 64 KiB + 4096 over; built against a temporary 5 MB partition table | reject | reject |

Expected outcomes are the ones `poolmanifest.expected_outcomes` returns, one `{"accept": bool, "reason": str}`
verdict per transport:

- `valid`: both transports accept; the reason is "sector-aligned image fits the slot".
- `near_limit`: both transports accept; the reason is "image within 64 KiB of the slot limit and still fits".
- `unaligned_trailer`: WiFi accepts because the "bootloader never reads the bytes after the signature sector";
  BLE rejects, with the trailer length in the reason, because the trailer "leaves the image not 4096-aligned".
- `too_big`: both transports reject, "image is larger than the slot".

This gives 12 non-`too_big` images, the minimum `validate_manifest` requires, over at least 8 distinct sizes.

## 4. Manifest schema

The manifest is written next to the images and is the run's contract: the index, the seed, the geometry and the
expected verdict for both transports. `validate_manifest` re-checks that contract before a run trusts it, so a
corrupt pool fails loudly instead of quietly producing a false pass.

Top-level keys, from `poolmanifest.make_manifest`:

| Key | Meaning |
|-----|---------|
| schema | manifest format version, currently 1 |
| seed_base | the seed base the pool was generated from |
| slot_size | the OTA slot size the images were checked against (SLOT_SIZE) |
| images | list of entries, one per built image, in index order |

Entry keys, from `poolmanifest.make_entry`:

| Key | Meaning |
|-----|---------|
| index | position in the pool, 0-based, must match the entry's position in `images` |
| seed | the per-index seed `seed_for(seed_base, index)` produced |
| role | one of `valid`, `unaligned_trailer`, `near_limit`, `too_big` |
| version | the image's version string, `gen-<8 hex>`; unique in the manifest |
| file | the image's file name; unique in the manifest |
| size | file size in bytes, `len(data)` |
| signed_len | length of the signed part, i.e. the image without its trailer |
| trailer_len | bytes appended after the signature sector, `size - signed_len` |
| sha256 | lowercase hex sha256 of the whole file; differs on every rebuild because the RSA-PSS signature is salted |
| content_sha256 | sha256 of everything before the signature sector; identical on every rebuild of the same seed, so this is the reproducibility check |
| params | `pad_bytes`, `blink_ms`, `led_rgb` (list of 3), `pins` (list of 2) |
| expected | per-transport verdicts, `{"wifi": {"accept", "reason"}, "ble": {"accept", "reason"}}` |

## 5. Budget

Measured (AC5, `scripts/evidence/bl069_pool_install_2026-09-25/`): the resumed run of 50 steps took 2 h 25 m. WiFi installs 31.8 / 46.4 / 68.8 s
(min / median / max), BLE installs 154 / 264 / 359 s; the 4.13 MB near_limit image took 357 s over BLE and 67 s over WiFi; the over-limit image was refused after 154 s (WiFi) and 484 s (BLE).
BLE times are close to the drift figure in `docs/LESSONS_LEARNED.md` Trap 24.

## 6. What is committed

The generated `.bin` files are gitignored; only the manifest, its README and the seed file are committed. The pool
reproduces byte for byte from the seed base, so a clone rebuilds the images instead of storing them.
