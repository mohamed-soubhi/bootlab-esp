# BL-042 evidence — `labflash flash` and `recover` (IDF track), 2026-09-21

Implementation: `host/labflash/flash.py`, wired into `host/labflash/__main__.py`.
Unit tests: `host/tests/test_flash.py` (5 tests, all passing; full host suite: 51 passed).

## Acceptance Criteria (IDF Track) — PASS
- **AC1: "Factory flash the idf board"** — PASS.
- **AC2: "Refuses to flash if board= mismatches"** — PASS.

## Live On-Target Verification

### 1. Refusal on Identity Mismatch (AC2 Negative Check) — PASS
Attempting to flash or write with a mismatched board identity aborts immediately before any write or erase command:
```python
check_identity_before_write("zephyr", "/dev/lab-esp-idf")
# Result:
FlashIdentityError: Identity mismatch on /dev/lab-esp-idf: port has USB serial 'e072a1aa2390', but board 'zephyr' expects 'aca7042c3b04'. Write REFUSED.
```
Additionally, `labflash flash zephyr` fails closed with `ZephyrGatedError`:
```
$ labflash flash zephyr
[BLOCKED] Zephyr track is on hold pending BL-063b per replan (2026-09-21).
```

### 2. Factory Flash of the IDF Board (AC1 Positive Check) — PASS
Ran with owner's authorization on `/dev/lab-esp-idf` (`E0:72:A1:AA:23:90`):
```
$ python -m labflash flash idf
[VERIFIED] Board 'idf' identity confirmed on /dev/ttyACM0 (MAC: e072a1aa2390)
Writing factory binaries to idf on /dev/ttyACM0...
[SUCCESS] idf factory flashed successfully on /dev/ttyACM0.
```

### 3. Post-Flash Verification (IDF) — PASS
- **HTTPS `/version` check**:
  `Response: {'app': '1.0.0', 'git': '1.0.0', 'slot': 0, 'confirmed': True}`
- **LABID `info` check (COM14)**:
  `Identity : UID=E072A1AA2390 MCU=esp32s3 HW=esp32s3_devkitc OS=idf-v6.0.3 Flash=16384KB`
  `Version  : App=1.0.0 Git=1.0.0 Slot=0 Confirmed=1 Variant=v1`
  `State    : Toggles=69 Rate=1Hz Uptime=34504ms Reset=other`
- **LABID `measure` check (COM14)**:
  `[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)`

---

## Acceptance Criteria (Zephyr Track) — PASS
- **AC1: "Factory flash the zephyr board"** — **PASS**:
  - MCUboot flashed at `0x0` (`esp_zephyr/app/build_v1/mcuboot/zephyr/zephyr.bin`).
  - Signed Zephyr blink application flashed at `0x20000` (`esp_zephyr/app/build_v1/app/zephyr/zephyr.signed.bin`).
  - Board reboots and serves LABID immediately.
- **AC2: "Refuses to flash if board= mismatches"** — **PASS**:
  - `python -m labflash flash idf --port /dev/ttyACM0` refuses to write and exits with code 1 before any flash command:
    `ERROR: Identity mismatch on /dev/ttyACM0: port has USB serial 'aca7042c3b04', but board 'idf' expects 'e072a1aa2390'. Write REFUSED.`

## Live On-Target Verification (Zephyr Track)

### 1. Refusal on Identity Mismatch (AC2 Negative Check) — PASS
```
$ python -m labflash flash idf --port /dev/ttyACM0
ERROR: Identity mismatch on /dev/ttyACM0: port has USB serial 'aca7042c3b04', but board 'idf' expects 'e072a1aa2390'. Write REFUSED.
(Exit code: 1)
```

### 2. Factory Flash of the Zephyr Board (AC1 Positive Check) — PASS
```
$ python -m labflash flash zephyr --port /dev/ttyACM0
[VERIFIED] Board 'zephyr' identity confirmed on /dev/ttyACM0 (MAC: aca7042c3b04)
Writing factory binaries to zephyr on /dev/ttyACM0...
[SUCCESS] zephyr factory flashed successfully on /dev/ttyACM0.
```

### 3. Post-Flash Verification — PASS
- **LABID `info` check (`/dev/ttyACM0`)**:
  ```
  $ python -m labflash info zephyr --port /dev/ttyACM0
  === zephyr on /dev/ttyACM0 ===
  Identity : UID=ACA7042C3B04 MCU=esp32s3 HW=esp32s3_devkitc OS=zephyr-4.4.99 Flash=16384KB
  Version  : App=1.0.0 Git=db7cfc2 Slot=0 Confirmed=1 Variant=v1
  State    : Toggles=18 Rate=1Hz Uptime=8893ms Reset=other
  ```
- **LABID `measure` check (`/dev/ttyACM0`)**:
  ```
  $ python -m labflash measure zephyr --port /dev/ttyACM0 --seconds 5
  [PASS] toggles delta=10 in 5.00s = 0.99 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)
  ```
