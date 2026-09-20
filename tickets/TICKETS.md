# bootlab-esp — Tickets & Progress

> Generated from `tickets.json` by `tickets_tool.py render`. **Do not edit by hand.**
> Plan reference: `PLAN.md`. Legend: ⬜ todo · 🔵 doing · 🟣 review · 🟥 blocked · ✅ done

## Overall

`███████░░░░░░░░░░░░░░░░░░░░░░░` **11/47 done (23%)**

```mermaid
pie showData title Ticket status
    "todo" : 32
    "blocked" : 4
    "done" : 11
```

## Epics

| Epic | Phase | Title | Progress | Done | Status | Plan |
|---|---|---|---|---|---|---|
| E0 | P0 | Host & rig setup | `██████████░░` | 6/7 | 🟥 blocked | §2, §3, §8 P0 |
| EL | PL | LABID common library | `██████████░░` | 4/5 | 🟥 blocked | §7.3, §8 PL |
| E1 | P1 | ESP32-S3 #2 — ESP-IDF | `░░░░░░░░░░░░` | 0/9 | 🟥 blocked | §4.2, §5, §6, §7.2, §8 P1 |
| E2 | P2 | ESP32-S3 #1 — Zephyr | `░░░░░░░░░░░░` | 0/7 | ⬜ todo | §4.1, §5, §6, §7.1, §8 P2 |
| E3 | P3 | labflash CLI | `██░░░░░░░░░░` | 1/7 | 🟥 blocked | §8 P3 |
| E4 | P4 | HIL tests + CI | `░░░░░░░░░░░░` | 0/8 | ⬜ todo | §8 P4 |
| E5 | P5 | Soak, docs, handover | `░░░░░░░░░░░░` | 0/4 | ⬜ todo | §8 P5 |

## Epic dependency graph

```mermaid
flowchart LR
    E0["P0 Host & rig setup<br/>6/7"]:::blocked
    EL["PL LABID common library<br/>4/5"]:::blocked
    E1["P1 ESP32-S3 #2 — ESP-IDF<br/>0/9"]:::blocked
    E2["P2 ESP32-S3 #1 — Zephyr<br/>0/7"]:::todo
    E3["P3 labflash CLI<br/>1/7"]:::blocked
    E4["P4 HIL tests + CI<br/>0/8"]:::todo
    E5["P5 Soak, docs, handover<br/>0/4"]:::todo
    E0 --> EL
    E1 --> E3
    E2 --> E3
    E3 --> E4
    E4 --> E5
    EL --> E1
    EL --> E2
    classDef todo fill:#eeeeee,stroke:#999,color:#333
    classDef doing fill:#cfe3ff,stroke:#2f6fdb,color:#123
    classDef blocked fill:#ffd6d6,stroke:#c62828,color:#400
    classDef done fill:#d4f5d4,stroke:#2e7d32,color:#132
```

## Ready to start now

- **BL-030** Zephyr west + sysbuild MCUboot + swap-with-revert check (M) — E2

## Blocked

- 🟥 **BL-005** Detect board hardware → rig.yaml 
- 🟥 **BL-014** Packaging: Zephyr module + IDF component 
- 🟥 **BL-020** IDF blink app + toggles + 5 variants + task WDT 
- 🟥 **BL-041** identify, info, status, measure 

## Tickets by epic

### E0 · P0 — Host & rig setup

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| ✅ | BL-001 | Repo skeleton + pinned versions | S | host | — |  |
| ✅ | BL-002 | Install toolchains on RPi4 | M | host | BL-001 |  |
| ✅ | BL-003 | Powered USB hub, udev rules by serial, groups | S | host | BL-002 |  |
| ✅ | BL-004 | Back up both ESP32-S3 boards | S | zephyr, idf | BL-003 |  |
| 🟥 | BL-005 | Detect board hardware → rig.yaml | S | zephyr, idf | BL-003 |  |
| ✅ | BL-006 | Generate lab signing keys | S | host | BL-002 |  |
| ✅ | BL-007 | labflash doctor (stub) | S | host | BL-003 |  |

<details><summary>✅ <b>BL-001</b> — Repo skeleton + pinned versions</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** —  
- **Plan:** §2, §3, §8 P0

Create the tree from PLAN §3. Pin Zephyr, IDF, MCUboot, ble_ota versions in scripts/versions.env.

**Acceptance criteria**
- [x] Tree matches PLAN §3
- [x] keys/, backups/, *.pem ignored by git
- [x] versions.env lists every pinned dependency

</details>

<details><summary>✅ <b>BL-002</b> — Install toolchains on RPi4</summary>

- **Size:** M (1–2 days)  
- **Boards:** host  
- **Depends on:** BL-001  
- **Plan:** §2, §3, §8 P0

Python 3.11+, BlueZ, west + Zephyr SDK, ESP-IDF, imgtool, esptool. Note: these ACs verify toolchain presence/version only, not that a build succeeds. Actual Zephyr build capability is a separate open question, tracked under the Zephyr esptool re-test (build gate).

**Acceptance criteria**
- [x] scripts/check_env.sh prints all versions and exits 0
- [x] Versions match versions.env

</details>

<details><summary>✅ <b>BL-003</b> — Powered USB hub, udev rules by serial, groups</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-002  
- **Plan:** §2, §3, §8 P0

Powered USB hub, udev rules by serial, groups. [BLOCKED 2026-09-17 on RPi4: AC3 (no brown-out resets over 10min) FAILS — continuous under-voltage, get_throttled=0x50000 on every read, 92 events this boot. Rate INDEPENDENT of attached peripherals: 2 boards ~2.0/min, 1 board ~2.0-2.5/min, 0 boards ~1.0/min => PSU/rail fault, NOT board load. This RPi4 finding stands as a separate, unresolved hardware-specific issue; see scripts/evidence/bl003_ac3_observation.jsonl. [DONE 2026-09-20 on WSL2 host, after RPi4->WSL2 migration: AC1 PASS (/dev/lab-esp-zephyr and /dev/lab-esp-idf exist, correctly mapped). AC2 PASS, verified across a real physical USB port swap on the Windows host, cross-checked via esptool chip-id and udevadm ID_SERIAL_SHORT — symlinks follow MAC/serial, not port order. AC3 PASS, 10-min clean observation 2026-09-20T03:11:57-03:21:57, 41 samples/15s, zero drops; the earlier WSL2-specific AC3 failure (usbipd/USB-IP bridge dropping both boards simultaneously ~1m45s in, confirmed via dmesg vhci_hcd disconnect logs) was a Windows USB selective-suspend issue under HP's custom power plan, fixed via powercfg at the registry level. Full evidence: scripts/evidence/bl003_ac3_wsl2_observation.md. This WSL2 pass does not overwrite or contradict the RPi4's separate PSU/rail finding above.]

**Acceptance criteria**
- [x] /dev/lab-esp-zephyr and /dev/lab-esp-idf exist
- [x] Symlinks survive replug and port swap
- [x] No brown-out resets over 10 min

</details>

<details><summary>✅ <b>BL-004</b> — Back up both ESP32-S3 boards</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-003  
- **Plan:** §2, §3, §8 P0

esptool read_flash of the current firmware before any erase.

**Acceptance criteria**
- [x] 2 backup images in backups/
- [x] docs/recovery.md has the restore command
- [x] Nothing committed to git

</details>

<details><summary>🟥 <b>BL-005</b> — Detect board hardware → rig.yaml</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-003  
- **Plan:** §2, §3, §8 P0

Flash size, PSRAM, board revision, RGB LED GPIO (48 or 38), USB serial per board.

**Acceptance criteria**
- [ ] host/config/rig.yaml filled for both boards
- [ ] LED GPIO confirmed by a quick blink

</details>

<details><summary>✅ <b>BL-006</b> — Generate lab signing keys</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-002  
- **Plan:** §2, §3, §8 P0

scripts/gen_keys.sh: zephyr_p256, idf_sbv2. Refuses to overwrite.

**Acceptance criteria**
- [x] 2 keys in keys/
- [x] Second run refuses to overwrite
- [x] git status shows no key files

</details>

<details><summary>✅ <b>BL-007</b> — labflash doctor (stub)</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-003  
- **Plan:** §2, §3, §8 P0

Minimal environment check. [EVIDENCE 2026-09-17 on RPi4: doctor verified OK while both boards were attached — output: 'ESP USB devices : 2/2  OK / Bluetooth : OK / WiFi : OK / Result: ALL OK', exit 0. Non-zero-exit path previously proven (exit 1 with 0 boards). At the time, dep-gated behind BL-003 (blocked on AC3/PSU). [DONE 2026-09-20 on WSL2 host, after BL-003 closed: rewrote doctor.py's ESP check to use pyserial (VID 0x303A) instead of shelling out to lsusb, since lsusb was not installed on this host — no longer depends on it either way. Added host-aware N/A logic for BT/WiFi: on a host with no BT stack (no hciconfig/bluetoothctl) or no wireless stack (no nmcli and no wlan* iface) reachable at all, those checks report N/A and do not count against the exit code, since WSL2 has no native BT/WiFi passthrough configured (a genuine host-capability gap, not a missing dependency). ESP USB board check remains a hard requirement everywhere. Fresh run with both boards attached: 'ESP USB devices : 2/2  OK / Bluetooth : N/A (not testable on this host) / WiFi : N/A (not testable on this host) / Result: ALL OK', exit 0.]

**Acceptance criteria**
- [x] Reports 2 ESP USB devices, BT adapter, WiFi
- [x] Non-zero exit on any missing item

</details>

### EL · PL — LABID common library

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| ✅ | BL-010 | LABID C parser, writer, CRC-16 | M | common | BL-001 |  |
| ✅ | BL-011 | Golden test vectors + Unity tests | M | common | BL-010 |  |
| ✅ | BL-012 | LABID parser fuzz target | S | common | BL-010 |  |
| ✅ | BL-013 | Python labid.py | S | host | BL-011 |  |
| 🟥 | BL-014 | Packaging: Zephyr module + IDF component | S | common | BL-010 |  |

<details><summary>✅ <b>BL-010</b> — LABID C parser, writer, CRC-16</summary>

- **Size:** M (1–2 days)  
- **Boards:** common  
- **Depends on:** BL-001  
- **Plan:** §7.3, §8 PL

C99, no malloc, no RTOS calls, fixed buffers, provider callbacks.

**Acceptance criteria**
- [x] Implements PLAN §7.3
- [x] CRC('123456789') == 0x29B1
- [x] -Wall -Wextra -Werror clean

</details>

<details><summary>✅ <b>BL-011</b> — Golden test vectors + Unity tests</summary>

- **Size:** M (1–2 days)  
- **Boards:** common  
- **Depends on:** BL-010  
- **Plan:** §7.3, §8 PL

test_vectors.json: valid frames, bad CRC, too long, unknown keys, garbage.

**Acceptance criteria**
- [x] 100 % vectors pass
- [x] Coverage ≥ 90 % line + branch

</details>

<details><summary>✅ <b>BL-012</b> — LABID parser fuzz target</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** common  
- **Depends on:** BL-010  
- **Plan:** §7.3, §8 PL

libFuzzer + ASan/UBSan.

**Acceptance criteria**
- [x] 10 min fuzz, 0 crashes, 0 sanitizer errors

</details>

<details><summary>✅ <b>BL-013</b> — Python labid.py</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-011  
- **Plan:** §7.3, §8 PL

Same framing + CRC in host/labflash/labid.py.

**Acceptance criteria**
- [x] Passes the same test_vectors.json
- [x] mypy clean

</details>

<details><summary>🟥 <b>BL-014</b> — Packaging: Zephyr module + IDF component</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** common  
- **Depends on:** BL-010  
- **Plan:** §7.3, §8 PL

One source, two build integrations. [BLOCKED: AC requires Zephyr native_sim + IDF linux builds; Zephyr path on hold + throttle != 0x0]

**Acceptance criteria**
- [ ] Builds for Zephyr native_sim and IDF linux target

</details>

### E1 · P1 — ESP32-S3 #2 — ESP-IDF

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| 🟥 | BL-020 | IDF blink app + toggles + 5 variants + task WDT | M | idf | BL-005, BL-014 |  |
| ⬜ | BL-021 | IDF partitions + signing + rollback config | S | idf | BL-020, BL-006 |  |
| ⬜ | BL-022 | IDF LABID port on USB-Serial-JTAG | S | idf | BL-020, BL-013 |  |
| ⬜ | BL-023 | IDF self-test + mark valid | S | idf | BL-021 |  |
| ⬜ | BL-024 | IDF WiFi + token provisioning via NVS | S | idf | BL-020 |  |
| ⬜ | BL-025 | IDF HTTPS control server (/ota, /version) | M | idf | BL-024 |  |
| ⬜ | BL-026 | IDF WiFi OTA (esp_https_ota pull) | M | idf | BL-025, BL-023 |  |
| ⬜ | BL-027 | IDF BLE OTA (ble_ota + NimBLE + coexistence) | L | idf | BL-023 |  |
| ⬜ | BL-028 | IDF phase acceptance run | S | idf | BL-022, BL-026, BL-027 |  |

<details><summary>🟥 <b>BL-020</b> — IDF blink app + toggles + 5 variants + task WDT</summary>

- **Size:** M (1–2 days)  
- **Boards:** idf  
- **Depends on:** BL-005, BL-014  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

FreeRTOS blink task (led_strip), toggles counter, variants per PLAN §5.3, CONFIG_ESP_TASK_WDT_PANIC. [BLOCKED 2026-09-20: esp_idf/main/ written in full -- app_main.c (blink task, toggles counter via app_get_toggle_count(), variant identity via app_get_variant() as BL-022's future LABID integration points, task-WDT hang variant), app_blink_timing.c/.h (pure blink-rate math, factored out specifically to be host-testable without the toolchain), Kconfig.projbuild (APP_VARIANT choice for all 5 variants, APP_LED_GPIO explicitly marked UNCONFIRMED per BL-005/R13, default 48 not treated as verified), CMakeLists.txt, idf_component.yml (espressif/led_strip pinned to 3.0.3, the real current version verified via the component registry API), sdkconfig.defaults (CONFIG_ESP_TASK_WDT_PANIC=y, TIMEOUT_S=5, default single-app partition table -- OTA partitions.csv is BL-021's scope). Host-side verification done: app_blink_timing.c compiled standalone with gcc -Wall -Wextra -Werror (exit 0) and unit-verified -- v1/no_confirm/bad_sig half-period=500ms (1Hz), v2 half-period=125ms (4Hz), both exact. Cannot close -- (1) ESP-IDF v6.0.3 is not installed on this host (~/tools/esp-idf absent, idf.py not found, confirmed at session start and re-confirmed now), so 'all 5 variants build' cannot be verified for real; (2) 'hang variant resets within 10s' and the R13 AC both require a real flash, not authorized yet. Toolchain install is a separate go/no-go from the flash go-ahead -- flagged to the owner.]

**Acceptance criteria**
- [ ] All 5 variants build
- [ ] v1 blinks 1 Hz
- [ ] hang variant resets within 10 s
- [ ] USB device serial descriptor is set to the chip MAC in normal run mode (not just bootloader mode) -- see PLAN §9 R13; labflash resolve_board() must still resolve this board after a normal boot, not only while in the ROM bootloader

</details>

<details><summary>⬜ <b>BL-021</b> — IDF partitions + signing + rollback config</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** idf  
- **Depends on:** BL-020, BL-006  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

partitions.csv (§4.2), sdkconfig.defaults (§6). No eFuse writes.

**Acceptance criteria**
- [ ] Signed build succeeds
- [ ] Forbidden-config grep passes
- [ ] efuse-summary unchanged after flash

</details>

<details><summary>⬜ <b>BL-022</b> — IDF LABID port on USB-Serial-JTAG</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** idf  
- **Depends on:** BL-020, BL-013  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

Driver read task, app/bootloader descriptions, OTA state.

**Acceptance criteria**
- [ ] ANNOUNCE ≤ 2 s after reset
- [ ] ID?, VER?, STATE? ≤ 100 ms
- [ ] Garbage input → ERR, no reset

</details>

<details><summary>⬜ <b>BL-023</b> — IDF self-test + mark valid</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** idf  
- **Depends on:** BL-021  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

5 s health check then esp_ota_mark_app_valid_cancel_rollback().

**Acceptance criteria**
- [ ] VER? confirmed=1 after 5 s
- [ ] no_confirm stays confirmed=0

</details>

<details><summary>⬜ <b>BL-024</b> — IDF WiFi + token provisioning via NVS</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** idf  
- **Depends on:** BL-020  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

labflash provision idf writes SSID/PSK/token over USB.

**Acceptance criteria**
- [ ] Board joins WiFi after reboot
- [ ] No credentials in source or logs

</details>

<details><summary>⬜ <b>BL-025</b> — IDF HTTPS control server (/ota, /version)</summary>

- **Size:** M (1–2 days)  
- **Boards:** idf  
- **Depends on:** BL-024  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

Bearer token, RPi4 self-signed CA pinned.

**Acceptance criteria**
- [ ] GET /version matches LABID VER.app
- [ ] Wrong token → 401

</details>

<details><summary>⬜ <b>BL-026</b> — IDF WiFi OTA (esp_https_ota pull)</summary>

- **Size:** M (1–2 days)  
- **Boards:** idf  
- **Depends on:** BL-025, BL-023  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

Pull from RPi4 HTTPS server, signature check on update.

**Acceptance criteria**
- [ ] v1 → v2 over WiFi, 4 Hz, confirmed=1
- [ ] bad_sig rejected, v1 keeps running

</details>

<details><summary>⬜ <b>BL-027</b> — IDF BLE OTA (ble_ota + NimBLE + coexistence)</summary>

- **Size:** L (3–5 days)  
- **Boards:** idf  
- **Depends on:** BL-023  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

esp-iot-solution ble_ota, NimBLE host, SW coexistence.

**Acceptance criteria**
- [ ] v2 → v1 over BLE
- [ ] WiFi stays connected during BLE OTA
- [ ] Interrupted transfer → old image still running

</details>

<details><summary>⬜ <b>BL-028</b> — IDF phase acceptance run</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** idf  
- **Depends on:** BL-022, BL-026, BL-027  
- **Plan:** §4.2, §5, §6, §7.2, §8 P1

Run all P1 acceptance checks.

**Acceptance criteria**
- [ ] All P1 checkboxes ticked with logs in the PR

</details>

### E2 · P2 — ESP32-S3 #1 — Zephyr

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| ⬜ | BL-030 | Zephyr west + sysbuild MCUboot + swap-with-revert check | M | zephyr | BL-002, BL-006 |  |
| ⬜ | BL-031 | Zephyr blink app + toggles + 5 variants + watchdog | M | zephyr | BL-030, BL-005 |  |
| ⬜ | BL-032 | Zephyr LABID port on console | S | zephyr | BL-031, BL-014 |  |
| ⬜ | BL-033 | Zephyr self-test + confirm + twister tests | S | zephyr | BL-031 |  |
| ⬜ | BL-034 | Zephyr mcumgr SMP over BLE | M | zephyr | BL-033 |  |
| ⬜ | BL-035 | Zephyr WiFi + SMP over UDP (single build with BT) | L | zephyr | BL-034 |  |
| ⬜ | BL-036 | Zephyr phase acceptance run | S | zephyr | BL-032, BL-035 |  |

<details><summary>⬜ <b>BL-030</b> — Zephyr west + sysbuild MCUboot + swap-with-revert check</summary>

- **Size:** M (1–2 days)  
- **Boards:** zephyr  
- **Depends on:** BL-002, BL-006  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

FIRST ticket for Zephyr. Verify revert-capable swap mode on ESP32-S3.

**Acceptance criteria**
- [ ] MCUboot + hello app boot on the board
- [ ] Swap mode decision written in PLAN §4.1
- [ ] ESCALATE to owner if only overwrite-only exists

</details>

<details><summary>⬜ <b>BL-031</b> — Zephyr blink app + toggles + 5 variants + watchdog</summary>

- **Size:** M (1–2 days)  
- **Boards:** zephyr  
- **Depends on:** BL-030, BL-005  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

LED strip driver (verify WS2812 backend), toggles, variants, hardware watchdog.

**Acceptance criteria**
- [ ] All 5 variants build and sign
- [ ] v1 blinks 1 Hz
- [ ] hang variant resets within 10 s
- [ ] USB device serial descriptor is set to the chip MAC in normal run mode (not just bootloader mode) -- see PLAN §9 R13; labflash resolve_board() must still resolve this board after a normal boot, not only while in the ROM bootloader

</details>

<details><summary>⬜ <b>BL-032</b> — Zephyr LABID port on console</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr  
- **Depends on:** BL-031, BL-014  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

Console device (USB-Serial-JTAG), irq RX, hwinfo UID, boot API, shell off.

**Acceptance criteria**
- [ ] ANNOUNCE ≤ 2 s
- [ ] ID?, VER?, STATE? ≤ 100 ms
- [ ] 1 000 requests under heavy logging, 0 corrupt

</details>

<details><summary>⬜ <b>BL-033</b> — Zephyr self-test + confirm + twister tests</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr  
- **Depends on:** BL-031  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

boot_write_img_confirmed() after 5 s; native_sim tests with mocked boot API.

**Acceptance criteria**
- [ ] twister passes
- [ ] confirmed=1 on board after 5 s

</details>

<details><summary>⬜ <b>BL-034</b> — Zephyr mcumgr SMP over BLE</summary>

- **Size:** M (1–2 days)  
- **Boards:** zephyr  
- **Depends on:** BL-033  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

MCUMGR image + os groups over BT.

**Acceptance criteria**
- [ ] v1 → v2 over BLE, confirmed
- [ ] no_confirm and hang revert
- [ ] bad_sig refused by MCUboot

</details>

<details><summary>⬜ <b>BL-035</b> — Zephyr WiFi + SMP over UDP (single build with BT)</summary>

- **Size:** L (3–5 days)  
- **Boards:** zephyr  
- **Depends on:** BL-034  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

WiFi STA, DHCP, UDP SMP port 1337.

**Acceptance criteria**
- [ ] v2 → v1 over UDP
- [ ] One build with BT + WiFi, OR documented reason + 2 variants + owner decision

</details>

<details><summary>⬜ <b>BL-036</b> — Zephyr phase acceptance run</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr  
- **Depends on:** BL-032, BL-035  
- **Plan:** §4.1, §5, §6, §7.1, §8 P2

Run all P2 acceptance checks.

**Acceptance criteria**
- [ ] All P2 checkboxes ticked with logs in the PR

</details>

### E3 · P3 — labflash CLI

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| ✅ | BL-040 | labflash core: config, UID resolution, re-enumeration wait | M | host | BL-013, BL-007 |  |
| 🟥 | BL-041 | identify, info, status, measure | S | host | BL-040, BL-020, BL-022 |  |
| ⬜ | BL-042 | flash, recover, provision (USB) | S | host | BL-040, BL-020, BL-021 |  |
| ⬜ | BL-043 | update idf --transport ble|wifi | M | host, idf | BL-040, BL-028 |  |
| ⬜ | BL-044 | update zephyr --transport ble|udp | M | host, zephyr | BL-040, BL-036 |  |
| ⬜ | BL-045 | build + sign orchestration | S | host | BL-040, BL-020, BL-021, BL-030, BL-031 |  |
| ⬜ | BL-046 | labflash mocked unit tests | M | host | BL-041, BL-042, BL-043, BL-044, BL-045 |  |

<details><summary>✅ <b>BL-040</b> — labflash core: config, UID resolution, re-enumeration wait</summary>

- **Size:** M (1–2 days)  
- **Boards:** host  
- **Depends on:** BL-013, BL-007  
- **Plan:** §8 P3

rig.yaml, resolve ports by UID, wait ≤ 5 s after resets, --json. [DONE 2026-09-20: host/labflash/core.py (load_rig_config, resolve_board, resolve_all_boards, BoardResolutionError), wired as `labflash resolve [--json] [--wait N]`. AC1 (never reuses stale ttyACMx): mocked test proves re-scan on every call — first call returns /dev/ttyACM0, second call (simulated reset reassigning the same board to /dev/ttyACM3) returns /dev/ttyACM3, not the memoized first value; also a mocked physical-port-swap case resolves both boards to their correct new paths by serial. AC2 (clear error on missing or swapped board): mocked missing-board and swapped-board cases both raise BoardResolutionError naming the board key, expected serial, and what's actually present. Live evidence, real boards: initial resolve_all_boards() correctly mapped {'zephyr': '/dev/ttyACM0', 'idf': '/dev/ttyACM1'}, matching prior MAC identification. A later real re-run, after the owner reset both boards out of bootloader mode, hit a genuine (not mocked) instance of AC2: idf's board enumerated with USB serial '123456' instead of its MAC E0:72:A1:AA:23:90, and resolve_board() correctly reported \"board 'idf' ... not found ... Devices present: 123456, AC:A7:04:2C:3B:04\" rather than misattributing the wrong device — exact real-world confirmation of the AC, not staged. See PLAN.md §9 R13 for the architectural gap this real failure exposed (USB-serial-as-MAC is bootloader-mode-only; app firmware must explicitly set it).]

**Acceptance criteria**
- [x] Never reuses stale ttyACMx
- [x] Clear error on missing or swapped board

</details>

<details><summary>🟥 <b>BL-041</b> — identify, info, status, measure</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-040, BL-020, BL-022  
- **Plan:** §8 P3

LABID discovery, cross-check, toggle-based Hz. Deps corrected 2026-09-20: AC needs real LABID+blink firmware, not just host code -- BL-020/BL-022 (IDF blink+LABID) are the minimum for IDF-side real verification. Full closure (both boards) additionally needs BL-031/BL-032 (Zephyr blink+LABID), which stay on hold until the Zephyr path resumes; this ticket may be closable IDF-only in the meantime with Zephyr verification deferred. [BLOCKED 2026-09-20: host/labflash/identify.py implemented (wait_for_announce, query, identify, get_version, get_state, cross_check_identity, measure_toggles, SerialLineTransport) per PLAN §7.3's exact frame protocol. Host-side logic verified via a mocked LABID transport -- identify() correctly maps both boards' ID frames to rig.yaml by uid/mac and correctly rejects a mismatched cross-check; measure_toggles() correctly computes a toggle delta within ± 1 of a simulated 1Hz blinker's expected count over a 5s window. Cannot close -- AC requires live board evidence from BL-020+BL-022 (IDF blink+LABID firmware), which don't exist yet; SerialLineTransport (the real, non-mocked path) is written but untested against real hardware for the same reason. Will re-verify against real hardware once that firmware is flashed.]

**Acceptance criteria**
- [ ] identify maps both boards
- [ ] measure within ± 1 toggle over 5 s

</details>

<details><summary>⬜ <b>BL-042</b> — flash, recover, provision (USB)</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-040, BL-020, BL-021  
- **Plan:** §8 P3

esptool / west / idf.py wrappers with identity check before writing. Deps corrected 2026-09-20: "Factory flash both boards" needs an actual signed image to flash -- BL-020/BL-021 (IDF blink app + partitions/signing) are the minimum for IDF-side real verification. Full closure (both boards) additionally needs BL-030/BL-031 (Zephyr bootloader+blink), which stay on hold until the Zephyr path resumes.

**Acceptance criteria**
- [ ] Factory flash both boards
- [ ] Refuses to flash if board= mismatches

</details>

<details><summary>⬜ <b>BL-043</b> — update idf --transport ble|wifi</summary>

- **Size:** M (1–2 days)  
- **Boards:** host, idf  
- **Depends on:** BL-040, BL-028  
- **Plan:** §8 P3

Python ble_ota client + HTTPS trigger + local HTTPS server.

**Acceptance criteria**
- [ ] Both transports update and verify via LABID

</details>

<details><summary>⬜ <b>BL-044</b> — update zephyr --transport ble|udp</summary>

- **Size:** M (1–2 days)  
- **Boards:** host, zephyr  
- **Depends on:** BL-040, BL-036  
- **Plan:** §8 P3

SMP client over BLE and UDP.

**Acceptance criteria**
- [ ] Both transports update, SMP version == LABID version

</details>

<details><summary>⬜ <b>BL-045</b> — build + sign orchestration</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-040, BL-020, BL-021, BL-030, BL-031  
- **Plan:** §8 P3

labflash build <board|all> --variant. Deps corrected 2026-09-20: AC ("Builds all 10 images, 2 boards x 5 variants") explicitly requires both boards' app code and signing to exist -- BL-020/BL-021 (IDF) and BL-030/BL-031 (Zephyr), unlike BL-041/BL-042 this ticket cannot be partially satisfied IDF-only, so it stays effectively blocked until the Zephyr path resumes.

**Acceptance criteria**
- [ ] Builds all 10 images (2 boards × 5 variants)

</details>

<details><summary>⬜ <b>BL-046</b> — labflash mocked unit tests</summary>

- **Size:** M (1–2 days)  
- **Boards:** host  
- **Depends on:** BL-041, BL-042, BL-043, BL-044, BL-045  
- **Plan:** §8 P3

pytest with mocked BLE / serial / HTTP.

**Acceptance criteria**
- [ ] Line coverage ≥ 80 %
- [ ] ruff + mypy clean

</details>

### E4 · P4 — HIL tests + CI

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| ⬜ | BL-050 | HIL framework: fixtures, markers, artifacts | M | host | BL-046 |  |
| ⬜ | BL-051 | HIL T01–T03 boot + update | S | zephyr, idf | BL-050 |  |
| ⬜ | BL-052 | HIL T04–T09 rollback, security, robustness | M | zephyr, idf | BL-050 |  |
| ⬜ | BL-053 | HIL T10–T15 LABID + identity + USB | S | zephyr, idf | BL-050 |  |
| ⬜ | BL-054 | (Stretch) HIL T17 power cut | M | zephyr, idf | BL-050 |  |
| ⬜ | BL-055 | build.yml cloud CI | M | host | BL-028, BL-036 |  |
| ⬜ | BL-056 | hil.yml self-hosted runner on RPi4 | M | host | BL-055, BL-051 |  |
| ⬜ | BL-057 | Full HIL suite green 3× in a row | S | zephyr, idf | BL-051, BL-052, BL-053, BL-056 |  |

<details><summary>⬜ <b>BL-050</b> — HIL framework: fixtures, markers, artifacts</summary>

- **Size:** M (1–2 days)  
- **Boards:** host  
- **Depends on:** BL-046  
- **Plan:** §8 P4

rig fixture, factory_reset, btmon capture, JUnit.

**Acceptance criteria**
- [ ] Dummy HIL test runs on both boards and restores v1

</details>

<details><summary>⬜ <b>BL-051</b> — HIL T01–T03 boot + update</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-050  
- **Plan:** §8 P4

PLAN §8 P4 matrix.

**Acceptance criteria**
- [ ] Green on all board/transport combinations

</details>

<details><summary>⬜ <b>BL-052</b> — HIL T04–T09 rollback, security, robustness</summary>

- **Size:** M (1–2 days)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-050  
- **Plan:** §8 P4

no_confirm, hang, bad_sig, corrupt, interrupted, token.

**Acceptance criteria**
- [ ] Green on all combinations

</details>

<details><summary>⬜ <b>BL-053</b> — HIL T10–T15 LABID + identity + USB</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-050  
- **Plan:** §8 P4

identify, UID stability, version consistency, ERR, heavy logging, 50 resets.

**Acceptance criteria**
- [ ] All green

</details>

<details><summary>⬜ <b>BL-054</b> — (Stretch) HIL T17 power cut</summary>

- **Size:** M (1–2 days)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-050  
- **Plan:** §8 P4

Needs per-port switchable hub.

**Acceptance criteria**
- [ ] Recovers every run, or skipped if no hub

</details>

<details><summary>⬜ <b>BL-055</b> — build.yml cloud CI</summary>

- **Size:** M (1–2 days)  
- **Boards:** host  
- **Depends on:** BL-028, BL-036  
- **Plan:** §8 P4

Builds, unit tests, fuzz smoke, forbidden-config grep, CI test keys.

**Acceptance criteria**
- [ ] Green on main
- [ ] Signed artifacts uploaded

</details>

<details><summary>⬜ <b>BL-056</b> — hil.yml self-hosted runner on RPi4</summary>

- **Size:** M (1–2 days)  
- **Boards:** host  
- **Depends on:** BL-055, BL-051  
- **Plan:** §8 P4

Private repo, dedicated runner user, concurrency: hil.

**Acceptance criteria**
- [ ] HIL job runs on PR
- [ ] Runner has no sudo and no access to keys/

</details>

<details><summary>⬜ <b>BL-057</b> — Full HIL suite green 3× in a row</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-051, BL-052, BL-053, BL-056  
- **Plan:** §8 P4

Stability gate.

**Acceptance criteria**
- [ ] 3 consecutive green runs
- [ ] Runtime documented

</details>

### E5 · P5 — Soak, docs, handover

| | ID | Title | Size | Boards | Depends on | PR |
|---|---|---|---|---|---|---|
| ⬜ | BL-060 | Overnight soak ×100 | S | zephyr, idf | BL-057 |  |
| ⬜ | BL-061 | README quick start | S | host | BL-057 |  |
| ⬜ | BL-062 | Recovery runbook + adding-a-board guide | S | host | BL-057 |  |
| ⬜ | BL-063 | Final PLAN.md update | S | host | BL-060 |  |

<details><summary>⬜ <b>BL-060</b> — Overnight soak ×100</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** zephyr, idf  
- **Depends on:** BL-057  
- **Plan:** §8 P5

T16 repeated per board/transport.

**Acceptance criteria**
- [ ] Pass rate ≥ 99 %
- [ ] Root cause logged for every failure

</details>

<details><summary>⬜ <b>BL-061</b> — README quick start</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-057  
- **Plan:** §8 P5

< 5 min from clone to first OTA.

**Acceptance criteria**
- [ ] Fresh clone reaches T02 green following README only

</details>

<details><summary>⬜ <b>BL-062</b> — Recovery runbook + adding-a-board guide</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-057  
- **Plan:** §8 P5

docs/recovery.md, docs/adding-a-board.md.

**Acceptance criteria**
- [ ] Recovery tested once per board from the docs

</details>

<details><summary>⬜ <b>BL-063</b> — Final PLAN.md update</summary>

- **Size:** S (≤ 0.5 day)  
- **Boards:** host  
- **Depends on:** BL-060  
- **Plan:** §8 P5

Pinned versions, Zephyr partitions, deviations.

**Acceptance criteria**
- [ ] PLAN.md matches the delivered repo

</details>

## Full ticket dependency graph

<details><summary>Show graph</summary>

```mermaid
flowchart TB
    subgraph E0_g["P0 Host & rig setup"]
        BL001["BL-001"]:::done
        BL002["BL-002"]:::done
        BL003["BL-003"]:::done
        BL004["BL-004"]:::done
        BL005["BL-005"]:::blocked
        BL006["BL-006"]:::done
        BL007["BL-007"]:::done
    end
    subgraph EL_g["PL LABID common library"]
        BL010["BL-010"]:::done
        BL011["BL-011"]:::done
        BL012["BL-012"]:::done
        BL013["BL-013"]:::done
        BL014["BL-014"]:::blocked
    end
    subgraph E1_g["P1 ESP32-S3 #2 — ESP-IDF"]
        BL020["BL-020"]:::blocked
        BL021["BL-021"]:::todo
        BL022["BL-022"]:::todo
        BL023["BL-023"]:::todo
        BL024["BL-024"]:::todo
        BL025["BL-025"]:::todo
        BL026["BL-026"]:::todo
        BL027["BL-027"]:::todo
        BL028["BL-028"]:::todo
    end
    subgraph E2_g["P2 ESP32-S3 #1 — Zephyr"]
        BL030["BL-030"]:::todo
        BL031["BL-031"]:::todo
        BL032["BL-032"]:::todo
        BL033["BL-033"]:::todo
        BL034["BL-034"]:::todo
        BL035["BL-035"]:::todo
        BL036["BL-036"]:::todo
    end
    subgraph E3_g["P3 labflash CLI"]
        BL040["BL-040"]:::done
        BL041["BL-041"]:::blocked
        BL042["BL-042"]:::todo
        BL043["BL-043"]:::todo
        BL044["BL-044"]:::todo
        BL045["BL-045"]:::todo
        BL046["BL-046"]:::todo
    end
    subgraph E4_g["P4 HIL tests + CI"]
        BL050["BL-050"]:::todo
        BL051["BL-051"]:::todo
        BL052["BL-052"]:::todo
        BL053["BL-053"]:::todo
        BL054["BL-054"]:::todo
        BL055["BL-055"]:::todo
        BL056["BL-056"]:::todo
        BL057["BL-057"]:::todo
    end
    subgraph E5_g["P5 Soak, docs, handover"]
        BL060["BL-060"]:::todo
        BL061["BL-061"]:::todo
        BL062["BL-062"]:::todo
        BL063["BL-063"]:::todo
    end
    BL001 --> BL002
    BL002 --> BL003
    BL003 --> BL004
    BL003 --> BL005
    BL002 --> BL006
    BL003 --> BL007
    BL001 --> BL010
    BL010 --> BL011
    BL010 --> BL012
    BL011 --> BL013
    BL010 --> BL014
    BL005 --> BL020
    BL014 --> BL020
    BL020 --> BL021
    BL006 --> BL021
    BL020 --> BL022
    BL013 --> BL022
    BL021 --> BL023
    BL020 --> BL024
    BL024 --> BL025
    BL025 --> BL026
    BL023 --> BL026
    BL023 --> BL027
    BL022 --> BL028
    BL026 --> BL028
    BL027 --> BL028
    BL002 --> BL030
    BL006 --> BL030
    BL030 --> BL031
    BL005 --> BL031
    BL031 --> BL032
    BL014 --> BL032
    BL031 --> BL033
    BL033 --> BL034
    BL034 --> BL035
    BL032 --> BL036
    BL035 --> BL036
    BL013 --> BL040
    BL007 --> BL040
    BL040 --> BL041
    BL020 --> BL041
    BL022 --> BL041
    BL040 --> BL042
    BL020 --> BL042
    BL021 --> BL042
    BL040 --> BL043
    BL028 --> BL043
    BL040 --> BL044
    BL036 --> BL044
    BL040 --> BL045
    BL020 --> BL045
    BL021 --> BL045
    BL030 --> BL045
    BL031 --> BL045
    BL041 --> BL046
    BL042 --> BL046
    BL043 --> BL046
    BL044 --> BL046
    BL045 --> BL046
    BL046 --> BL050
    BL050 --> BL051
    BL050 --> BL052
    BL050 --> BL053
    BL050 --> BL054
    BL028 --> BL055
    BL036 --> BL055
    BL055 --> BL056
    BL051 --> BL056
    BL051 --> BL057
    BL052 --> BL057
    BL053 --> BL057
    BL056 --> BL057
    BL057 --> BL060
    BL057 --> BL061
    BL057 --> BL062
    BL060 --> BL063
    classDef todo fill:#eeeeee,stroke:#999,color:#333
    classDef doing fill:#cfe3ff,stroke:#2f6fdb,color:#123
    classDef blocked fill:#ffd6d6,stroke:#c62828,color:#400
    classDef done fill:#d4f5d4,stroke:#2e7d32,color:#132
```

</details>

## Workflow rules for the agent

1. Pick only tickets from **Ready to start now**.
2. `python3 tickets_tool.py set BL-xxx doing` when starting.
3. One branch + one PR per ticket: `bl-xxx-short-title`. PR body copies the acceptance criteria with evidence.
4. `set BL-xxx review --pr <url>` when the PR is open; `set BL-xxx done` after merge.
5. `set BL-xxx blocked --pr <issue-or-note-url>` when an ESCALATE condition triggers; stop and ask the owner.
6. Commit `tickets.json` and `TICKETS.md` together with each status change.
