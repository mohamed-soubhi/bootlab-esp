# BL-069 gate R1 — post-signature trailer accepted by the real board (2026-09-25)

**Question:** does the bootloader/OTA path accept a signed image followed by bytes after the signature sector (file size not a
multiple of 4096)? The two `unaligned_trailer` pool images rest on this.

**Result: YES, over WiFi, on both trailer images.** Board 1 (idf, UID E072A1AA2390, COM14), native Windows Python 3.12, image
served by `labflash update` over HTTPS from 192.168.1.134.

| step | image | file size | trailer | before | after |
|---|---|---:|---:|---|---|
| control | build_v2 (2.0.0) | 1,249,280 | 0 | 1.0.0 slot 0 | 2.0.0 slot 1 confirmed=1 |
| R1 (try 2) | g03 `gen-de2752f3` | 1,317,986 | 3,170 | 2.0.0 slot 1 | gen-de2752f3 slot 0 confirmed=1 |
| R1 | g09 `gen-6b593e13` | 1,841,012 | 1,908 | gen-de2752f3 slot 0 | gen-6b593e13 slot 1 confirmed=1 |
| restore | build (1.0.0) | 1,249,280 | 0 | gen-6b593e13 slot 1 | 1.0.0 slot 0 confirmed=1 |

Board left on confirmed v1, slot 0. `update_*.log` are the update CLI outputs, `console_*.log.gz` the raw board console.

**Honest note:** the very first g03 attempt FAILED: the board accepted the trigger but never pulled the image
(`host served: {}`, board still 1.0.0 slot 0). A control install of v2 immediately afterwards worked, then g03 worked on the
next attempt, so this was a transient WiFi-pull failure, not the trailer; but it is one sample each, and the run
`tests_hil.pool_install` (AC5) will show how often it happens (it retries failed steps on `--resume` and records the cause).
