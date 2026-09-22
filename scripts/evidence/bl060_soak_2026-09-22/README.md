# BL-060 soak trial — 8 cycles (mode: live) — 2026-09-22, lab-esp-idf COM14
`scripts/soak_overnight.sh 8`. 8/8 passed (100%), 4 WiFi + 4 BLE, 1431 s (~24 min for 8 -> ~4.8 h projected for 100), ended confirmed v1.
Trial run to prove the runner (resumable JSONL, abort-on-failure, v1 restore) end to end before the full overnight 100-cycle run.
This is NOT the 100-cycle soak; BL-060 stays open until that runs.
