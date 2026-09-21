# BL-043 evidence — `labflash update idf --transport ble|wifi`, 2026-09-21

Board `lab-esp-idf` (`E0:72:A1:AA:23:90`). The command ran **natively on Windows** (serial port and BLE radio must be
used natively; PLAN R14) from the isolated venv, against images built with per-dir sdkconfig (PLAN R15).
`labflash update idf` = validate image -> read the image's own version -> **check board identity before sending** ->
send -> wait for the new version and its confirmation -> verify. 13 hardware-free pytest tests cover the logic
(`host/tests/test_update.py`); the whole host suite is 32 passed.

## AC: "Both transports update and verify via LABID" — PASS
**BLE, v1 -> v2** (`--transport ble --labid-port COM14 --board-mac E0:72:A1:AA:23:90`):
```
Updating idf over ble: ...\v2.bin (1249280 bytes)
  BLE: found nimble-ble-ota at E0:72:A1:AA:23:92
image version 2.0.0; before: app=1.0.0 slot=0; after: app=2.0.0 slot=1
[PASS] running the new image: board reports '2.0.0', image is '2.0.0'
[PASS] slot flipped: slot 0 -> 1
[PASS] confirmed: self-test confirmed the image
[PASS] identity (uid): board E072A1AA2390, expected E072A1AA2390
UPDATE OK
```
**WiFi, v2 -> v1** (`--transport wifi --board-ip 192.168.1.152 --labid-port COM14`; the tool ran its own HTTPS image server,
the token came from an environment variable):
```
  WiFi: board accepted the request; serving 1249280 bytes from 192.168.1.134:8443
image version 1.0.0; before: app=2.0.0 slot=1; after: app=1.0.0 slot=0
[PASS] running the new image   [PASS] slot flipped: slot 1 -> 0   [PASS] confirmed   [PASS] identity (uid)
[PASS] LABID == HTTPS version: LABID app=1.0.0 slot=0; HTTPS app=1.0.0 slot=0      # PLAN 7.3.4 consistency rule
UPDATE OK
```
Verification uses LABID (`VER?` + `ID?` over serial) in both runs; the WiFi run also cross-checks the HTTPS `/version`.

## It fails when it should (live negatives)
- **Wrong identity** (`--board-mac AC:A7:04:2C:3B:04` given for the idf board): refused, nothing sent, the BLE radio was
  not even scanned, exit 1:
  `ERROR: identity mismatch: the board reports uid E072A1AA2390 but ACA7042C3B04 is expected; nothing was sent`
- **Foreign-key-signed image over BLE**: the board refused it; the tool did NOT claim success, exit 1:
  `[FAIL] running the new image: board reports '1.0.0', image is '2.0.0'` / `[FAIL] slot flipped: slot 0 -> 0` / `UPDATE FAILED`
- Also (unit-tested): non-ESP file and unaligned image for BLE are rejected before any transport; CLI errors exit 1 without a traceback.

## Design notes / limits
- The expected version is read from the image's app descriptor (0x20 magic `0xABCD5432`, version at 0x30), not typed.
- Polling is sparse (2 s) on purpose: dense `/version` polling starves the board's TLS stack (BL-026).
- WSL2 caveat: no Bluetooth, and usbipd resets the board on serial open (R14). From WSL the WiFi transport works only with
  `--no-labid` (identity then NOT checked) and only if the board can reach the host (`scripts/tcp_forwarder.py` + `--host-ip`).
- `ruff` / `mypy` are not installed in the project venv yet; BL-046 owns that gate. `scripts/ota_check.py` still carries its own
  copy of the server/client code (the evidence tool for BL-026); folding it onto `labflash.idf_wifi_ota` is left for later.
- Final BL-056a re-run from the RPi4 is still to do (the RPi4 is the OTA-programming host).
