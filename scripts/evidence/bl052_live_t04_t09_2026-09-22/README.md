# LIVE HIL — T04–T09 (mode: live) — 2026-09-22, lab-esp-idf COM14 (serial E0:72:A1:AA:23:90)
5 passed, 2 skipped (T08, Zephyr) in 214 s. Windows-native.
- T04 no_confirm: image booted (app/slot changed, confirmed=False), host hard reset (DTR/RTS transition sequence, proven by uptime drop), board rolled back to the previous confirmed app AND slot.
- T05 hang: image transferred, WDT reset, board recovered to previous confirmed app and slot with no host reset.
- T06 bad_sig refused, state unchanged; T07 host-side validation only; T09 wrong token 401 x2, state unchanged.
NOT verified: T08 (interrupted transfer driver missing). BL-052 stays open until T08 is real.
