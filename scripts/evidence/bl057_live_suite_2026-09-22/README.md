# BL-057 — whole live HIL suite, lab-esp-idf COM14, Windows-native, mode: live — 2026-09-22
Command: `pytest tests_hil -m "not slow" --port COM14 --keys-dir keys --env-file credentials.env` (T16 soak excluded; T17 skips, no power hub; Zephyr gated).
| run | result | time |
|---|---|---|
| 1 | 37 passed, 6 skipped | 935 s |
| 2 | **1 FAILED**, 36 passed, 6 skipped | 802 s |
| 3 | 37 passed, 6 skipped | 1023 s |
(An earlier attempt failed on a Windows path bug in a *unit* test; fixed before run 1.)
Run 2 failure: BLE update -> `BleakCharacteristicNotFoundError 00008020` ("unhandled services changed event"): Windows returned a GATT table before discovery finished and `upload` crashed without retry. Real intermittent host-side bug. Fixed in idf_ble_ota.upload (reconnect up to 3x, then BleOtaError; unit-tested).
**BL-057 needs 3 CONSECUTIVE green runs: the streak restarts after the fix. Only run 3 predates the fix, so it does not count.**

## Streak after the BLE fix (b7cb137) — 3 consecutive, back to back
| run | result | time |
|---|---|---|
| 1 | 37 passed, 6 skipped | 871 s |
| 2 | 37 passed, 6 skipped | 842 s |
| 3 | 37 passed, 6 skipped | 872 s |
BL-057 acceptance (3x green live suite) MET. T16 soak and T17 (no hub) remain separately open. BL-057 still lists BL-056
(RPi4 runner) as an IDF dependency though these runs are from the workstation per the 2026-09-21 replan — owner decision open.
