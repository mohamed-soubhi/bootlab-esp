# LIVE HIL — T10–T15 (mode: live) — 2026-09-22, lab-esp-idf COM14
6 passed, 1 skipped (Zephyr gated) in 4.5 s, Windows-native, real LABID over serial (no HTTP stand-ins).
- T10/T11 uid E072A1AA2390, hw/mcu from rig.yaml x5 queries. T12 LABID == HTTPS app+slot (independent readers).
- T13 real bad-CRC / >200 B / garbage frames: board answered ERR crc, ERR len, uptime kept counting (no reset), then answered normally.
- T14 200/200 VER? on one connection (plan target 1000: not yet). T15 port resolved by USB serial in 0.031 s.
First live attempt of T13 failed (helper misread the board's ERR as a reply) — helper fixed, not the assertion.
T17: skips (no uhubctl, and no power-cut driver) — NOT verified.
