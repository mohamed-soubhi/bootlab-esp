# LIVE HIL — T04–T09 (mode: live) — 2026-09-22, lab-esp-idf COM14
3 passed (T06 bad_sig really sent via WiFi and refused, running image unchanged over LABID; T07 host-side validation; T09 wrong token 401 x2, board unchanged), 4 skipped.
**NOT verified on hardware: T04 (no_confirm rollback), T05 (hang WDT rollback), T08 (interrupted transfer).** They need a host-driven board reset / raw send / abort driver; the previous "PASS" for them was a mock with no live assertion. BL-052 stays open.
