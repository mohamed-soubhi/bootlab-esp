# BL-060 soak — 100 cycles, mode: live — 2026-09-24, lab-esp-idf COM14

First COMPLETE live T16 soak on the IDF board: 100/100 cycles, 100 % pass (target ≥ 99 %),
strict `wifi,wifi,ble,ble` alternation, final state v1, no aborts, `failure_log` empty.

Command (native Windows, not WSL — R14):

```
python -m tests_hil.soak --port COM14 --board-ip 192.168.1.152 --keys-dir keys \
  --env-file credentials.env --cycles 100 --out scripts/evidence/bl060_soak_2026-09-23d
```

Wall window from `console.log`: `01:08:28` → `04:57:18` (3 h 48 m 50 s, 13 729.7 s per `report.json`).

## Result

| | WiFi | BLE |
|---|---|---|
| Cycles | 50 | 50 |
| Passes | 50 | 50 |
| min / median / mean / max duration | 29.7 / 31.9 / 31.7 / 32.9 s | 165.9 / 210.4 / 232.3 / 391.4 s |
| Throughput for the 1 249 280 B image | ~38 KB/s | 3.1–7.4 KB/s (median 5.8) |

- Both transports exercised both variants (`v1`, `v2` seen on each); slots alternate, the RSA-PSS signature
  verifies, the board self-confirms ~6 s after boot, and cycle 100 ends on `v1` (`final_state_v1: true`).
- **BLE is ~7× slower than HTTPS** and degrades across the run: first 50 BLE cycles median 193.6 s vs second 50
  median 280.5 s (+45 %); 5 cycles over 300 s (72, 75, 80, 83, 95), worst 391.4 s at cycle 95. Not a failure —
  every cycle passed — but the drift is real and is the open question left by this run
  (see `docs/LESSONS_LEARNED.md`).
- WiFi is very stable: the whole spread is 29.7–32.9 s.

## Console scan (`console.log.gz`)

| Pattern | Count | Reading |
|---|---|---|
| `rst:0xc` | 101 | 100 OTA reboots + the run's initial boot. Expected. |
| `esp-tls-mbedtls: read error :-0x0050` | 51 | Known benign: the first HTTPS probe of each OTA is reset, the retry succeeds ~1 s later. 50 cycles + 1 initial. |
| `confirmed=1` / `confirmed=0` | 1016 / 360 | `confirmed=0` is the transient window between boot and the ~6 s self-test that calls `esp_ota_mark_app_valid_cancel_rollback()`. Expected. |
| `grep -i fail` | 1 | `wifi:Coexist: Wi-Fi connect fail, apply reconnect coex policy` — RF coexistence policy line, **not** a cycle failure. |
| retry markers in `update.log` | 0 | Every host update succeeded on the first attempt. |

## Files

`cycles.jsonl` (per-cycle record), `report.json` (summary), `status.json` (final heartbeat),
`update.log` (host CLI output), `console.log.gz` (raw board capture, gzipped — 3.7 MB raw).
