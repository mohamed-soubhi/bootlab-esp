# BL-060 OTA soak test

Runner: `tests_hil/soak.py`. Runs N alternating OTA cycles (v1 <-> v2) against the real board, mixing WiFi and BLE.
Run natively (Windows workstation / RPi4), never under WSL (R14).

## How it works

**Transport pattern.** `wifi, wifi, ble, ble`, repeated (`TRANSPORT_PATTERN`). 100 cycles = 50 WiFi + 50 BLE.

**Version.** Toggles each cycle (v1 -> v2 -> v1 ...). The target comes from the board's *actual* app version
(`next_variant`), not the plan, so a failed cycle never causes a resend of the version already running.

**Setup.** `reset_to_v1()` first. If the board cannot reach confirmed v1 the run stops ("precondition failed").

**Each cycle**
1. Read current app version over serial (`backend.snapshot()`), pick the opposite variant.
2. `backend.update(variant, transport, ...)` runs the update CLI. WiFi = HTTPS pull; BLE = GATT push. Flashing does not use serial.
3. Update CLI does its own LABID check.
4. Soak takes an independent serial snapshot. Requires `app == expected` and `confirmed == True`
   (board reports `confirmed=0`, then `confirmed=1` ~6 s after boot).
5. Append result to `cycles.jsonl`, update `status.json`, sleep `--pause` (default 5 s).

**On failure.** Best-effort `reset_to_v1()`, continue. Abort after 3 consecutive failures (`--max-consecutive-failures`).

**End of run.** Restore board to v1, write `report.json` (pass rate, per-transport totals). Exit 0 only if
pass rate >= 99 %, not aborted, and final state is v1.

**Serial (COM14) is verification only**: snapshots, LABID checks, and the raw `console.log` capture.
OTA data travels over WiFi/BLE. If COM14 drops, the OTA may still succeed but the test cannot confirm it.
The USB-Serial-JTAG port re-enumerates on every reboot, which can look like a test failure.

## Output directory

| File | Content |
|---|---|
| `cycles.jsonl` | one record per cycle: cycle, variant, transport, ok, cause, duration_s |
| `status.json` | heartbeat: mode, cycle, of, passes |
| `report.json` | final summary |
| `update.log` | update CLI output |
| `console.log` | raw board console capture (timestamped) |

## Commands used

Update the workstation checkout:

```
git pull
```

Smoke run (1 cycle):

```
.venv_win_ble\Scripts\python.exe -m tests_hil.soak --port COM14 --board-ip 192.168.1.152 --keys-dir keys --env-file credentials.env --cycles 1
```

Full run (100 cycles):

```
python -m tests_hil.soak --port COM14 --board-ip 192.168.1.152 --keys-dir keys --env-file credentials.env --cycles 100 --out scripts/evidence/bl060_soak_<date>
```

Resume an interrupted run (same `--out`):

```
python -m tests_hil.soak ... --out scripts/evidence/bl060_soak_<date> --resume
```

Watch live (PowerShell, second window):

```
Get-Content -Wait scripts\evidence\bl060_soak_<date>\console.log
Get-Content -Wait scripts\evidence\bl060_soak_<date>\update.log
```

Other flags: `--pause`, `--max-consecutive-failures`, `--images-dir`, `--rig-config`, `--console-log`, `--no-console-log`.
`--out` must be a new directory unless `--resume` is passed.

## Observations from run 2026-09-23d (console.log)

Timings, HTTPS OTA (3 cycles, consistent within ~1 s):

| Phase | Time |
|---|---|
| OTA request -> reboot | ~22 s |
| Flash write + signature verify | ~20 s |
| Reboot -> `confirmed=1` | ~6 s |

- Slots alternate correctly (ota_0 <-> ota_1); RSA-PSS signature verified each time; rollback protection works.
- `esp-tls-mbedtls: read error :-0x0050` (connection reset) appears on the first probe of every HTTPS OTA; the retry succeeds ~1 s later. Benign but recurring; candidate lesson-learned.
- `skip_common_name=true` warning: acceptable in the lab, must not ship (disables server-name authentication).
- BLE OTA: `fw_length = 1249280`, progress notifications on att_handle=16 about every 1.8 s. Still running after 4.6 min
  (roughly 3-5 KB/s, >12x slower than HTTPS). Connection interval flips between 48 and 12 units.
  Disconnect `reason=531` (0x213) is the client closing the link; harmless.
- Timestamp jumps of 2-5 s inside the BLE log (23:34:28, 23:36:35, 23:38:33) are likely host log buffering; a real BLE pause is not ruled out.

Log line meaning: `GATT procedure initiated: notify; att_handle=16` = board pushed a progress/ack notification to the subscribed client.

## Running the soak on the RPi4 with the second board (2026-09-24, in progress)

Goal: run the same IDF soak on the second physical board (the ex-Zephyr hardware, MAC `ac:a7:04:2c:3b:04`, BLE
`AC:A7:04:2C:3B:06`) from the Pi, in parallel with the workstation soak on board 1. Full trap write-up:
`docs/LESSONS_LEARNED.md` Traps 20-23.

**Setup that worked**
1. `sudo systemctl unmask bluetooth && sudo systemctl enable --now bluetooth && sudo hciconfig hci0 up`
   (scan then sees `nimble-ble-ota`). `rfkill list` must show no block.
2. `git clone`, `python3 -m venv .venv`, `pip install -e host`, `pip install bleak esp-idf-nvs-partition-gen`.
3. Copy from the workstation: `credentials.env`, `keys/{ca,server_cert,server_key}.pem`, and
   `esp_idf/build/` (bootloader, partition table, otadata, app) plus `esp_idf/build_v2/bootlab_idf_blink.bin`.
   Do NOT copy `idf_sbv2.pem` (signing key). `chmod 600` the secrets.
4. Flash the IDF baseline (explicit offsets, `-b 230400`, run from `esp_idf/build`):
   `python -m esptool --chip esp32s3 -p /dev/ttyACM0 -b 230400 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size keep --flash-freq 80m 0x0 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0xf000 ota_data_initial.bin 0x20000 bootlab_idf_blink.bin`
5. Provision WiFi/token into NVS: `labflash provision idf --port /dev/ttyACM0 --env-file credentials.env`.
   Boot log then shows `WiFi connected: IP=192.168.1.153` and `HTTPS control server started on port 443`;
   `curl -k https://192.168.1.153/version` returns `{"app":"1.0.0",...,"slot":0,"confirmed":true}`.
6. `rig-pi.yaml` (untracked) pins `idf` to the second board (`mac`, `ble_mac`, `ip`), so the Pi never touches board 1.
7. `sudo ufw allow from 192.168.1.153 to any port 8443 proto tcp` (the board pulls the image from the Pi).
8. Run: `python -m tests_hil.soak --port /dev/ttyACM0 --board-ip 192.168.1.153 --keys-dir keys --env-file credentials.env --rig-config rig-pi.yaml --cycles 4 --out scripts/evidence/bl060_soak_pi_smoke_<date>`

**Status: BLOCKED on Pi power.** The trigger and the board's pull now work (TLS fix `13a1d2c`, ufw rule), but the
download stopped at 196,608 / 1,249,280 bytes while `vcgencmd get_throttled` showed `0x50005` (live under-voltage).
Fix the supply / use a powered hub for the ESP, then re-run and watch the live bits:
`while true; do v=$(vcgencmd get_throttled | cut -d= -f2); (( (v & 0x5) != 0 )) && echo "$(date +%T) $v"; sleep 0.5; done`
Not yet exercised on the Pi: a completed OTA and any BLE cycle.

## Evidence

_To be added after the runs complete._

| Run | Date | Cycles | Pass rate | WiFi | BLE | Final v1 | Evidence dir |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
