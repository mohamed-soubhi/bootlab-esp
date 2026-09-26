# BL-072 — the BL-067 randomized soak on TWO boards in parallel from one workstation (2026-09-26)

Board 1 (idf, UID E072A1AA2390, COM14, 192.168.1.152) and board 2 (same hardware, UID ACA7042C3B04, COM12, 192.168.1.153, ex-Zephyr board flashed with the IDF app)
ran `tests_hil/soak_random.py` AT THE SAME TIME on one native-Windows machine: **the same seed 20260925, the same 200-cycle plan and the same 13-image pool on each
board, 400 cycles in total, one report per board.** Started 00:56, finished before 08:46 (`elapsed_s` 28,141 s board 1, 26,365 s board 2).

## Result
| | board 1 | board 2 |
|---|---:|---:|
| cycles matching the expected outcome | 200 / 200 | 200 / 200 |
| pass rate (target >= 99 %) | 100 % | 100 % |
| WiFi / BLE cycles | 111 / 89 | 111 / 89 |
| host-side retries | 0 | 0 |
| aborted / final state | no / confirmed v1 | no / confirmed v1 |

Outcome agreement cycle by cycle: **200 of 200 cycles had the same outcome on both boards, none differed** (`comparison_board1_vs_board2.md`, made with
`tests_hil/compare_boards.py`, which was written by the second AI agent against tests written first). Per image kind: 139 fixed, 22 generated, 39 failure images
(bad_sig, hang, no_confirm) on each board; every one matched the model on both.

## How the two runs were kept apart (acceptance criterion 2)
| collision risk | how it was avoided | check |
|---|---|---|
| serial port / console log | one COM port and one console.log per run (`--port`, `--out`) | no serial errors in either run |
| local OTA HTTPS server port (both default to 8443) | board 1 on 8443, board 2 on 8444 (`--http-port`) | no bind errors |
| BLE target | each run pinned by its own rig file (`host/config/rig.yaml` / `rig-board2.yaml`): identity checked against the board's own UID and the BLE scan pinned to its own address (board 2 = AC:A7:04:2C:3B:06) | every install verified against the right UID |
| one BLE adapter, two boards | BLE transfers take turns through a cross-process file lock (`--ble-lock`, `tests_hil/filelock.py`); WiFi runs in parallel | 0 failures, 0 retries |
Before the full run, a 10-cycle parallel pilot (`pilot_board1/`, `pilot_board2/`, all BLE, so the lock was contended every cycle) passed 10/10 on both boards.
Second-board prerequisite (criterion 1): `scripts/evidence/bl072_board2_gate_2026-09-26/` (WiFi and BLE OTA proven from the workstation).

## Board-to-board differences (acceptance criterion 5)
Medians of the per-cycle duration in seconds, board 1 / board 2 (nothing exceeded the 25 % flag threshold):
| transport | kind | board 1 | board 2 | ratio |
|---|---|---:|---:|---:|
| WiFi | fixed | 31.9 | 27.85 | 0.87 |
| WiFi | generated | 61.55 | 52.55 | 0.85 |
| WiFi | failure | 152.7 | 152.7 | 1.00 |
| BLE | fixed | 206.3 | 205.4 | 1.00 |
| BLE | generated | 256.65 | 288.05 | 1.12 |
| BLE | failure | 281.85 | 251.85 | 0.89 |

1. **WiFi is 13-15 % faster on board 2**, consistently: on the same images and cycles board 2 was faster in 72 of 78 fixed cycles (median 4.0 s less) and in 10 of 10 generated
   cycles; the difference is the same in the first and last ten cycles, and board 1 itself is steady (31.9 s solo and in parallel). **Root cause: not determined.**
   Checked and ruled out: WiFi signal strength. Board 2 is the weaker one (median RSSI -66 dBm against -55 dBm for board 1, from each board's console log),
   which points the opposite way. Untested candidate: flash write speed (the WiFi OTA is flash-write bound; the two boards are the same module model but the flash chip
   lot or vendor was not compared, and reading it needs a download-mode `esptool flash-id` on each board, which was not done under the R14 constraint).
   The difference does not affect any outcome.
2. **BLE**: no board difference above run-to-run noise; the BLE spread between the boards (0.89-1.12) goes both ways.
3. **Not a board difference, an effect of sharing:** BLE cycles took 1.5-1.9x longer than board 1 alone (`comparison_board1_solo_vs_parallel.md`: fixed 108.7 s solo -> 206.3 s parallel),
   because the two boards queue for the one BLE adapter. WiFi durations were unchanged (31.9 s vs 31.9 s). It costs time, not correctness.

## Files
`board1/`, `board2/`: `cycles.jsonl`, `report.json`, `status.json`, `update.log.gz`, `console.log.gz`. `pilot_board1/`, `pilot_board2/`: the 10-cycle pilot.
`comparison_board1_vs_board2.md`, `comparison_board1_solo_vs_parallel.md`. Runbook: `docs/BL067_RANDOM_SOAK.md` (flags `--http-port`, `--ble-lock`, `--rig-config`).
