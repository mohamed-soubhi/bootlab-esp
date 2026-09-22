# BL-060 soak — watched runs after fixes, mode: live — 2026-09-22, lab-esp-idf COM14

## Round 1 (before the harness fix, commit 0ab9b22)
15-cycle run aborted after 3 consecutive failures. WiFi trigger-timeout fix confirmed working (no more raw URLError),
but cycle 1's v2 image was accepted, host reported it fully "served" (later found misleading, see below), yet the
board never applied it (stayed 1.0.0 slot 0 after the full 240s wait). Cycle 2 then resent v1 while ALREADY on v1
(cycle-parity harness bug) -- fixed in f7715ad: `next_variant()` now targets off the board's real state, and
`run_update` prints the host's ACTUAL `server.served` byte count (not just the intended image size).

## Round 2 (after f7715ad; this run's cycles.jsonl/report.json/update.log)
15-cycle run again aborted after 3 consecutive failures, all targeting v2 correctly (harness fix confirmed working):
- Cycles 1-2 (WiFi): `host served: {}` -- the board never even connected to the host's image server, despite the
  POST /ota trigger being accepted (202). Not a transfer stall; the download never started.
- Cycle 3 (BLE): ALL 305 sectors were sent and ACKed by the board over BLE (full transfer completed per the host's
  view), yet the board STILL stayed on 1.0.0 slot 0, unconfirmed -- exactly the same symptom as the WiFi cycles,
  reached by a completely different transport.

**Conclusion: this is not a host/network/timeout problem.** Both transports show the same thing: the board is not
applying/switching to the new image, regardless of whether the transfer itself happened. This points at the board's
own OTA-apply path (esp_ota_end / esp_ota_set_boot_partition / the bootloader's slot-select), not at labflash or the
soak harness. The board stays healthy and cleanly on v1 (LABID/HTTPS agree, confirmed) -- it is not crashing or
looping, it is simply never leaving v1.

**Blocked on real console capture.** `tests_hil/conftest.py`'s live `serial_capture` fixture does not actually
capture anything (a stub note only) -- there is no board-side log of what happens during/after a rejected OTA.
Next step: build a real console reader and run ONE watched WiFi update to see the board's own log lines.

BL-060 stays open; this is now a firmware/board-level finding, not a host-tooling one.
