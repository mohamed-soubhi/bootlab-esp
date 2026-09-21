# BL-028 evidence — ESP-IDF phase (P1) acceptance run, 2026-09-21

Board `lab-esp-idf` (USB serial `E0:72:A1:AA:23:90`), **all checks re-run on the final P1 firmware**
(WiFi + HTTPS OTA + BLE OTA + LABID + colour LED), images built with per-dir sdkconfig (PLAN R15) and
signed RSA-3072. Board left on v1 (`1.0.0`, slot 0, confirmed). Windows-side tools ran natively
(`serial_watch.py`, `labid_check.py`, `labid_query.py`, `rate_check.py`, `idf_ble_ota.py`, `ota_check.py`;
PLAN R14). PLAN §8 P1 acceptance, item by item:

## 1. USB flash v1 -> `measure` 1 Hz, `ANNOUNCE` <= 2 s — PASS
v1 (the build flashed over USB, `ota_0`), LABID `VER?` and the blink rate:
```
$LAB,VER,bl=v6.0.3,app=1.0.0,git=1.0.0,build=20260921T1730Z,variant=v1,slot=0,confirmed=1*37C5   crc_ok=True
[PASS] toggles 141 -> 151 in 5.01 s = 1.00 Hz (expected 1.0 Hz +/-15%)
```
`ANNOUNCE`, latency and garbage handling on a **fresh boot** (`labid_check.py --wait 300`, the boot was an OTA reboot):
```
[PASS] AC1 ANNOUNCE <= 2 s: announced at ~1003 ms uptime, board=idf uid=E072A1AA2390
[PASS] AC2 ID? <= 100 ms: 20 runs, median 3.3 ms, max 4.4 ms
[PASS] AC2 VER? <= 100 ms: 20 runs, median 4.4 ms, max 5.6 ms
[PASS] AC2 STATE? <= 100 ms: 20 runs, median 3.0 ms, max 3.2 ms
[PASS] AC3 garbage -> ERR syntax / unknown / crc / len   [PASS] AC3 no reset after garbage: uptime 1212 -> 1220 ms, rx_err=4
```
Note: the ANNOUNCE boot was v2's (same firmware, different variant), not a USB-flashed v1 boot.

## 2. WiFi OTA v1 -> v2 -> 4 Hz, `VER?` shows `app=2.x slot=1 confirmed=1` — PASS
```
[PASS] AC1 board runs v2: {'app': '2.0.0', 'slot': 1, 'confirmed': True}   [PASS] AC1 slot flipped: slot 0 -> 1
$LAB,VER,bl=v6.0.3,app=2.0.0,git=2.0.0,build=20260921T1735Z,variant=v2,slot=1,confirmed=1*17E4   crc_ok=True
[PASS] toggles 122 -> 163 in 5.00 s = 4.10 Hz (expected 4.0 Hz +/-15%)
```

## 3. BLE OTA v2 -> v1 -> 1 Hz — PASS
`idf_ble_ota.py` v2 -> v1, 305 sectors, then LABID and rate on the result:
```
$LAB,VER,...,app=1.0.0,git=1.0.0,variant=v1,slot=0,confirmed=1*37C5   crc_ok=True
[PASS] toggles 167 -> 177 in 5.00 s = 1.00 Hz (expected 1.0 Hz +/-15%)
```
Full BLE console evidence (verification, reboot, interrupted transfer, foreign-key refusal): `bl027_ble_ota_acceptance.md`.

## 4. `no_confirm` and `hang` -> previous version after reset — PASS
Both images built from the final source and verified signed. Starting state: v2 confirmed, slot 1.
**no_confirm** (WiFi OTA, then a hardware RST pressed by the owner):
```
after OTA   : {'app': '1.0.0-noconfirm', 'slot': 0, 'confirmed': False}
12 s later  : {'app': '1.0.0-noconfirm', 'slot': 0, 'confirmed': False}      # past the 5 s self-test window
after RST   : {'app': '2.0.0', 'git': '2.0.0', 'slot': 1, 'confirmed': True}  # rolled back
$LAB,VER,...,app=2.0.0,variant=v2,slot=1,confirmed=1*17E4   crc_ok=True
```
Caveat: proven by **state**, not by a bootloader log line. A hardware RST drops the ESP32-S3 USB port for
~600 ms, so the console capture reconnected after the bootloader had already run.
**hang** (WiFi OTA; the reset is the task watchdog, a software reset that keeps the port, so the console is complete):
```
I (92218) app_https: OTA pull and verification successful! Rebooting in 1s...
I (119) boot: Loaded app from partition at offset 0x20000     I (130) app_init: App version: 1.0.0-hang
E (5138) task_wdt: Task watchdog got triggered ...  E (5138) task_wdt: CPU 0: blink   E (5138) task_wdt: Aborting.
Rebooting...   rst:0xc (RTC_SW_CPU_RST)
I (301) boot: Loaded app from partition at offset 0x420000    I (312) app_init: App version: 2.0.0
```
The board went dark, then answered again as `{'app': '2.0.0', 'slot': 1, 'confirmed': True}` **17 s** after the request,
with no manual reset: the bootloader picked the previous slot (`0x420000`) after the panic.

## 5. `bad_sig` rejected in `esp_ota_end()`, old version keeps running — PASS
Re-run on the final firmware (`ota_check.py --only ac2 --console-log`), evidence taken from the board console:
```
[PASS] bad_sig_key.bin board reached verification and rejected it: signature, foreign key rejected; console has 'signature verification failed'
[PASS] bad_sig_key.bin board did not reboot   [PASS] bad_sig_key.bin running image unchanged (2.0.0 / slot 1 / confirmed)
[PASS] bad_sig_tamper.bin ... rejected: integrity (checksum), not a signature test   [PASS] ... unchanged, no reboot
```
The same foreign-key image is also refused over BLE (`bl027_ble_ota_acceptance.md`).

## 6. `efuse summary` unchanged vs backup — PASS
`espefuse summary` (read-only) compared to `backups/efuse_E072A1AA2390.txt`, the backup taken before any write,
run **twice**: once mid-run and once **last**, after every OTA and rollback of this phase. Both identical
(final: 187 lines compared, SHA-256 `2fb491e6...8a00` on both sides; the only earlier diff was a header note the backup
tool had printed, `Pre-connection option "no-reset"`).

## Tooling fixed on the way
- `labid_check.py` assumed the port disappears on reset. A software reset (OTA reboot, watchdog) does NOT drop the
  ESP32-S3 USB port, so it never fired, and its open/close polling kept COM14 busy (which blocked a rate measurement
  until the process was stopped). It now holds one connection and waits for the boot `ANNOUNCE` (`--wait`).
- New `labid_query.py` prints one CRC-verified LABID reply.

## Not covered / notes
- no_confirm rollback has no bootloader log line (item 4); its proof is the confirmed state before and after the RST.
- The Zephyr board was not involved. BL-028 stays `blocked` only through its dependencies (BL-022/026/027 wait on BL-020).
