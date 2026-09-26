# BL-069 AC5 — every valid pool image installed and confirmed on both OTA slots (2026-09-25)

Board 1 (idf, UID E072A1AA2390, COM14), native Windows Python 3.12, pool `bl069-2026-09-25` (13 images, manifest validated,
sha256 verified before the run). Command (twice, second time with `--resume`):
`python -m tests_hil.pool_install --pool esp_idf\build_pool --port COM14 --board-ip 192.168.1.152 --keys-dir <keys> --env-file <credentials> --out evidence\bl069_pool_install_2026-09-25`

## Result
**AC5 is met:** `report.json` has `coverage_gaps: []` and `slot_coverage.json` shows all 12 valid images confirmed in BOTH slots over
WiFi, and the 10 BLE-accepting ones in both slots over BLE. The 2 trailer images (`gen-de2752f3`, `gen-6b593e13`) are WiFi-only by
design (the host refuses non-4096-aligned images over BLE, see `docs/LESSONS_LEARNED.md` Trap 25/26). Final state: board on confirmed v1,
not aborted, no recovery failures.

| | count |
|---|---:|
| pass | 52 (24 WiFi + 28 BLE, of which 10 are top-up installs) |
| expected_reject | 2 (`too_big`, 4,263,936 B: WiFi 153.6 s, BLE 484.0 s; board unchanged both times) |
| skipped | 4 (2 trailer images x 2 sweeps over BLE) |
| fail | 2 (see below), plus 3 in the aborted first run (retried and passed in the second) |

Timings (pass): WiFi 31.8 / 46.4 / 68.8 s (min / median / max); BLE 154.2 / 264.0 / 359.3 s. The 4.13 MB `near_limit` image
(`gen-bc23f981`): WiFi 66.8-68.8 s, BLE 356-359 s.

## Run 1 (13:33-13:47) aborted itself after 16 of 50 steps
WiFi sweep 1 passed 12/12 and the WiFi `too_big` reject was correct (the board downloaded all 4,263,936 B and refused it). Then three
steps in a row failed within ~4 s each: the first with `PermissionError: [WinError 32] ... labflash-ota-...\update.bin` (a Windows file
lock on the update CLI's temp file), the next two with the update reported not ok and the board unchanged; the runner's 3-in-a-row
rule stopped the run (`report_run1_aborted.json`). The board was healthy: a fresh process installed v1 immediately. The cause of the lock
is not proven (a handle left open inside the long-lived process, or antivirus scanning the freshly written file). The runners now retry
host-side errors (max 3, 20 s backoff, only while the board is unchanged, counted as `infra_retries`) and write the stack trace to
`update.log`. Run 2 (`--resume`, 13:57-16:17, 2 h 25 m) retried those three steps, they passed, and the lock did not recur
(`infra_retries: 0`).

## The two remaining failures are a schedule artifact, not the board
`ble:1:0` (`g00.bin`) and `ble:2:11` (`g11.bin`) were installs of the SAME version that was already running: the reversed second sweep
starts with the image the first sweep ended on, and the first BLE image repeated the last WiFi one. The board did install correctly (the
runner's own snapshot shows the expected image, slot and confirmed=1), but `labflash update` recognises a finished install by the
version changing, so it printed `[FAIL] slot flipped` and returned failure. The same effect explains why `wifi:2:11` (same image again)
was the first step to go wrong in run 1, although the error there was the file lock.
**Fix (committed with this evidence):** `pool_schedule` no longer reverses; it swaps neighbouring pairs (or repeats the order for an odd count),
which still puts every image on the opposite slot but never repeats an image back to back, and BL-067's picker never re-sends the running
version. This run used the OLD schedule; it was not repeated because coverage is complete.

## Files
`results.jsonl` (header + every step record, retried steps appear twice, latest wins), `report.json`, `report_run1_aborted.json`,
`slot_coverage.json` (version -> transport -> slots confirmed), `status.json`, `update.log.gz`, `console.log.gz` (raw board console).

**Update 2026-09-26:** the Windows file lock and the "trigger accepted, image never pulled" failures now have a proven root cause (a fresh serial open resetting the board mid-download, and a server that waited forever on the dead connection): `docs/LESSONS_LEARNED.md` Traps 34 and 35, evidence `scripts/evidence/bl069_followup_ota_root_cause_2026-09-26/`.
