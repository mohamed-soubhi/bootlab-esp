# BL-027 evidence — IDF OTA over BLE (espressif/ble_ota 0.1.18 + NimBLE), 2026-09-21

Board: `lab-esp-idf`, USB serial `E0:72:A1:AA:23:90` (BLE address `E0:72:A1:AA:23:92` = base MAC + 2).
Firmware built with per-dir sdkconfig (PLAN R15), signed RSA-3072; options verified after the build.
Central: laptop Bluetooth LE via `bleak 3.0.2` in an isolated Windows venv; client `host/labflash/idf_ble_ota.py`
(protocol read from the component source; 15 pytest tests). Console captured natively on Windows
(`serial_watch.py COM14`, DTR/RTS inactive; PLAN R14). Transfers: 305 sectors, ATT MTU 256, ~110 s (~11 KB/s).

## Failure found first (and fixed)
The first BLE build **boot-looped** the board (restart every ~400 ms):
```
E (394) BLE_INIT: hci inits failed
E (394) NimBLE_BLE_OTA: nimble host init failed
expression: app_ble_ota_start()      abort() was called ...
```
Causes: (1) ble_ota calls `esp_nimble_init()` (host only), so the app must run
`esp_bt_controller_init/enable` first -- IDF's `nimble_port_init()` does that, `esp_nimble_init()` does not;
(2) my `ESP_ERROR_CHECK` made an optional subsystem fatal, which also took the WiFi OTA recovery path down.
Fixed: controller bring-up added; a BLE start failure is now logged, not fatal. The board was recovered by a USB flash.

## AC1 — v2 -> v1 over BLE (and v1 -> v2): PASS
v1 -> v2 (console):
```
I (205259) app_ble_ota: BLE OTA started: 1249280 bytes into ota_1 @0x420000
I (317439) esp_image: Verifying image signature...
I (317749) app_ble_ota: BLE OTA verification successful! Rebooting in 1s...
rst:0xc (RTC_SW_CPU_RST)   I (302) boot: Loaded app from partition at offset 0x420000   App version: 2.0.0
```
`/version` after: `{'app': '2.0.0', 'git': '2.0.0', 'slot': 1, 'confirmed': True}`.
v2 -> v1, run right after the interrupted transfer below:
```
I (160110) app_ble_ota: BLE OTA started: 1249280 bytes into ota_0 @0x20000
I (266340) esp_image: Verifying image signature...
I (266650) app_ble_ota: BLE OTA verification successful! Rebooting in 1s...
I (297) boot: Loaded app from partition at offset 0x20000   App version: 1.0.0
```
`/version` after: `{'app': '1.0.0', 'git': '1.0.0', 'slot': 0, 'confirmed': True}`.

## AC2 — WiFi stays connected during a BLE OTA: PASS
`GET /version` sampled every ~5 s (sparse on purpose: dense polling starves the board's TLS, see BL-026)
during the 116 s v1 -> v2 transfer: **24 of 24 samples OK** (17:57:08 -> 17:59:12), each returning the
correct `{'app': '1.0.0', 'slot': 0, 'confirmed': True}`; the single FAIL (17:59:18) is the planned reboot,
and 2.0.0 answered at 17:59:25. WiFi disconnect events in the whole console log: **0**.
(`E mbedtls_ssl_handshake -0x7280` lines are the sampler closing a TLS handshake, not a fault.)

## AC3 — interrupted transfer, old image still running: PASS
v1 sent to a board running v2, link dropped after 100 of 305 sectors:
```
I (82650) app_ble_ota: BLE OTA started: 1249280 bytes into ota_0 @0x20000
W (120440) app_ble_ota: BLE OTA aborted (BLE disconnected) after 409600 bytes; partial image discarded
```
409600 = 100 x 4096. No reboot; `/version`: `{'app': '2.0.0', 'slot': 1, 'confirmed': True}`. A full transfer
started right afterwards succeeded (AC1, v2 -> v1).

## Extra — the BLE path refuses a badly signed image: PASS
`bad_sig_key.bin` (valid image signed with a foreign RSA-3072 key), all 257 sectors delivered:
```
I (158276) esp_image: Verifying image signature...
E (158286) esp_image: Secure boot signature verification failed
W (158366) esp_image: image valid, signature bad
E (158366) esp_ota_ops: New image failed verification
E (158366) app_ble_ota: BLE OTA image failed verification: ESP_ERR_OTA_VALIDATE_FAILED
```
No reboot; the board stayed on v1 (slot 0, confirmed).

## Not covered / notes
- The interrupted-transfer test drops the link cleanly; a radio-level loss (walk out of range) was not tried.
- Only 4096-aligned images are supported by the client (ours are); ~11 KB/s, so ~2 min per image.
- Verified single-board only: the Zephyr board was not present on BLE OTA (Zephyr path on hold).
