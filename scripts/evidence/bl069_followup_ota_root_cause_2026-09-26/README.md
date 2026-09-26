# BL-069 follow-up (2026-09-26): content hashes across a rebuild, LED rate on the board, CI, and the real root cause of the intermittent OTA failures

## 1. Same seed, same image: all 13 images (`manifest_rebuilt.json` vs the committed manifest)
The whole pool was rebuilt from scratch into a different directory. **content_sha256, size and version are identical for all 13 images; the whole-file sha256 differs for
all 13** (RSA-PSS signatures are salted, LESSONS Trap 30). Before this only `g00` had been compared.

## 2. CI on the pushed commits
Six local commits were pushed (`566b094..2ecff02`); every job of `build.yml` passed: Python host tests (51 s), LABID unit and fuzz (43 s), forbidden-config checks,
ESP-IDF build and sign of all 7 variants (13 min), Zephyr build and sign.

## 3. LED-toggle rate measured on board 1 (`measure_pool.json`, 30 s per image, WiFi install then `LiveBackend.measure`)
Measured with the firmware's toggle counter read over LABID (this validates the blink loop's timing, not the physical LED or pins).
| image | configured half-period | nominal Hz | FreeRTOS-tick rate (10 ms tick) | measured Hz |
|---|---:|---:|---:|---:|
| g08 | 269 ms | 1.859 | 1.923 | 1.917 |
| g05 | 359 ms | 1.393 | 1.429 | 1.417 |
| g00 | 402 ms | 1.244 | 1.250 | 1.250 |
| g07 | 932 ms | 0.536 | 0.538 | 0.550 |
The rate follows the tick-quantized period (`vTaskDelay` of `pdMS_TO_TICKS(ms)` at `CONFIG_FREERTOS_HZ=100`, so 269 ms runs as 260 ms): within 1 % for three images,
2.3 % for the slowest. The nominal rate the image reports over LABID (`500 / blink_ms`) is therefore up to 3.1 % off for short periods (g08 fails the tool's 2-toggle
tolerance for that reason). Not changed, only documented. **Still not verified:** the physical LED colour and the toggling of the two spare pins (needs an eye or a meter).

## 4. Root cause of the "trigger accepted, image never pulled" failures and the 7-hour hang (LESSONS Traps 34 and 35, corrected)
Sequence that led to it (`measure_pool_updates.log.gz`, `console_*.log.gz`):
1. The first measurement run failed its first install with `host served: {}`; the second run then hung for 7 hours. The board was healthy (uptime 7 h, LED counter running)
   but held an ESTABLISHED connection to the local OTA server that never completed its TLS handshake, and the host process waited on it forever.
2. After stopping only that hung process, a fresh install worked at once, so the board was not stuck.
3. Every failure so far ran code that opens the serial port FRESH for each LABID read (the update CLI, `restore.py`, this script); every success had the runner's shared console
   port open. `SerialLineTransport` opened the port with pyserial's defaults, which assert DTR and RTS on open; on the USB-Serial-JTAG port that can reset the chip (PLAN R14),
   and the update command reads the board over serial WHILE the OTA downloads. A reset mid-download aborts the OTA (`served: {}`) and leaves a half-open connection on the host.
4. Fix: `SerialLineTransport` now sets DTR and RTS inactive before opening (test first). **Proof:** the same script that failed every install a few minutes earlier, with a
   fresh serial open per read, then completed 4 of 4 installs with 0 retries and restored v1.
5. Hardening kept: the OTA server now handshakes in the per-connection thread under a 60 s timeout and never joins stuck handlers on shutdown, so a dead connection can no longer
   hang the update process (a test reproduces the old hang).
Earlier evidence that said "cause not proven" (BL-069 AC5 README, BL-067 README) is annotated with a pointer here.
