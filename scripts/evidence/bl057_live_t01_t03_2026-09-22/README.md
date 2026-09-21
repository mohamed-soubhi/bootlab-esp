# LIVE HIL run — T01–T03 (mode: live, NOT mock) — 2026-09-22
Board lab-esp-idf, COM14, USB serial E0:72:A1:AA:23:90 (verified before run). Windows-native python, commit f533f32+1a13ffc.
Command: `pytest tests_hil/test_t01_t03_boot_update.py --port COM14 --keys-dir keys --env-file credentials.env`
Result: 5 passed, 1 skipped (Zephyr, gated) in 502 s. Every update verified via LABID (uid, version, slot flip, confirmed) + HTTPS.
History: earlier live runs of the same tests FAILED (T03 ran v1->v1; absolute slot asserts wrong) — rig bugs, fixed in 1a13ffc.
This is ONE run. BL-057 needs 3 consecutive green runs of the whole live suite (T01-T17), so it stays open.
