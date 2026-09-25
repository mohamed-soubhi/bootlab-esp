# BL-072 gate: the second board takes WiFi and BLE OTA from the workstation (2026-09-25 23:55, board 2)

Board 2 (ex-Zephyr hardware flashed with the IDF app; UID ACA7042C3B04, COM12, 192.168.1.153), driven from the same native-Windows workstation as board 1 with its own
rig file (`host/config/rig-board2.yaml`), OTA server port 8444, keys and credentials of the lab.

| step | image | transport | before | after |
|---|---|---|---|---|
| 1 | build_v2 (2.0.0) | WiFi | 1.0.0 slot 0 | 2.0.0 slot 1, confirmed=1, uid ACA7042C3B04 |
| 2 | build (1.0.0) | BLE | 2.0.0 slot 1 | 1.0.0 slot 0, confirmed=1, uid ACA7042C3B04 |

The BLE scan found `AC:A7:04:2C:3B:06` (board 2's own address), not board 1's. Board 2 ends on confirmed v1. Files: `update_*.log` (update CLI output), `console_*.log.gz` (raw board
console). Meets the first BL-072 acceptance criterion (second board runs the IDF app, WiFi and BLE OTA proven from the workstation).
