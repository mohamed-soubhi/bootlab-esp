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

## Evidence

_To be added after the runs complete._

| Run | Date | Cycles | Pass rate | WiFi | BLE | Final v1 | Evidence dir |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
