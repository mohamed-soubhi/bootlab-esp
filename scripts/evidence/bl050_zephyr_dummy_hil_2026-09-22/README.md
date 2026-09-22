# BL-050[zephyr] — Dummy HIL test runs on the zephyr board and restores v1

**Date:** 2026-09-22
**Board:** `lab-esp-zephyr` (`AC:A7:04:2C:3B:04`), COM12 (Windows workstation)

## What happened

Board was found stuck in the ROM download bootloader ("waiting for download") -- root cause was
physical: the BOOT button/GPIO0 jumper was still held from an earlier manual boot-mode entry, so
every reset re-entered the ROM bootloader instead of booting the app. This looked like a firmware
crash loop (rapid USB connect/disconnect observed) but was purely mechanical.

Recovery: reflashed the known-good confirmed v1 build (`esp_zephyr/app/build_v1/{mcuboot,app}/zephyr/
{zephyr.bin,zephyr.signed.bin}`, same recipe as BL-030) via esptool from WSL2 (identity verified first:
`esptool chip-id` -> MAC `ac:a7:04:2c:3b:04`) while diagnosing -- this turned out to be unnecessary
(the board was never actually corrupted) but harmless, since it wrote the same known-good image. After
releasing the BOOT button and a normal reset, the board came up healthy: LABID answers, `app=1.0.0`,
`slot=0`, `confirmed=1`, 1.00 Hz blink measured.

## Live test run

Ran `test_dummy_hil_zephyr_board` live (not `--mock-rig`) on Windows against `COM12`:

```
.venv_win_ble\Scripts\python.exe -m pytest tests_hil\test_dummy_hil.py::test_dummy_hil_zephyr_board \
  -m zephyr --port COM12 --board-ip 192.168.1.153 --keys-dir keys --env-file credentials.env -v
```

Result: **1 passed**. `console.log` (BL-060's `SharedConsolePort`, working for zephyr too, unmodified)
shows real live LABID frames, not mock output:

```
$LAB,VER,bl=mcuboot,app=1.0.0,git=db7cfc2,build=20260922T1921Z,variant=v1,slot=0,confirmed=1*37A0
$LAB,ID,board=zephyr,hw=esp32s3_devkitc,mcu=esp32s3,uid=ACA7042C3B04,os=zephyr-4.4.99,flash_kb=16384*3A52
```

`dummy_report_zephyr.txt` is tagged `mode: live`.

## Result

`BL-050[zephyr]` -> **done**. `BL-050[idf]` was already done. Ticket fully closed.

## Notes for whoever continues BL-051/BL-052/BL-053/BL-055 (zephyr tracks)

- `--port COMx` must be passed explicitly on this workstation; `resolve_board()` auto-detection
  did not find the zephyr board by USB serial number over the Windows-native pyserial backend
  (untriaged -- works fine over WSL2's USB/IP passthrough, per the identity check during recovery).
- Watch for stray `serial_watch.py` processes holding the port exclusively (Windows COM ports are
  exclusive-access) -- `tasklist | findstr python` / `taskkill /F /PID <n>` before a live run if a
  test fails with `PermissionError(13, 'Access is denied.')` on the port.
- If `usbipd list` ever shows a board's busid as `Shared (forced)` instead of `Shared` or `Not shared`,
  Windows native apps (pyserial included) cannot open it -- `usbipd unbind --busid <n>` restores the
  normal Windows driver.
