# BL-060 soak — timeline, 2026-09-22, lab-esp-idf COM14

- `trial_8cycles/`: `scripts/soak_overnight.sh 8`. 8/8 passed (100%), 4 WiFi + 4 BLE, 1431 s, ended confirmed v1.
  Trial run proving the runner itself (resumable JSONL, abort-on-failure, v1 restore) end to end before the overnight run.
- `attempt1_crashed/`: first 100-cycle attempt. Crashed at cycle 1 (unhandled exception in the runner's best-effort
  recovery reset on a WiFi timeout) -- runner bug, fixed in f77c01c. Resumed, then aborted after 4 consecutive failures
  (2x WiFi timeout, 2x BLE unreachable). Board was healthy when checked directly afterward (LABID/HTTPS/USB all clean, v1 confirmed).

See `bl060_soak_2026-09-22b/` (aborted, root-caused the WiFi `TRIGGER_TIMEOUT_S` margin) and `bl060_soak_2026-09-22c/`
(after both fixes: the timeout margin and a soak-harness cycle-targeting bug) for the continued investigation.
**BL-060 is NOT met.** The 100-cycle soak has not completed; the current blocker is described in `bl060_soak_2026-09-22c/README.md`.
