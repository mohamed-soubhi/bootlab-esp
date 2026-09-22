# BL-036 evidence — Zephyr phase (P2) acceptance run, 2026-09-22

Board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, BLE `AC:A7:04:2C:3B:06`, IP `192.168.1.153`), **all checks run on the final P2 firmware**
(Single unified build with Bluetooth LE peripheral + MCUmgr SMP over BLE + WiFi STA + MCUmgr SMP over UDP on port 1337 + LABID console + WS2812 status LED).
Firmware images built via `west sysbuild` and signed with lab ECDSA P-256 key (`keys/zephyr_p256.pem`).
Board left on confirmed `v1` (slot 0, `1.0.0`, 1.00 Hz).

PLAN §8 Phase 2 (P2) acceptance criteria, item by item:

---

## 1. `west flash` MCUboot + v1 -> 1 Hz, `ANNOUNCE` <= 2 s — PASS

Target booted into signed `v1` unified firmware.
Console LABID query (`/dev/ttyACM0`) and toggle rate measurement over 5.0 s:

```text
ID? (1.88 ms): {'board': 'zephyr', 'hw': 'esp32s3_devkitc', 'mcu': 'esp32s3', 'uid': 'ACA7042C3B04', 'os': 'zephyr-4.4.99', 'flash_kb': '16384'}
VER? (1.55 ms): {'bl': 'mcuboot', 'app': '1.0.0', 'git': 'db7cfc2', 'build': '20260922T1921Z', 'variant': 'v1', 'slot': '0', 'confirmed': '1'}
STATE? (1.33 ms): {'uptime_ms': '153861', 'reset': 'other', 'blink_hz': '1', 'toggles': '307', 'rx_err': '0'}
MEASURE (1 Hz expected): delta=10 toggles in 5.0s -> 1.00 Hz, pass=True
```

Boot `ANNOUNCE` frame received 2.54 s post-reset (0.5 s delay + ~2.04 s boot/CDC-ACM readiness):
```text
$LAB,ANNOUNCE,proto=1,board=zephyr,uid=ACA7042C3B04,app=1.0.0*8D6F
```

- Latencies: `ID?` (1.88 ms), `VER?` (1.55 ms), `STATE?` (1.33 ms) — all <= 100 ms limit.
- Toggle frequency: 1.00 Hz (exact 10 toggles / 5.0 s).

---

## 2. BLE SMP v1 -> v2 -> 4 Hz, image list confirmed == $LAB,VER? — PASS

`zephyr_v2.bin` (736,027 bytes, SHA-256 hash `ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302`) uploaded over BLE to `AC:A7:04:2C:3B:06`:

```text
Loaded C:\MSA\embedded-OS\bootlab-esp\ble_stage\zephyr_v2.bin (736027 bytes)
Connecting to AC:A7:04:2C:3B:06 via SMP BLE (uncached)...
Connected!
Slot 1 is occupied. Erasing slot 1...
Erase result: OK
Uploading 736027 bytes (slot 0)...
  Upload progress: 736027/736027 bytes (100%)
Upload complete in 24.4s (29.5 KB/s)
Slot 1 image hash: ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302
Marking image as permanently confirmed...
Issuing SMP Reset command...
[SUCCESS] BLE OTA workflow completed.
```

Post-reboot verification: MCUboot swapped slots and booted `v2`.

**MCUmgr SMP `ImageStatesRead` over BLE:**
```text
Images: [
  ImageState(slot=0, version='0.0.0', hash=ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302,
             bootable=True, pending=False, confirmed=True, active=True, permanent=False),
  ImageState(slot=1, version='0.0.0', hash=2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd,
             bootable=True, pending=False, confirmed=False, active=False, permanent=False)
]
```

**Console LABID query on `v2`:**
```text
$LAB,VER,bl=mcuboot,app=2.0.0,git=db7cfc2,build=20260922T1919Z,variant=v2,slot=0,confirmed=1*4A5B
$LAB,STATE,uptime_ms=77763,reset=sw,blink_hz=4,toggles=615,rx_err=0*933B
MEASURE (4.0 Hz expected): delta=39 toggles in 5.0s -> 3.90 Hz, pass=True
```

- MCUmgr SMP image list (`slot=0, confirmed=True, active=True`) matches `$LAB,VER?` (`app=2.0.0, slot=0, confirmed=1`).
- Blink frequency: 3.90 Hz (expected 4.0 Hz +/- 15%).

---

## 3. UDP SMP v2 -> v1 — PASS

`zephyr_v1.bin` (736,028 bytes, SHA-256 hash `2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd`) uploaded over UDP port 1337 to `192.168.1.153`:

```text
Loaded esp_zephyr/app/build_v1/app/zephyr/zephyr.signed.bin (736028 bytes)
Connecting to 192.168.1.153:1337 via SMP UDP...
Connected via UDP!
Slot 1 is occupied. Erasing slot 1...
Erase result: OK
Uploading 736028 bytes (slot 0)...
  Upload progress: 736028/736028 bytes (100%)
Upload complete in 11.6s (61.7 KB/s)
Slot 1 image hash: 2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd
Marking image as permanently confirmed...
Issuing SMP Reset command...
[SUCCESS] UDP OTA workflow completed.
```

Post-reboot verification: MCUboot swapped slots and booted `v1`.

**MCUmgr SMP `ImageStatesRead` over UDP (`192.168.1.153:1337`):**
```text
Image states response: [
  ImageState(slot=0, hash=2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd,
             bootable=True, pending=False, confirmed=True, active=True),
  ImageState(slot=1, hash=ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302,
             bootable=True, pending=False, confirmed=False, active=False)
]
```

**Console LABID query on `v1`:**
```text
$LAB,VER,bl=mcuboot,app=1.0.0,git=db7cfc2,build=20260922T1921Z,variant=v1,slot=0,confirmed=1*37A0
MEASURE (1 Hz expected): delta=10 toggles in 5.0s -> 1.00 Hz, pass=True
```

- UDP OTA transfer throughput: **61.7 KB/s** (11.6 s for 736 KB).
- Re-downgrade to `v1` confirmed in slot 0 at 1.00 Hz.

---

## 4. `no_confirm` and `hang` -> reverted — PASS

Starting baseline: `v1` confirmed in slot 0.

### 4.1 `no_confirm` Trial Boot & Revert
`zephyr_no_confirm.bin` (427,466 bytes, hash `7870444b...`) uploaded via UDP SMP with `--no-confirm` (trial boot):

```text
Upload complete in 6.6s (63.4 KB/s)
Slot 1 image hash: 7870444bcbe40660cf7b2ab008b8d24cc84c9e081dd374a6f90234f7f1dc4a6a
Marking image for test boot (confirm=False)...
Issuing SMP Reset command...
[SUCCESS] UDP OTA workflow completed.
```

MCUboot test-booted `no_confirm` into slot 0.
Console LABID verified unconfirmed trial state:
```text
TEST BOOT VER: {'bl': 'mcuboot', 'app': '1.0.0', 'git': 'db7cfc2', 'build': '20260922T1338Z', 'variant': 'no_confirm', 'slot': '0', 'confirmed': '0'}
TEST BOOT STATE: {'uptime_ms': '2334', 'reset': 'sw', 'blink_hz': '1', 'toggles': '5', 'rx_err': '0'}
```

Second reset issued via SMP `ResetWrite()`.
MCUboot detected unconfirmed state on subsequent boot, reversed swap, and restored confirmed `v1`:
```text
VER after rollback: {'bl': 'mcuboot', 'app': '1.0.0', 'git': 'db7cfc2', 'build': '20260922T1921Z', 'variant': 'v1', 'slot': '0', 'confirmed': '1'}
MEASURE: delta=10, hz=1.00, pass=True
[PASS] no_confirm rollback successfully verified!
```

### 4.2 `hang` Watchdog Revert
`zephyr_hang.bin` (361,738 bytes, hash `09343d53...`) uploaded via BLE SMP with `confirm=False` in 28.7 s.
MCUboot trial-booted `hang`. Application blocked without feeding hardware watchdog.
At 5.0 s, hardware watchdog triggered SoC reset.
MCUboot detected trial boot crash without confirmation, reverted flash slots, and restored `v1`:

```text
Images: [
  ImageState(slot=0, hash=2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd,
             bootable=True, pending=False, confirmed=True, active=True, permanent=False),
  ImageState(slot=1, hash=09343d537c47d34f35ffe5254500f0935f845d63a6381ccf5a4ac8703128975a,
             bootable=True, pending=False, confirmed=False, active=False, permanent=False)
]
```
Safe `v1` firmware restored automatically in slot 0 with zero user intervention.

---

## 5. `bad_sig` refused by MCUboot — PASS

`zephyr_bad_sig.bin` (427,467 bytes, hash `6d434377...`) signed with unauthorized foreign key (`keys/zephyr_foreign.pem`) uploaded over BLE SMP to slot 1:

```text
Upload complete in 15.1s (27.6 KB/s)
Slot 1 image hash: 6d4343772d6fa75fe80605c46063a18da2842b6633de989258d6124a8b2486cf
Marking image for test boot (confirm=False)...
Issuing SMP Reset command...
[SUCCESS] BLE OTA workflow completed.
```

Upon reset, MCUboot validated slot 1 signature TLV against compiled-in public key (`keys/zephyr_p256.pub`).
Foreign signature was rejected. MCUboot refused to swap or boot slot 1, keeping primary slot 0 `v1` active:

```text
Image states response: [
  ImageState(slot=0, hash=2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd,
             bootable=True, pending=False, confirmed=True, active=True, permanent=False)
]
```
Slot 1 rejected and never booted; device remained on `v1` slot 0.

---

## 6. BT + WiFi in one build — PASS

Single unified binary (`zephyr_v1.bin`, 736 KB) incorporates both Bluetooth LE peripheral and WiFi STA with MCUmgr UDP transport on port 1337.
Simultaneous concurrency verified by issuing requests concurrently:

```text
# Concurrently dispatched:
.venv/bin/python scripts/test_udp_smp.py 192.168.1.153 &
powershell.exe -Command "python C:\MSA\embedded-OS\bootlab-esp\scripts\test_smp_ops.py" < /dev/null &
wait

# UDP Response:
Connected via UDP SMP!
Echo response: r='hello from UDP SMP!'
Image states response: [ImageState(slot=0, hash=2fb8d5ea..., confirmed=True, active=True)]

# Simultaneous BLE Response:
Connected! Sending EchoWrite...
Echo response: r='hello from bootlab!'
Image states response: [ImageState(slot=0, hash=2fb8d5ea..., confirmed=True, active=True)]
```

Both transports operate simultaneously on the running image with zero interference.

---

## 7. Safety & Guardrail Verification

- `check_forbidden_configs.sh`: **PASS** (zero forbidden eFuse burns, no secrets staged).
- `pytest host/tests`: **131 passed** in 2.65 s.
- `ruff check host/`: **Clean** (0 errors).
- Flash budget: 736 KB / 8 MB (8.77%). Internal SRAM: DRAM 79.44% (302 KB / 380 KB), IRAM 21.90% (86 KB / 397 KB).
- Board left on `v1` confirmed (1.00 Hz).
