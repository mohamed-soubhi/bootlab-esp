# BL-005 evidence — board hardware detection, 2026-09-21

## PSRAM mode
Both boards' eFuse dumps (`backups/efuse_E072A1AA2390.txt`, `backups/efuse_ACA7042C3B04.txt`, taken before any
write and confirmed unchanged at the end of BL-028) are **identical in every PSRAM field**:
```
PSRAM_CAP    (BLOCK1) PSRAM capacity    = 8M
PSRAM_VENDOR (BLOCK1) PSRAM vendor      = AP_3v3        # 3.3 V supply variant; NOT "quad"
PSRAM_TEMP   (BLOCK1) PSRAM temperature = 85C           FLASH_TYPE = 4 data lines (quad flash)
```
On the ESP32-S3 an 8 MB embedded PSRAM is the Octal part (the 2 MB one is quad), so the fuses point to Octal.
That is an inference from the chip family, so it was tested rather than trusted:

**idf board (`E0:72:A1:AA:23:90`): CONFIRMED octal.** A v1 build with `CONFIG_SPIRAM=y` and `CONFIG_SPIRAM_MODE_OCT=y`
(`esp_idf/sdkconfig.psram`, a detection build that is not part of the product; options verified in
`build_psram/sdkconfig` after building, image signed) was flashed, then re-delivered by OTA so that the software reset
kept the USB port and the whole boot was captured:
```
I (305) octal_psram: vendor id    : 0x0d (AP)
I (305) octal_psram: dev id       : 0x02 (generation 3)
I (305) octal_psram: density      : 0x03 (64 Mbit)
I (306) octal_psram: VCC          : 0x01 (3V)
I (307) esp_psram: Found 8MB PSRAM device
I (307) esp_psram: Speed: 40MHz
I (1039) esp_psram: SPI SRAM memory test OK
I (1051) esp_psram: Adding pool of 8192K of PSRAM memory to heap allocator
```
A wrong mode makes this init fail and the boot abort; it booted, joined WiFi and answered `/version`.
The board was then restored to v1 (slot 0, confirmed; LABID `VER?` checked).

**zephyr board (`AC:A7:04:2C:3B:04`): octal, INFERRED.** Its PSRAM eFuses are identical to the idf board's and it is
the same module (16 MB quad flash, 8 MB PSRAM, rev v0.2), but nothing was flashed to it, so the octal result is not
run-tested there. `rig.yaml` says so in its comment.

## LED GPIO
- idf board: GPIO48, confirmed by a real blink (BL-020, PLAN R14).
- zephyr board: **still unknown.** Confirming it needs a blink app running on that board, which means writing its flash
  (a backup exists: `backups/esp_ACA7042C3B04.bin` + `.sha256`) and is outside the Zephyr hold only if done with an IDF build.
  Not done: it needs the owner's per-instance go-ahead.
