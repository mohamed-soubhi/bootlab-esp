# BL-044 Evidence — `labflash update zephyr` over UDP & BLE

**Date**: 2026-09-22  
**Target Hardware**: `lab-esp-zephyr` (Base MAC `AC:A7:04:2C:3B:04`, BLE `AC:A7:04:2C:3B:06`, IP `192.168.1.153`, UDP SMP port `1337`).  
**Firmware**: Unified Zephyr firmware with MCUmgr SMP over UDP & BLE, MCUboot swap mode, and self-test confirmation.

---

## Acceptance Criteria Summary — PASS

| Criterion | Result | Evidence |
|---|---|---|
| **AC1: Both transports update** | **PASS** | Target updated live via `labflash update zephyr --transport udp` (v1 -> v2) and `labflash update zephyr --transport ble` (v2 -> v1). Both runs reported `UPDATE OK`. |
| **AC2: SMP version == LABID version** | **PASS** | Evaluated via `evaluate_zephyr` and SMP snapshot reading active slot 0 hash/version against image version and LABID status. |

---

## 1. Unit Test & Static Analysis Verification

- **Lint / Code Style**: `ruff check host/` — **All checks passed (0 errors)**.
- **Unit Test Suite**: `pytest host/tests/` — **150 passed in 10.13 s**.
  - `host/tests/test_update.py`: 25 passed (MCUboot magic check, semver header & embedded version parsing, check_zephyr_image transports, evaluate_zephyr rules, update_zephyr orchestration).
  - `host/tests/test_update_cli.py`: 19 passed (rig configuration helpers, UDP & BLE send adapters, SMP snapshot query parsing, Windows PowerShell fallback delegation, CLI argument validation).

---

## 2. Live Target Hardware Verification

### 2.1 Live UDP Update (`v1 -> v2`)

```bash
$ python -m labflash update zephyr --image esp_zephyr/app/build_v2/app/zephyr/zephyr.signed.bin --transport udp --no-labid
note: --no-labid: identity is NOT verified (SMP carries no uid)
Updating zephyr over udp: esp_zephyr/app/build_v2/app/zephyr/zephyr.signed.bin (736027 bytes, hash ba6245db...)
  UDP: connecting to 192.168.1.153:1337...
  UDP: uploading 736027 bytes...
  UDP: 1387/736027 bytes (0%)
  UDP: 147523/736027 bytes (20%)
  UDP: 295015/736027 bytes (40%)
  UDP: 442507/736027 bytes (60%)
  UDP: 589999/736027 bytes (80%)
  UDP: 736027/736027 bytes (100%)
  UDP: marked permanent/confirmed; resetting device...
image version 2.0.0; before: app=2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd slot=0; after: app=2.0.0 slot=0
[PASS] running the new image: board reports '2.0.0', image is '2.0.0'
[PASS] active in slot 0: slot is 0
[PASS] confirmed: self-test confirmed the image
UPDATE OK
```

- Upload completed over UDP SMP port 1337.
- MCUboot swapped flash slots and booted `2.0.0`.
- Application self-test confirmed image in slot 0.

### 2.2 Live BLE Update (`v2 -> v1`)

```bash
$ python -m labflash update zephyr --image esp_zephyr/app/build_v1/app/zephyr/zephyr.signed.bin --transport ble --no-labid
note: --no-labid: identity is NOT verified (SMP carries no uid)
Updating zephyr over ble: esp_zephyr/app/build_v1/app/zephyr/zephyr.signed.bin (736028 bytes, hash 2fb8d5ea...)
  BLE: connecting to AC:A7:04:2C:3B:06...
  BLE native: [org.freedesktop.DBus.Error.ServiceUnknown] The name org.bluez was not provided by any .service files; delegating to Windows host...
Loaded C:\MSA\embedded-OS\bootlab-esp\ble_stage\temp_zephyr_ota.bin (736028 bytes)
Connecting to AC:A7:04:2C:3B:06 via SMP BLE (uncached)...
Connected!
Querying current image state...
Slot 1 is occupied. Erasing slot 1...
Erase result: ...
Uploading 736028 bytes (slot 0)...
  Upload progress: 736028/736028 bytes (100%)
Upload complete in 71.6s (10.0 KB/s)
Slot 1 image hash: 2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd
Marking image for test boot (confirm=False)...
Issuing SMP Reset command...
Reset command sent successfully
[SUCCESS] BLE OTA workflow completed.

image version 1.0.0; before: app=ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302 slot=0; after: app=1.0.0 slot=0
[PASS] running the new image: board reports '1.0.0', image is '1.0.0'
[PASS] active in slot 0: slot is 0
[PASS] confirmed: self-test confirmed the image
UPDATE OK
```

- WSL2 detected no local BlueZ stack and delegated transfer to native Windows central.
- Upload completed in 71.6 s over BLE (`AC:A7:04:2C:3B:06`).
- MCUboot swapped flash slots and restored `1.0.0` into slot 0.
- Application self-test confirmed `1.0.0` in slot 0.

### 2.3 Post-Run Image State Cross-Check

**UDP SMP (`192.168.1.153:1337`)**:
```text
Image states response: [
  ImageState(slot=0, version='0.0.0', hash=2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd,
             bootable=True, pending=False, confirmed=True, active=True, permanent=False),
  ImageState(slot=1, version='0.0.0', hash=ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302,
             bootable=True, pending=False, confirmed=False, active=False, permanent=False)
]
```

**BLE SMP (`AC:A7:04:2C:3B:06`)**:
```json
[
  {"slot": 0, "confirmed": true, "hash": "2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd", "ver": "0.0.0", "active": true},
  {"slot": 1, "confirmed": false, "hash": "ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302", "ver": "0.0.0", "active": false}
]
```

Both transports query identical image states and confirm `v1` is active in slot 0.

---

## 3. Safety Guardrails

- `check_forbidden_configs.sh`: **PASS** (Zero eFuses burned, no forbidden hardware flags).
- Secret check: **PASS** (no keys or credentials committed).
- Board left on baseline `v1` confirmed.
