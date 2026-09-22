# BL-060 soak — failed attempt, root cause found — 2026-09-22
15-cycle run aborted after 3 consecutive failures (2x WiFi, 1x BLE). All WiFi failures' `duration_s` clustered at
5.2-5.6s, just above the old `TRIGGER_TIMEOUT_S = 5.0` in `WifiBoard.trigger()`. Reproduced directly: a fake/unreachable
OTA image URL gets a fast 202 from the board's /ota handler, but the real flow (a live local OtaServer + trigger)
occasionally takes just over 5s. Not a dead board — LABID/HTTPS/USB all answered cleanly when checked mid-run.
Fixed in 0ab9b22: timeout widened to 10s with one retry; trigger() now returns -1 instead of leaking a raw urllib
exception. Unit-tested (host/tests/test_wifi_trigger_retry.py). Re-verifying on the board before the full 100-cycle run.
