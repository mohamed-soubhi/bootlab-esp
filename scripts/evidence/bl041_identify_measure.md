# BL-041 evidence — `labflash identify`, `info`, `measure` (IDF + Zephyr tracks)

Implementation: `host/labflash/identify.py`, wired into `host/labflash/__main__.py`.
Unit tests: `host/tests/test_identify.py` (12 tests passing; full host suite: 119 passed, ruff and mypy clean).

## Acceptance Criteria Summary — PASS (Both Tracks Complete)

### IDF Track (COM14)
- **AC1: "identify maps the idf board (LABID uid matches rig.yaml)"** — PASS.
- **AC2: "measure within ± 1 toggle over 5 s on the idf board"** — PASS.

### Zephyr Track (/dev/ttyACM0, busid 6-3, UID `ACA7042C3B04`)
- **AC3: "identify maps the zephyr board"** — PASS.
- **AC4: "measure within ± 1 toggle over 5 s on the zephyr board"** — PASS.

---

## 1. Zephyr Track Live Hardware Verification (/dev/ttyACM0)

Target hardware: ESP32-S3 `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, USB VID:PID 303A:1001, running BL-031/BL-032/BL-033 firmware).

### 1.1 `labflash identify --port /dev/ttyACM0`
```text
$ python -m labflash identify --port /dev/ttyACM0
Board      Port             UID              MCU          Board Name
-----------------------------------------------------------------
zephyr     /dev/ttyACM0     ACA7042C3B04     esp32s3      zephyr
```
- Matched live LABID UID `ACA7042C3B04` against `rig.yaml`'s configured `mac: "ac:a7:04:2c:3b:04"`.
- Resolved board key: `zephyr`.

### 1.2 `labflash info zephyr --port /dev/ttyACM0`
Human-readable:
```text
=== zephyr on /dev/ttyACM0 ===
Identity : UID=ACA7042C3B04 MCU=esp32s3 HW=esp32s3_devkitc OS=zephyr-4.4.99 Flash=16384KB
Version  : App=1.0.0 Git=db7cfc2 Slot=0 Confirmed=1 Variant=v1
State    : Toggles=373 Rate=1Hz Uptime=186575ms Reset=other
```

Machine-readable (`--json`):
```json
{
  "ok": true,
  "board": "zephyr",
  "port": "/dev/ttyACM0",
  "id": {
    "board": "zephyr",
    "hw": "esp32s3_devkitc",
    "mcu": "esp32s3",
    "uid": "ACA7042C3B04",
    "os": "zephyr-4.4.99",
    "flash_kb": "16384"
  },
  "version": {
    "bl": "mcuboot",
    "app": "1.0.0",
    "git": "db7cfc2",
    "build": "20260922T0808Z",
    "variant": "v1",
    "slot": "0",
    "confirmed": "1"
  },
  "state": {
    "uptime_ms": "189945",
    "reset": "other",
    "blink_hz": "1",
    "toggles": "379",
    "rx_err": "0"
  }
}
```

### 1.3 `labflash measure zephyr --port /dev/ttyACM0 --seconds 5`
```text
$ python -m labflash measure zephyr --port /dev/ttyACM0 --seconds 5
[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)
```
- Measured delta: exactly 10 toggles over 5.00 s = 1.00 Hz (expected 10 toggles, tolerance ±1 toggle).

---

## 2. IDF Track Live Hardware Verification (Windows native COM14, PLAN R14)

### 2.1 `labflash identify --port COM14`
```text
$ python -m labflash identify --port COM14
Board      Port             UID              MCU          Board Name
-----------------------------------------------------------------
idf        COM14            E072A1AA2390     esp32s3      idf
```
- Matched live LABID UID `E072A1AA2390` against `rig.yaml`'s configured `mac: "e0:72:a1:aa:23:90"`.

### 2.2 `labflash info idf --port COM14`
Human-readable:
```text
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

### 2.3 `labflash measure idf --port COM14 --seconds 5`
```text
$ python -m labflash measure idf --port COM14 --seconds 5
[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)
```
- Measured delta: exactly 10 toggles over 5.00 s = 1.00 Hz (expected 10 toggles, tolerance ±1 toggle).
