# BL-026 evidence — IDF WiFi OTA pull (esp_https_ota), 2026-09-21

Board: `lab-esp-idf`, USB serial `E0:72:A1:AA:23:90`, IP 192.168.1.152. Firmware built with per-dir
sdkconfig (PLAN R15), signed RSA-3072. Server: `scripts/ota_check.py` (HTTPS, Lab Root CA) reached
through `scripts/tcp_forwarder.py` on the Windows host. Console captured natively on Windows
(`scripts/serial_watch.py COM14`, DTR/RTS inactive) — PLAN R14.

## Failed first attempt (root cause: transport, not firmware)
- v2 never appeared; console showed `esp_https_ota: data read -1, errno 104` →
  `OTA failed: ESP_FAIL`. The board did NOT reboot (no boot banner, uptime continuous).
- Cause: `tcp_forwarder.py` closed both sockets on the first EOF, sending a RST that truncated the
  1 MB download. Fixed (half-close, close after both directions) and the server now speaks
  HTTP/1.1 with Content-Length.
- The first AC2 "refused" results were vacuous: server-side "bytes served" does not prove the board
  received them. Withdrawn; AC2 now requires the board's own console evidence.

## AC1 — v1 -> v2 over WiFi, 4 Hz, confirmed=1: PASS
```
before: {'app': '1.0.0', 'git': '1.0.0', 'slot': 0, 'confirmed': True}
[PASS] AC1 POST /ota accepted: HTTP 202
[PASS] AC1 board runs v2: after: {'app': '2.0.0', 'git': '2.0.0', 'slot': 1, 'confirmed': True}
[PASS] AC1 slot flipped: slot 0 -> 1
[PASS] AC1 confirmed after health check: {'app': '2.0.0', 'git': '2.0.0', 'slot': 1, 'confirmed': True}
```
Console:
```
I (1910501) app_https: OTA requested: url=https://192.168.1.134:8443/v2.bin, version=2.0.0, task created
I (1911171) esp_https_ota: Writing to <ota_1> partition at offset 0x420000
I (1925911) app_https: OTA pull and verification successful! Rebooting in 1s...
rst:0xc (RTC_SW_CPU_RST),boot:0x9 (SPI_FAST_FLASH_BOOT)
I (264) boot: Loaded app from partition at offset 0x420000
I (275) app_init: App version:      2.0.0
I (3822) app_https: HTTPS control server started on port 443
```
Blink rate over LABID from native Windows (`scripts/rate_check.py COM14 --expect-hz 4`):
```
[PASS] toggles 528 -> 570 in 5.00 s = 4.20 Hz (expected 4.0 Hz +/-15%)
```

## AC2 — bad_sig rejected, v1 keeps running: PASS
Two artifacts, both confirmed failing `espsecure verify-signature` against the pinned key:
- `bad_sig_key.bin`: valid image signed with a foreign RSA-3072 key -> a real signature rejection.
  Console: `Verifying image signature...` / `E esp_image: Secure boot signature verification failed` /
  `W esp_image: image valid, signature bad` / `E esp_ota_ops: New image failed verification` /
  `E app_https: OTA failed: ESP_ERR_OTA_VALIDATE_FAILED (0x1503)`.
  This also shows the board pins its trust key (a validly-formed image from an unknown key is refused).
- `bad_sig_tamper.bin`: one body byte changed. Rejected by the image CHECKSUM
  (`E esp_image: Checksum failed. Calculated 0x7d read 0x82`), i.e. integrity, NOT a signature test.
```
[PASS] AC2 bad_sig_tamper.bin board reached verification and rejected it
[PASS] AC2 bad_sig_tamper.bin board did not reboot: no ROM boot banner in the console during the attempt
[PASS] AC2 bad_sig_tamper.bin running image unchanged: 1.0.0 / slot 0 / confirmed
[PASS] AC2 bad_sig_key.bin board reached verification and rejected it
[PASS] AC2 bad_sig_key.bin board did not reboot: no ROM boot banner in the console during the attempt
[PASS] AC2 bad_sig_key.bin running image unchanged: 1.0.0 / slot 0 / confirmed
ALL PASS
```
A real v2 -> v1 OTA (restore) was also exercised in the intermediate run and ended `1.0.0`, slot 0,
confirmed.

## Not covered
- no_confirm / hang revert (`hang.bin` in the scratchpad is a stale pre-WiFi build; rebuild first).
- A tampered image with a VALID checksum but an invalid signature (same-key signature-byte corruption).
