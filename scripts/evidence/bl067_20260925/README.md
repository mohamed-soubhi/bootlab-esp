# BL-067 — heavy randomized OTA soak, 200 cycles on board 1 (2026-09-25)

Board 1 (idf, UID E072A1AA2390, COM14, 192.168.1.152), native Windows Python 3.12, seed **20260925**, pool `bl069-2026-09-25`,
`--cycles 200 --ble-share 0.5 --failure-cap 2` (defaults). Every cycle picks an image and a transport from a seeded SHAKE-256 stream
and is judged against the expected-outcome model (`tests_hil/soak_model.py`); the plan is reproducible with `--dry-run --seed 20260925`.

## Result
**200 / 200 cycles matched the model (100 %, target >= 99 %)**, not aborted, board restored to confirmed v1 (`report.json`).
Read the next section before quoting this number.

| kind | cycles | matched | WiFi (min / median / max s) | BLE (min / median / max s) |
|---|---:|---:|---|---|
| fixed valid (v1..v4) | 139 | 139 | 29.7 / 31.9 / 37.4 (78) | 100.7 / 108.7 / 219.8 (61) |
| generated (BL-069 pool) | 22 | 22 | 42.4 / 64.0 / 70.1 (10) | 150.4 / 219.2 / 343.7 (12) |
| failure images | 39 | 39 | 64.3 / 152.8 / 155.5 (23) | 138.1 / 182.8 / 276.1 (16) |

Transports: 111 WiFi + 89 BLE. Failure images: bad_sig 10 (7 WiFi, 3 BLE), hang 15 (7, 8), no_confirm 14 (9, 5); never more than 2 in a row.
Total cycle time 5.2 h. Host-side retries needed: 0. `generated_slots` in `report.json` lists the slots each generated image landed in
(8 of the 12 images were picked; several landed in both slots).

## What "200 / 200" includes (honest account)
The run took **three windows** and stopped twice on RUNNER defects, never on the board:
1. **Window 1 (16:53-18:17) aborted at cycle 42.** The first `no_confirm` cycle: the board booted the image unconfirmed as it should, then
   `backend.reset()` opened COM14 a second time while the runner's own console capture held it, and Windows refused ("Access is denied").
   The runner's recovery then tried an OTA to restore v1, which a board in pending-verify refuses (the transfer stops after 81,920 B), so
   three restores failed and the 3-in-a-row abort fired (`report_window1_aborted.json`).
2. **Window 2 (resumed, 18:30-18:51) crashed at cycle 53** on the same defect (second `no_confirm`; `report_window2_crashed.json`).
3. **Window 3 (resumed with `--rerun-cycles 42,53`, ~19:00-22:55)** ran with the fixes: cycles 42 and 53 were executed again and matched, then
   cycles 54-200. The original failed records stay in `cycles.jsonl` (marked by the later `"rerun": true` records); the report counts the latest
   record per cycle. **On first attempts 198 of 200 cycles matched; the 2 misses were the runner bug, none was the board.**

Fixes made because of this (all in the same commit): the shared console port now toggles DTR/RTS on the handle it already holds
(`SharedConsolePort.hard_reset`); recovery from an image pending verify is a hard reset, never an OTA; serial reads retry through a
re-opening port; `reset_to_v1` retries 3 times. See `docs/LESSONS_LEARNED.md` Traps 31-35.

## How each outcome was verified on the real board
- **valid:** update CLI ok AND the runner's own LABID snapshot shows (version, slot flipped, confirmed).
- **bad_sig:** update not ok, the whole image delivered (update log: bytes served / last BLE sector), board unchanged.
- **no_confirm:** pending state read (new version, flipped slot, confirmed=0), hard reset, rollback to the previous confirmed image.
- **hang:** whole image delivered AND proof it ran (`Task watchdog got triggered` in this cycle's console capture or the update CLI saw
  it running), then rollback to the previous confirmed image.

## Files
`cycles.jsonl` (header, warm-up, one record per cycle, re-runs), `report.json`, `report_window1_aborted.json`, `report_window2_crashed.json`,
`status.json`, `update.log.gz`, `console.log.gz`. The 10-cycle smoke run before it: `scripts/evidence/bl067_smoke_20260925/` (10/10, all BLE, includes a hang).
Runbook: `docs/BL067_RANDOM_SOAK.md`. `elapsed_s` in `report.json` covers the last window only.

**Update 2026-09-26:** the intermittent "trigger accepted, image never pulled" seen around this run has a proven root cause and a fix (`docs/LESSONS_LEARNED.md` Trap 34; evidence `scripts/evidence/bl069_followup_ota_root_cause_2026-09-26/`). This run used shared console capture, which never opens the port fresh, and needed 0 retries.
