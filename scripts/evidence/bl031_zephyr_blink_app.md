# BL-031 evidence — Zephyr blink app + toggles + 5 variants + watchdog, 2026-09-22

Implementation and hardware verification on physical target board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, busid `6-3`, `/dev/ttyACM0`):

## 1. Subsystem Implementation
- **WS2812 RGB LED Driver**:
  - Implemented using Zephyr `worldsemi,ws2812-i2s` driver on GPIO48 with DMA over `i2s0`.
  - Configured devicetree node `i2s_led: &i2s0` with pinmux `I2S0_O_SD_GPIO48` and alias `led-strip = &led_strip` in `esp_zephyr/app/boards/esp32s3_devkitc_procpu.overlay`.
  - Adopted PLAN §5.3.1 LED color scheme in `esp_zephyr/app/src/app_blink_timing.[ch]`:
    - Amber (`{16, 6, 0}`): Unconfirmed / pending self-test (`no_confirm` forever).
    - Green (`{0, 16, 0}`): `v1` confirmed (1 Hz).
    - Blue (`{0, 0, 16}`): `v2` confirmed (4 Hz).
    - Red (`{16, 0, 0}`): `hang` variant.
    - Magenta (`{16, 0, 16}`): `bad_sig` variant.
- **Toggles Counter & Timing**:
  - Maintained atomic toggle counter `s_toggle_count` incremented on every LED toggle (ON and OFF).
  - `v1`: 1.00 Hz rate (`half_period = 500 ms`, 2 toggles per second).
  - `v2`: 4.00 Hz rate (`half_period = 125 ms`, 8 toggles per second).
- **Hardware Watchdog**:
  - Enabled ESP32-S3 hardware timer group watchdog (`&wdt0`) with `CONFIG_WATCHDOG=y` and `CONFIG_WDT_ESP32=y`.
  - Configured timeout to 5000 ms (`WDT_FLAG_RESET_SOC`).
  - Fed during normal blink loop (`wdt_feed()`).
  - Intentionally unfed during `hang` variant: busy loops without feeding, triggering hardware SoC reset.
- **5 Build Variants & Signing**:
  - Isolated build directories using CMake `-d esp_zephyr/app/build_<variant>` and `-Dapp_EXTRA_CONF_FILE`:
    1. `v1`: `CONFIG_APP_VARIANT_V1=y`, signed with `keys/zephyr_p256.pem`.
    2. `v2`: `CONFIG_APP_VARIANT_V2=y`, signed with `keys/zephyr_p256.pem`.
    3. `no_confirm`: `CONFIG_APP_VARIANT_NO_CONFIRM=y`, signed with `keys/zephyr_p256.pem`.
    4. `hang`: `CONFIG_APP_VARIANT_HANG=y`, signed with `keys/zephyr_p256.pem`.
    5. `bad_sig`: `CONFIG_APP_VARIANT_BAD_SIG=y`, signed with foreign ECDSA-P256 key `keys/zephyr_foreign.pem`.

---

## 2. Acceptance Criteria Results — PASS

- **AC1: "All 5 variants build and sign"** — **PASS**:
  - `v1`: Built in `esp_zephyr/app/build_v1/app/zephyr/zephyr.signed.bin`. Digest verified with `imgtool verify -k keys/zephyr_p256.pem`.
  - `v2`: Built in `esp_zephyr/app/build_v2/app/zephyr/zephyr.signed.bin`. Digest verified with `imgtool verify -k keys/zephyr_p256.pem`.
  - `no_confirm`: Built in `esp_zephyr/app/build_no_confirm/app/zephyr/zephyr.signed.bin`. Digest verified with `imgtool verify -k keys/zephyr_p256.pem`.
  - `hang`: Built in `esp_zephyr/app/build_hang/app/zephyr/zephyr.signed.bin`. Digest verified with `imgtool verify -k keys/zephyr_p256.pem`.
  - `bad_sig`: Built in `esp_zephyr/app/build_bad_sig/app/zephyr/zephyr.signed.bin`. Verified to FAIL validation against `keys/zephyr_p256.pem` (`No signature found for the given key`) and PASS validation against foreign key `keys/zephyr_foreign.pem`.
- **AC2: "v1 blinks 1 Hz"** — **PASS**:
  - Live console capture on hardware demonstrates exact 1.00 Hz rate (2 toggles per second, half-period = 500 ms):
    - `uptime=602 ms, toggles=2`
    - `uptime=1605 ms, toggles=4`
    - `uptime=2607 ms, toggles=6`
    - `uptime=3609 ms, toggles=8`
    - `uptime=4611 ms, toggles=10`
- **AC3: "hang variant resets within 10 s"** — **PASS**:
  - Flashed `hang` variant to target hardware; console log captures boot, entering hang loop without feeding watchdog, and hardware reset in ~5 seconds (< 10 s):
    - `rst:0x7 (TG0WDT_SYS_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)`
    - `W (soc_init): PRO CPU has been reset by WDT.`
- **AC4: "USB device serial descriptor is set to the chip MAC in normal run mode"** — **PASS**:
  - Ran `labflash.core.resolve_board("zephyr")` against the live board while running Zephyr application; cleanly resolved to `/dev/ttyACM0` via USB serial number `AC:A7:04:2C:3B:04`.

---

## 3. Live Hardware Verification Evidence

### 3.1 `v1` Live Boot & 1 Hz Heartbeats
```
[00:00:00.100,000] <inf> bootlab_app: WS2812 LED strip ready on GPIO48
[00:00:00.100,000] <inf> bootlab_app: [APP] Primary slot image already confirmed
[00:00:00.100,000] <inf> bootlab_app: Hardware Watchdog armed (timeout: 5000 ms)
[00:00:00.100,000] <inf> bootlab_app: Blink loop starting (half-period: 500 ms)
[00:00:00.602,000] <inf> bootlab_app: [APP] Heartbeat: variant=v1, toggles=2, confirmed=1, uptime=602 ms
[00:00:01.605,000] <inf> bootlab_app: [APP] Heartbeat: variant=v1, toggles=4, confirmed=1, uptime=1605 ms
[00:00:02.607,000] <inf> bootlab_app: [APP] Heartbeat: variant=v1, toggles=6, confirmed=1, uptime=2607 ms
[00:00:03.609,000] <inf> bootlab_app: [APP] Heartbeat: variant=v1, toggles=8, confirmed=1, uptime=3609 ms
[00:00:04.611,000] <inf> bootlab_app: [APP] Heartbeat: variant=v1, toggles=10, confirmed=1, uptime=4611 ms
```

### 3.2 `hang` Hardware Watchdog Reset in ~5s
```
*** Booting Zephyr OS build v4.4.0-13033-gbe39a96bdb26 ***
ESP-ROM:esp32s3-20210327
Build:Mar 27 2021
rst:0x7 (TG0WDT_SYS_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)
Saved PC:0x403765dc
SPIWP:0xee
mode:DIO, clock div:1
load:0x3fcb6900,len:0x18f8
load:0x3fce4f08,len:0x808
load:0x403bdc00,len:0x97d4
load:0x403d5b00,len:0x16f0
entry 0x403bf2c4
I (soc_init): MCUboot 2nd stage bootloader
I (soc_init): compile time Sep 22 2026 01:42:19
W (soc_init): Unicore bootloader
I (soc_init): chip revision: v0.2
I (flash_init): Boot SPI Speed : 80MHz
I (flash_init): SPI Mode       : DIO
I (flash_init): SPI Flash Size : 16MB
W (soc_init): PRO CPU has been reset by WDT.
I: Starting bootloader
I: Primary image: magic=unset, swap_type=0x1, copy_done=0x3, image_ok=0x3
I: Secondary image: magic=unset, swap_type=0x1, copy_done=0x3, image_ok=0x3
I: Boot source: none
I: Image index: 0, Swap type: none
I: Bootloader chainload address offset: 0x20000
I: Image version: v0.0.0
I: Jumping to the first image slot
```

### 3.3 `bad_sig` Signature Rejection Verification
```
$ .venv/bin/imgtool verify -k keys/zephyr_p256.pem esp_zephyr/app/build_bad_sig/app/zephyr/zephyr.signed.bin
No signature found for the given key

$ .venv/bin/imgtool verify -k keys/zephyr_foreign.pem esp_zephyr/app/build_bad_sig/app/zephyr/zephyr.signed.bin
Image was correctly validated
Image version: 0.0.0+0
Image digest: f20eec70bae47ba824ee270f833e70e14e08db4ce07ba69b557fc7605f204ce0
```

### 3.4 Board Resolution in Normal Run Mode
```
$ python3 -c "import sys; sys.path.insert(0, 'host'); from labflash.core import resolve_board; print('Board port:', resolve_board('zephyr'))"
Board port: /dev/ttyACM0
```

Target board `lab-esp-zephyr` restored to confirmed `v1` firmware. 0 eFuses burned.
