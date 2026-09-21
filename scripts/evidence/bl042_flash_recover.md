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

### 3. Post-Flash Verification — PASS
- **HTTPS `/version` check**:
  `Response: {'app': '1.0.0', 'git': '1.0.0', 'slot': 0, 'confirmed': True}`
- **LABID `info` check (COM14)**:
  `Identity : UID=E072A1AA2390 MCU=esp32s3 HW=esp32s3_devkitc OS=idf-v6.0.3 Flash=16384KB`
  `Version  : App=1.0.0 Git=1.0.0 Slot=0 Confirmed=1 Variant=v1`
  `State    : Toggles=69 Rate=1Hz Uptime=34504ms Reset=other`
- **LABID `measure` check (COM14)**:
  `[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)`
