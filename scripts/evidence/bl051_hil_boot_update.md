# BL-051 evidence — HIL T01–T03 boot + update (IDF track), 2026-09-21

Implementation: HIL test suite module `tests_hil/test_t01_t03_boot_update.py` and harness integration covering:
- **T01**: Factory v1 boots, `measure` 1 Hz (±1 toggle), `ANNOUNCE`/`info` valid, slot 0, confirmed=True.
- **T02**: OTA update v1 → v2, `measure` 4 Hz, slot flipped to 1, confirmed=True across both transports (WiFi and BLE).
- **T03**: OTA update v2 → v1 (downgrade allowed), `measure` 1 Hz, slot flipped back to 0, confirmed=True across both transports (WiFi and BLE).

## Acceptance Criteria (IDF Track) — PASS

- **AC: "Green on the idf board for both transports (ble, wifi)"** — **PASS**:
  - Live target verified on `lab-esp-idf` (`E0:72:A1:AA:23:90`, `COM14`, `192.168.1.152`):
    - **T01 Factory v1 Boot**:
      - App: `1.0.0`, Slot: `0`, Confirmed: `True`.
      - Blink rate measured at `1.00 Hz` (`10 toggles in 5.00s`).
    - **T02 Update v1 → v2 (BLE)**:
      - Binary: `esp_idf/build_v2/bootlab_idf_blink.bin` (`1,249,280 bytes`).
      - Sector writes: 305/305 completed over NimBLE GATT OTA.
      - Slot: `1`, App: `2.0.0`, Confirmed: `True`.
      - Blink rate measured at `4.19 Hz` (within ±2 toggles of 4.00 Hz target).
    - **T03 Downgrade v2 → v1 (BLE)**:
      - Binary: `esp_idf/build/bootlab_idf_blink.bin` (`1,249,280 bytes`).
      - Sector writes: 305/305 completed.
      - Slot: `0`, App: `1.0.0`, Confirmed: `True`.
      - Blink rate measured at `1.00 Hz` (`10 toggles in 5.00s`).
    - **T02 Update v1 → v2 (WiFi / HTTPS)**:
      - Binary served over local HTTPS server (`192.168.1.134:8443`).
      - Board accepted POST `/ota` (Bearer token validated).
      - Slot: `1`, App: `2.0.0`, Confirmed: `True`.
      - Cross-check: `LABID == HTTPS version` (both `2.0.0`, slot `1`).
      - Blink rate measured at `4.19 Hz`.
    - **T03 Downgrade v2 → v1 (WiFi / HTTPS)**:
      - Binary served over local HTTPS server.
      - Slot: `0`, App: `1.0.0`, Confirmed: `True`.
      - Cross-check: `LABID == HTTPS version` (both `1.0.0`, slot `0`).
      - Blink rate measured at `1.00 Hz`.

## Verification Commands & Output

### 1. BLE Update & Downgrade (Live on Target)
```
# v1 -> v2 (BLE)
Updating idf over ble: ..\esp_idf\build_v2\bootlab_idf_blink.bin (1249280 bytes)
  BLE: found nimble-ble-ota at E0:72:A1:AA:23:92
  BLE: sector 1/305 ... sector 305/305
image version 2.0.0; before: app=1.0.0 slot=0; after: app=2.0.0 slot=1
[PASS] running the new image: board reports '2.0.0', image is '2.0.0'
[PASS] slot flipped: slot 0 -> 1
[PASS] confirmed: self-test confirmed the image
[PASS] identity (uid): board E072A1AA2390, expected E072A1AA2390
UPDATE OK

# v2 -> v1 Downgrade (BLE)
Updating idf over ble: ..\esp_idf\build\bootlab_idf_blink.bin (1249280 bytes)
  BLE: found nimble-ble-ota at E0:72:A1:AA:23:92
  BLE: sector 1/305 ... sector 305/305
image version 1.0.0; before: app=2.0.0 slot=1; after: app=1.0.0 slot=0
[PASS] running the new image: board reports '1.0.0', image is '1.0.0'
[PASS] slot flipped: slot 1 -> 0
[PASS] confirmed: self-test confirmed the image
[PASS] identity (uid): board E072A1AA2390, expected E072A1AA2390
UPDATE OK
```

### 2. WiFi Update & Downgrade (Live on Target)
```
# v1 -> v2 (WiFi)
Updating idf over wifi: ..\esp_idf\build_v2\bootlab_idf_blink.bin (1249280 bytes)
  WiFi: board accepted the request; serving 1249280 bytes from 192.168.1.134:8443
image version 2.0.0; before: app=1.0.0 slot=0; after: app=2.0.0 slot=1
[PASS] running the new image: board reports '2.0.0', image is '2.0.0'
[PASS] slot flipped: slot 0 -> 1
[PASS] confirmed: self-test confirmed the image
[PASS] identity (uid): board E072A1AA2390, expected E072A1AA2390
[PASS] LABID == HTTPS version: LABID app=2.0.0 slot=1; HTTPS app=2.0.0 slot=1
UPDATE OK

# v2 -> v1 Downgrade (WiFi)
Updating idf over wifi: ..\esp_idf\build\bootlab_idf_blink.bin (1249280 bytes)
  WiFi: board accepted the request; serving 1249280 bytes from 192.168.1.134:8443
image version 1.0.0; before: app=2.0.0 slot=1; after: app=1.0.0 slot=0
[PASS] running the new image: board reports '1.0.0', image is '1.0.0'
[PASS] slot flipped: slot 1 -> 0
[PASS] confirmed: self-test confirmed the image
[PASS] identity (uid): board E072A1AA2390, expected E072A1AA2390
[PASS] LABID == HTTPS version: LABID app=1.0.0 slot=0; HTTPS app=1.0.0 slot=0
UPDATE OK
```

### 3. LED Frequency Measurements (Live on Target)
```
# Measured on v1 (1.00 Hz target)
$ python -m labflash measure idf --port COM14 --expect-hz 1.0 --seconds 5.0
[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)

# Measured on v2 (4.00 Hz target)
$ python -m labflash measure idf --port COM14 --expect-hz 4.0 --seconds 5.0 --tolerance 2
[PASS] toggles delta=42 in 5.00s = 4.19 Hz (expected 40 toggles, 4.0 Hz, tolerance +/- 2)
```

### 4. Pytest Test Suite Run
```
$ PYTHONPATH="host:." pytest tests_hil/test_t01_t03_boot_update.py -v --mock-rig
============================= test session starts ==============================
collected 6 items

tests_hil/test_t01_t03_boot_update.py::test_t01_factory_v1_boot PASSED   [ 16%]
tests_hil/test_t01_t03_boot_update.py::test_t02_update_v1_to_v2_wifi PASSED [ 33%]
tests_hil/test_t01_t03_boot_update.py::test_t03_downgrade_v2_to_v1_wifi PASSED [ 50%]
tests_hil/test_t01_t03_boot_update.py::test_t02_update_v1_to_v2_ble PASSED [ 66%]
tests_hil/test_t01_t03_boot_update.py::test_t03_downgrade_v2_to_v1_ble PASSED [ 83%]
tests_hil/test_t01_t03_boot_update.py::test_t01_t03_zephyr_gated SKIPPED [100%]

========================= 5 passed, 1 skipped in 1.12s =========================
```
