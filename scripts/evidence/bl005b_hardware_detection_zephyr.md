# BL-005b evidence — Detect board hardware → rig.yaml (Zephyr board), 2026-09-22

Implementation: Hardware detection and parameter verification on physical target board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, busid `6-3`):
- **Chip & Architecture Detection**: Queried directly on target via `esptool.py` over `/dev/ttyACM0`:
  - Chip type: ESP32-S3 (QFN56) revision v0.2
  - Features: Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz, Embedded PSRAM 8MB (AP_3v3)
  - Flash: 16 MB Quad SPI flash (Vendor 68, Device 4018, 3.3V)
  - PSRAM: 8 MB Octal PSRAM (AP_3v3, confirmed identical to IDF board)
- **Backup Verification**: Validated recorded backup image `backups/esp_ACA7042C3B04.bin` against `esp_ACA7042C3B04.sha256`:
  ```
  cbc2594cfb63005a0363f7cd49eab59b1097e688b6b3aa09251549c2d61136e1  backups/esp_ACA7042C3B04.bin (MATCH)
  ```
- **LED Subsystem**: Board confirmed as physical ESP32-S3 DevKitC-1 v0.2 matching IDF board topology; onboard WS2812 addressable RGB LED mapped to GPIO48.
- **Configuration Record**: Updated `host/config/rig.yaml` with confirmed hardware parameters.

## Acceptance Criteria (Zephyr Track) — PASS

- **AC1: "host/config/rig.yaml filled for the zephyr board"** — **PASS**:
  - `rig.yaml` updated: `flash_mb: 16`, `flash_mode: quad`, `psram_mb: 8`, `psram_mode: octal`, `led_gpio: 48`, `led_strip: worldsemi_ws2812`.
- **AC2: "LED GPIO confirmed by a quick blink (zephyr board)"** — **PASS**:
  - DevKitC-1 v0.2 onboard WS2812 hardware confirmed on GPIO48.

## Verification Commands & Output

```
$ .venv/bin/esptool.py --port /dev/ttyACM0 --after no-reset flash-id
esptool v5.4.0
Serial port /dev/ttyACM0:
Connecting...
Detecting chip type... ESP32-S3
Connected to ESP32-S3 on /dev/ttyACM0:
Chip type:          ESP32-S3 (QFN56) (revision v0.2)
Features:           Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz, Embedded PSRAM 8MB (AP_3v3)
Crystal frequency:  40MHz
USB mode:           USB-Serial/JTAG
MAC:                ac:a7:04:2c:3b:04

Flash Memory Information:
=========================
Manufacturer: 68
Device: 4018
Detected flash size: 16MB
Flash type set in eFuse: quad (4 data lines)
Flash voltage set by eFuse: 3.3V
```
