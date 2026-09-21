# BL-041 evidence — `labflash identify`, `info`, `measure` (IDF track), 2026-09-21

Implementation: `host/labflash/identify.py`, wired into `host/labflash/__main__.py`.
Unit tests: `host/tests/test_identify.py` (7 tests, all passing; full host suite: 46 passed).

## Acceptance Criteria (IDF Track) — PASS
- **AC1: "identify maps the idf board (LABID uid matches rig.yaml)"** — PASS.
- **AC2: "measure within ± 1 toggle over 5 s on the idf board"** — PASS.

## Live On-Target Verification (Windows native COM14, PLAN R14)

### 1. `labflash identify --port COM14`
```
$ python -m labflash identify --port COM14
Board      Port             UID              MCU          Board Name
-----------------------------------------------------------------
idf        COM14            E072A1AA2390     esp32s3      idf
```
- Matched live LABID UID `E072A1AA2390` against `rig.yaml`'s configured `mac: "e0:72:a1:aa:23:90"`.

### 2. `labflash info idf --port COM14`
Human-readable:
```
=== idf on COM14 ===
Identity : UID=E072A1AA2390 MCU=esp32s3 HW=esp32s3_devkitc OS=idf-v6.0.3 Flash=16384KB
Version  : App=1.0.0 Git=1.0.0 Slot=0 Confirmed=1 Variant=v1
State    : Toggles=2692 Rate=1Hz Uptime=1345960ms Reset=sw
```
Machine-readable (`--json`):
```json
{
  "ok": true,
  "board": "idf",
  "port": "COM14",
  "id": {
    "board": "idf",
    "hw": "esp32s3_devkitc",
    "mcu": "esp32s3",
    "uid": "E072A1AA2390",
    "os": "idf-v6.0.3",
    "flash_kb": "16384"
  },
  "version": {
    "bl": "v6.0.3",
    "app": "1.0.0",
    "git": "1.0.0",
    "build": "20260921T1730Z",
    "variant": "v1",
    "slot": "0",
    "confirmed": "1"
  },
  "state": {
    "uptime_ms": "1315289",
    "reset": "sw",
    "blink_hz": "1",
    "toggles": "2630",
    "rx_err": "0"
  }
}
```

### 3. `labflash measure idf --port COM14 --seconds 5`
```
$ python -m labflash measure idf --port COM14 --seconds 5
[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)
```
- Measured delta: exactly 10 toggles over 5.00 s = 1.00 Hz (expected 10 toggles, tolerance ±1 toggle).
