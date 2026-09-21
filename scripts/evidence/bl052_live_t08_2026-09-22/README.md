# LIVE HIL — T08 interrupted transfer (mode: live) — 2026-09-22, lab-esp-idf COM14
OtaServer(abort_after_bytes=50%) declared the full Content-Length and cut the TLS connection at 624640/1249280 bytes; board accepted /ota (202),
abandoned the download, stayed on 1.0.0 slot 1 confirmed (LABID), then a normal WiFi retry updated to v2 (checks passed), teardown restored v1.
With the earlier T04/T05/T06/T07/T09 live run (bl052_live_t04_t09_2026-09-22) every test in the T04-T09 file now has a live assertion.
