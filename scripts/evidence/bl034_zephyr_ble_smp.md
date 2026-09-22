# BL-034 evidence — Zephyr MCUmgr SMP over BLE, 2026-09-22

Implementation and hardware verification on physical target board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, BLE address `AC:A7:04:2C:3B:06`, busid `6-3`):

## 1. Subsystem Implementation

- **Firmware MCUmgr SMP BLE Transport (`esp_zephyr/app/src/app_ble_smp.[ch]`)**:
  - Enabled Zephyr Bluetooth LE subsystem and MCUmgr BT transport in `esp_zephyr/app/prj.conf`:
    - `CONFIG_BT=y`
    - `CONFIG_BT_PERIPHERAL=y`
    - `CONFIG_BT_DEVICE_NAME="lab-esp-zephyr"`
    - `CONFIG_MCUMGR_TRANSPORT_BT=y`
    - `CONFIG_MCUMGR_TRANSPORT_BT_PERIPHERAL=y`
    - `CONFIG_MCUMGR_GRP_IMG=y`
    - `CONFIG_MCUMGR_GRP_OS=y`
    - `CONFIG_MCUMGR_TRANSPORT_NETBUF_SIZE=2475`
    - `CONFIG_BT_L2CAP_TX_MTU=252`
    - `CONFIG_BT_BUF_ACL_RX_SIZE=256`
  - Registered SMP Service UUID `8D53DC1D-1DB7-4CD3-868B-8A527460AA84` and Characteristic UUID `DA2E7828-FBCE-4E01-AE9E-261174997C48`.
  - Hal Espressif blobs linked into Zephyr build for Bluetooth LE controller on ESP32-S3.
  - Initialized in `esp_zephyr/app/src/main.c` via `app_ble_smp_init()`.

- **Windows Host Tools (`scripts/`)**:
  - `scripts/ble_smp_query.py`: GATT inspector discovering SMP services using uncached service resolution.
  - `scripts/test_smp_ops.py`: SMP client query utility testing `EchoWrite` (OS group) and `ImageStatesRead` (Image group) over BLE.
  - `scripts/zephyr_ble_ota.py`: End-to-end OTA update orchestrator utilizing `smpclient` and `SMPBLETransport`:
    - Solves WinRT GATT caching across reboots by passing `winrt={"use_cached_services": False}`.
    - Automatic slot 1 erase handling with reconnect protection during SPI flash erase.
    - Chunked streaming upload with real-time transfer progress and throughput calculation.
    - Slot image state tagging: test-boot (`confirm=False`) or permanent confirmation (`confirm=True`).
    - SMP software reset execution (`ResetWrite`).

---

## 2. Acceptance Criteria Results — ALL PASS

### AC1: v1 → v2 over BLE, confirmed — PASS
- Staged signed `zephyr_v2.bin` (427,482 bytes, image hash `2ad9375cd968f24aac0c607301b18fd64e34c8480b7fe1908369208699817b91`).
- Uploaded over BLE to `lab-esp-zephyr` (`AC:A7:04:2C:3B:06`) in slot 1.
- Marked for permanent confirmation (`confirm=True`) and reset.
- Target device rebooted into MCUboot, which swapped slot 1 to slot 0 and booted `v2`.
- App self-test validated $\ge 5000\text{ ms}$ uptime and $\ge 5$ toggles, calling `boot_write_img_confirmed()`.
- Verified via BLE SMP `ImageStatesRead`:
  - `slot=0`: `hash=2ad9375c...`, `confirmed=True`, `active=True`, `pending=False`
  - High-frequency toggle rate: 4.0 Hz (measured by LABID and visual blue LED).

### AC2: no_confirm and hang revert — PASS
- **`no_confirm` Revert**:
  - Uploaded `zephyr_no_confirm.bin` (427,466 bytes) to slot 1.
  - Marked for test boot (`confirm=False`) and reset device.
  - MCUboot test-booted `no_confirm` in slot 0.
  - `no_confirm` variant purposefully omitted self-test confirmation (`can_confirm=false`), keeping `confirmed=False`.
  - Upon subsequent reset, MCUboot detected the unconfirmed state and swapped back to previous valid image (`v2`), restoring confirmed state.
- **`hang` Watchdog Revert**:
  - Uploaded `zephyr_hang.bin` (361,738 bytes, image hash `09343d537c47d34f35ffe5254500f0935f845d63a6381ccf5a4ac8703128975a`) in **10.9 s** (**32.3 KB/s**).
  - Marked for test boot (`pending=True`, `confirmed=False`) and sent SMP `ResetWrite()`.
  - MCUboot loaded `hang` image.
  - `hang` variant set LED red and blocked without feeding the hardware watchdog.
  - Hardware watchdog timeout triggered SoC reset at 5.0 s.
  - MCUboot detected trial boot failed without confirmation, rolled back flash slots, and restored `v2`.
  - Verified via BLE SMP `ImageStatesRead`:
    - `slot=0`: `hash=2ad9375c...` (`v2`), `active=True`, `confirmed=True`
    - `slot=1`: `hash=09343d53...` (`hang`), `active=False`, `confirmed=False`

### AC3: bad_sig refused by MCUboot — PASS
- Uploaded `zephyr_bad_sig.bin` (427,467 bytes, image hash `6d4343772d6fa75fe80605c46063a18da2842b6633de989258d6124a8b2486cf`) signed with unauthorized foreign key (`keys/zephyr_foreign.pem`) in **10.9 s** (**38.2 KB/s**).
- Marked for test boot (`pending=True`, `confirmed=False`) and sent SMP `ResetWrite()`.
- MCUboot booted and inspected slot 1 signature TLV against compiled-in public key (`keys/zephyr_p256.pub`).
- MCUboot rejected the foreign signature, refused to swap or execute slot 1, and immediately booted safe primary slot 0 (`v2`).
- Verified via BLE SMP `ImageStatesRead`:
  - `slot=0`: `hash=2ad9375c...` (`v2`), `active=True`, `confirmed=True`
  - Slot 1 rejected / invalidated.

---

## 3. Live Hardware Verification Logs

### 3.1 SMP BLE Operations Smoke Test
```text
Connecting to AC:A7:04:2C:3B:06 via SMPBLETransport (uncached)...
Connected! Sending EchoWrite...
Echo response: header=Header(op=<OP.WRITE_RSP: 3>, version=<Version.V2: 1>, flags=<Flag.UNUSED: 0>, length=24, group_id=0, sequence=1, command_id=0) smp_data=b'...' r='hello from bootlab!'
Sending ImageStatesRead...
Image states response: images=[ImageState(slot=0, version='0.0.0', image=None, hash=b'*\xd97\\\xd9h\xf2J\xac\x0c`s\x01\xb1\x8f\xd6N4\xc8H\x0b\x7f\xe1\x90\x83i \x86\x99\x81{\x91', bootable=True, pending=False, confirmed=True, active=True, permanent=False)] splitStatus=0
```

### 3.2 Hang Variant Upload & Watchdog Revert
```text
Loaded C:\MSA\embedded-OS\bootlab-esp\ble_stage\zephyr_hang.bin (361738 bytes)
Connecting to AC:A7:04:2C:3B:06 via SMP BLE (uncached)...
Connected!
Querying current image state...
Current images: [ImageState(slot=0, version='0.0.0', hash=2ad9375c..., bootable=True, pending=False, confirmed=True, active=True)]
Uploading 361738 bytes (slot 0)...
  Upload progress: 36704/361738 bytes (10%)
  Upload progress: 73463/361738 bytes (20%)
  Upload progress: 110198/361738 bytes (30%)
  Upload progress: 146933/361738 bytes (40%)
  Upload progress: 181219/361738 bytes (50%)
  Upload progress: 217954/361738 bytes (60%)
  Upload progress: 254689/361738 bytes (70%)
  Upload progress: 291424/361738 bytes (80%)
  Upload progress: 325710/361738 bytes (90%)
  Upload progress: 361738/361738 bytes (100%)
Upload complete in 10.9s (32.3 KB/s)
Slot 1 image hash: 09343d537c47d34f35ffe5254500f0935f845d63a6381ccf5a4ac8703128975a
Marking image for test boot (confirm=False)...
ImageStatesWrite response: [ImageState(slot=0, hash=2ad9375c..., confirmed=True), ImageState(slot=1, hash=09343d53..., pending=True, confirmed=False)]
Issuing SMP Reset command...
Reset command sent successfully
[SUCCESS] BLE OTA workflow completed.
```

**Post-Watchdog Rollback Confirmation (`test_smp_ops.py`):**
```text
Connecting to AC:A7:04:2C:3B:06 via SMPBLETransport (uncached)...
Connected! Sending EchoWrite...
Echo response: r='hello from bootlab!'
Sending ImageStatesRead...
Images: [
  ImageState(slot=0, version='0.0.0', hash=b'*\xd97\\\xd9h\xf2J\xac\x0c`s\x01\xb1\x8f\xd6N4\xc8H\x0b\x7f\xe1\x90\x83i \x86\x99\x81{\x91', bootable=True, pending=False, confirmed=True, active=True, permanent=False),
  ImageState(slot=1, version='0.0.0', hash=b'\t4=S|G\xd3O5\xff\xe5%E\x00\xf0\x93_\x84]c\xa68\x1c\xcfZJ\xc8p1(\x97Z', bootable=True, pending=False, confirmed=False, active=False, permanent=False)
]
```

### 3.3 Bad Signature Upload & MCUboot Refusal
```text
Loaded C:\MSA\embedded-OS\bootlab-esp\ble_stage\zephyr_bad_sig.bin (427467 bytes)
Connecting to AC:A7:04:2C:3B:06 via SMP BLE (uncached)...
Connected!
Querying current image state...
Uploading 427467 bytes (slot 0)...
  Upload progress: 44057/427467 bytes (10%)
  Upload progress: 85708/427467 bytes (20%)
  Upload progress: 129790/427467 bytes (30%)
  Upload progress: 171423/427467 bytes (40%)
  Upload progress: 215505/427467 bytes (50%)
  Upload progress: 257138/427467 bytes (60%)
  Upload progress: 301220/427467 bytes (70%)
  Upload progress: 342853/427467 bytes (80%)
  Upload progress: 386935/427467 bytes (90%)
  Upload progress: 427467/427467 bytes (100%)
Upload complete in 10.9s (38.2 KB/s)
Slot 1 image hash: 6d4343772d6fa75fe80605c46063a18da2842b6633de989258d6124a8b2486cf
Marking image for test boot (confirm=False)...
ImageStatesWrite response: [ImageState(slot=0, hash=2ad9375c..., confirmed=True), ImageState(slot=1, hash=6d434377..., pending=True, confirmed=False)]
Issuing SMP Reset command...
Reset command sent successfully
[SUCCESS] BLE OTA workflow completed.
```

**Post-Reset Rejection Verification (`test_smp_ops.py`):**
```text
Connecting to AC:A7:04:2C:3B:06 via SMPBLETransport (uncached)...
Connected! Sending EchoWrite...
Echo response: r='hello from bootlab!'
Sending ImageStatesRead...
Images: [
  ImageState(slot=0, version='0.0.0', hash=b'*\xd97\\\xd9h\xf2J\xac\x0c`s\x01\xb1\x8f\xd6N4\xc8H\x0b\x7f\xe1\x90\x83i \x86\x99\x81{\x91', bootable=True, pending=False, confirmed=True, active=True, permanent=False)
]
```
Slot 1 invalid signature was completely rejected by MCUboot, and the device remained safe on `v2` in slot 0.
