# Results index (evidence for the presentation)

Every claim below points at a directory with the raw data. Dates are 2026-09-25/26. Boards: board 1 = ESP32-S3 DevKitC-1 v0.2 (UID E072A1AA2390, COM14),
board 2 = same hardware (UID ACA7042C3B04, COM12). All hardware runs used native Windows Python (R14: never open the serial port from WSL).

| # | Result | Evidence |
|---|---|---|
| 1 | **BL-060 IDF soak: 100 / 100 cycles** (50 HTTPS + 50 BLE OTA, v1<->v2), 3 h 48 m, final v1 | `scripts/evidence/bl060_soak_2026-09-23d/` |
| 2 | **BL-069 image pool built offline**: 13 signed images (9 valid, 2 with a post-signature trailer, 1 just under 4 MB, 1 over it), reproducible content hash | `scripts/evidence/bl069_pool_2026-09-25/` |
| 3 | **Gate R1**: an image whose file size is not a multiple of 4096 (3,170-byte and 1,908-byte trailers) installs and confirms on the real board | `scripts/evidence/bl069_r1_2026-09-25/` |
| 4 | **BL-069 AC5**: all 12 valid pool images confirmed in BOTH OTA slots over WiFi, the 10 BLE-accepting ones over BLE; the 4.26 MB `too_big` image refused over both | `scripts/evidence/bl069_pool_install_2026-09-25/` |
| 5 | **BL-067 smoke**: 10 / 10 cycles, all BLE, includes a `hang` image | `scripts/evidence/bl067_smoke_20260925/` |
| 6 | **BL-067 randomized soak: 200 / 200 cycles matched the model** (seed 20260925; 111 WiFi + 89 BLE; 139 fixed, 22 generated, 39 failure images: bad_sig, hang, no_confirm), 5.2 h. On first attempts 198/200: the two misses were a runner bug, fixed and re-run | `scripts/evidence/bl067_20260925/` (README = the honest account) |
| 7 | **BL-072 gate, board 2**: WiFi OTA and BLE OTA both proven from the workstation, identity verified against board 2's own UID, BLE scan pinned to its address | `scripts/evidence/bl072_board2_gate_2026-09-26/` |
| 8 | **BL-072 two boards in parallel: 400 cycles, 200 per board, same seed; 200/200 matched the model on BOTH boards**, identical outcome on every cycle, BLE serialized by a file lock, one small unexplained WiFi speed difference (board 2 ~13-15 % faster) | `scripts/evidence/bl072_two_boards_2026-09-26/` |
| 9 | **Working with a second AI agent**: task/report exchange, guardrails, review outcome per task | `docs/presentation/evidence/agent_collaboration/` |

## Things worth showing (each came from a live run, not from a test)
- Salted RSA-PSS signatures: whole-file hashes differ per build, content hashes do not (LESSONS Trap 30).
- The update CLI cannot tell a same-version reinstall from a failure (Trap 33); a board pending verify refuses OTA and needs a reset (Trap 32);
  a second open of a COM port already held by the run is refused on Windows (Trap 31).
- Honest failure accounting: two runner-caused misses in the 200-cycle run are listed, re-run and disclosed, not hidden.
- Unexplained and still open: the board sometimes accepts an OTA trigger and never pulls the image (Trap 34, seen 3 times in one day, retry always worked).

## Reproduce
`docs/BL067_RANDOM_SOAK.md` (randomized soak runbook), `docs/BL069_IMAGE_POOL.md` (pool), `docs/BL060_SOAK_TEST.md`, `docs/LESSONS_LEARNED.md` (all traps).
