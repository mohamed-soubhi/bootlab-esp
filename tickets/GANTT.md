# Gantt — schedule, progress and dependencies (per board)

> Generated from `tickets.json` by `python3 tickets/tickets_tool.py gantt` (also refreshed by `set`).
> **Do not edit.** Bar **colours are the actual status**; bar **positions are a plan** computed from ticket
> size (S=1 d, M=2 d, L=4 d) and dependencies, starting 2026-09-16 — not a record of when work ran.
> A dependency applies to the **same board only**, so an IDF step never waits on a Zephyr one.

## Progress

- **IDF track:** `████████████████████████░░░░░░` **37/47 done**
- **Zephyr track:** `█████████████████████░░░░░░░░░` **29/41 done**

| Epic | Phase | IDF | Zephyr |
|---|---|---|---|
| E0 Host & rig setup | P0 | `██████████` 8/8 | `██████████` 6/6 |
| EL LABID common library | PL | `██████████` 4/4 | `██████████` 4/4 |
| E1 ESP32-S3 #2 — ESP-IDF | P1 | `██████████` 9/9 | — |
| E2 ESP32-S3 #1 — Zephyr | P2 | — | `█████████░` 10/11 |
| E3 labflash CLI | P3 | `██████████` 6/6 | `██████████` 6/6 |
| E4 HIL tests + CI | P4 | `████████░░` 8/10 | `██░░░░░░░░` 2/9 |
| E5 Soak, docs, handover | P5 | `██░░░░░░░░` 2/10 | `██░░░░░░░░` 1/5 |

## Gantt — IDF track

```mermaid
gantt
    title bootlab-esp — IDF track (colour = actual status, position = planned schedule)
    dateFormat YYYY-MM-DD
    axisFormat %d %b
    todayMarker stroke-width:3px,stroke:#f80,opacity:0.7
    section P0 Host & rig setup
    BL-001 Repo skeleton + pinned versions :done, bl001, 2026-09-16, 1d
    BL-002 Install toolchains on RPi4 :done, bl002, 2026-09-17, 2d
    BL-003 Powered USB hub udev rules by serial groups :done, bl003, 2026-09-19, 1d
    BL-004 Back up both ESP32-S3 boards :done, bl004, 2026-09-20, 1d
    BL-005a Detect board hardware → rig.yaml (IDF board) :done, bl005a, 2026-09-20, 1d
    BL-006 Generate lab signing keys :done, bl006, 2026-09-19, 1d
    BL-007 labflash doctor (stub) :done, bl007, 2026-09-20, 1d
    BL-014a Packaging IDF component (linux target) :done, bl014a, 2026-09-19, 1d
    section PL LABID common library
    BL-010 LABID C parser writer CRC-16 :done, bl010, 2026-09-17, 2d
    BL-011 Golden test vectors + Unity tests :done, bl011, 2026-09-19, 2d
    BL-012 LABID parser fuzz target :done, bl012, 2026-09-19, 1d
    BL-013 Python labid.py :done, bl013, 2026-09-21, 1d
    section P1 ESP32-S3 2 — ESP-IDF
    BL-020 IDF blink app + toggles + 5 variants + task W :done, bl020, 2026-09-21, 2d
    BL-021 IDF partitions + signing + rollback config :done, bl021, 2026-09-23, 1d
    BL-022 IDF LABID port on USB-Serial-JTAG :done, bl022, 2026-09-23, 1d
    BL-023 IDF self-test + mark valid :done, bl023, 2026-09-24, 1d
    BL-024 IDF WiFi + token provisioning via NVS :done, bl024, 2026-09-23, 1d
    BL-025 IDF HTTPS control server (/ota /version) :done, bl025, 2026-09-24, 2d
    BL-026 IDF WiFi OTA (esp_https_ota pull) :done, bl026, 2026-09-26, 2d
    BL-027 IDF BLE OTA (ble_ota + NimBLE + coexistence) :done, bl027, 2026-09-25, 4d
    BL-028 IDF phase acceptance run :done, bl028, 2026-09-29, 1d
    section P3 labflash CLI
    BL-040 labflash core config UID resolution re-enumer :done, bl040, 2026-09-22, 2d
    BL-041 identify info status measure :done, bl041, 2026-09-24, 1d
    BL-042 flash recover provision (USB) :done, bl042, 2026-09-24, 1d
    BL-043 update idf --transport ble|wifi :done, bl043, 2026-09-30, 2d
    BL-045 build + sign orchestration :done, bl045, 2026-09-24, 1d
    BL-046 labflash mocked unit tests :done, bl046, 2026-10-02, 2d
    section P4 HIL tests + CI
    BL-050 HIL framework fixtures markers artifacts :done, bl050, 2026-10-04, 2d
    BL-051 HIL T01–T03 boot + update :done, bl051, 2026-10-06, 1d
    BL-052 HIL T04–T09 rollback security robustness :done, bl052, 2026-10-06, 2d
    BL-053 HIL T10–T15 LABID + identity + USB :done, bl053, 2026-10-06, 1d
    BL-054 (Stretch) HIL T17 power cut :done, bl054, 2026-10-06, 2d
    BL-055 build.yml cloud CI :done, bl055, 2026-09-30, 2d
    BL-056 hil.yml self-hosted runner on RPi4 :done, bl056, 2026-10-07, 2d
    BL-057a Full HIL suite green 3× in a row (IDF board) :done, bl057a, 2026-10-08, 1d
    BL-070 hil.yml self-hosted runner on the development :bl070, 2026-10-07, 4d
    BL-071 IDF acceptance re-run from the development ma :bl071, 2026-10-11, 4d
    section P5 Soak docs handover
    BL-060 Overnight soak ×100 :done, bl060, 2026-10-09, 1d
    BL-061 README quick start :crit, bl061, 2026-10-09, 1d
    BL-062 Recovery runbook + adding-a-board guide :crit, bl062, 2026-10-09, 1d
    BL-063 Final PLAN.md update :crit, bl063, 2026-10-10, 1d
    BL-063a IDF lessons learned (retrospective) :crit, bl063a, 2026-10-15, 1d
    BL-063b HTML presentation of the IDF track :crit, bl063b, 2026-10-16, 2d
    BL-066 GitHub Pages project showcase & presentation :done, bl066, 2026-09-16, 2d
    BL-067 [Advanced] Heavy randomized OTA soak 4 good + :bl067, 2026-10-14, 4d
    BL-069 [Advanced] Random-variant image generator and :bl069, 2026-10-10, 4d
    BL-072 [Advanced] Multi-board randomized OTA soak tw :bl072, 2026-10-18, 4d
```

**Legend:** green = ✅ done · blue = 🔵 acceptance criteria pass, held only by a dependency · red = 🟥 blocked · plain = ⬜ todo · orange line = today.

### Root blockers — IDF track

| Ticket | Blocks | Why it is blocked |
|---|---|---|
| **BL-061** README quick start | 2 tickets | README content is complete and its commands were exercised during BL-043/051, but 'Fresh clone reaches T02 green following README only' was not run f… |
| **BL-062** Recovery runbook + adding-a-board guide | 2 tickets | Docs complete and the recovery evidence rests on the live BL-042 run (accepted); formally waits on BL-057 (dependency). |
| **BL-063** Final PLAN.md update | 2 tickets | Waits on BL-060. Its text also repeated the unverified soak/stability claims (PLAN 8 boxes unchecked in review); re-review after BL-057/BL-060 are re… |

### Ready to start — IDF track (todo, every dependency of this board done)

- **BL-069** [L] [Advanced] Random-variant image generator and signed image pool (varied footprint, both OTA slots)
- **BL-070** [L] hil.yml self-hosted runner on the development machine (workstation)

### Waiting-on — IDF track

| Ticket | Status | Waiting on (unfinished dependencies) |
|---|---|---|
| BL-061 README quick start | 🟥 blocked | — |
| BL-062 Recovery runbook + adding-a-board guide | 🟥 blocked | — |
| BL-063 Final PLAN.md update | 🟥 blocked | — |
| BL-063a IDF lessons learned (retrospective) | 🟥 blocked | BL-061[idf] 🟥, BL-062[idf] 🟥, BL-063[idf] 🟥, BL-071[idf] ⬜ |
| BL-063b HTML presentation of the IDF track | 🟥 blocked | BL-063a[idf] 🟥 |
| BL-067 [Advanced] Heavy randomized OTA soak 4 good + | ⬜ todo | BL-069[idf] ⬜ |
| BL-069 [Advanced] Random-variant image generator and | ⬜ todo | — |
| BL-070 hil.yml self-hosted runner on the development | ⬜ todo | — |
| BL-071 IDF acceptance re-run from the development ma | ⬜ todo | BL-070[idf] ⬜ |
| BL-072 [Advanced] Multi-board randomized OTA soak tw | ⬜ todo | BL-067[idf] ⬜ |

## Gantt — Zephyr track

```mermaid
gantt
    title bootlab-esp — Zephyr track (colour = actual status, position = planned schedule)
    dateFormat YYYY-MM-DD
    axisFormat %d %b
    todayMarker stroke-width:3px,stroke:#f80,opacity:0.7
    section P0 Host & rig setup
    BL-001 Repo skeleton + pinned versions :done, bl001, 2026-09-16, 1d
    BL-002 Install toolchains on RPi4 :done, bl002, 2026-09-17, 2d
    BL-003 Powered USB hub udev rules by serial groups :done, bl003, 2026-09-19, 1d
    BL-004 Back up both ESP32-S3 boards :done, bl004, 2026-09-20, 1d
    BL-006 Generate lab signing keys :done, bl006, 2026-09-19, 1d
    BL-007 labflash doctor (stub) :done, bl007, 2026-09-20, 1d
    section PL LABID common library
    BL-010 LABID C parser writer CRC-16 :done, bl010, 2026-09-17, 2d
    BL-011 Golden test vectors + Unity tests :done, bl011, 2026-09-19, 2d
    BL-012 LABID parser fuzz target :done, bl012, 2026-09-19, 1d
    BL-013 Python labid.py :done, bl013, 2026-09-21, 1d
    section P2 ESP32-S3 1 — Zephyr
    BL-005b Detect board hardware → rig.yaml (Zephyr boa :done, bl005b, 2026-09-20, 1d
    BL-014b Packaging Zephyr module (native_sim) :done, bl014b, 2026-09-19, 1d
    BL-030 Zephyr west + sysbuild MCUboot + swap-with-re :done, bl030, 2026-09-20, 2d
    BL-031 Zephyr blink app + toggles + 5 variants + wat :done, bl031, 2026-09-22, 2d
    BL-032 Zephyr LABID port on console :done, bl032, 2026-09-24, 1d
    BL-033 Zephyr self-test + confirm + twister tests :done, bl033, 2026-09-24, 1d
    BL-034 Zephyr mcumgr SMP over BLE :done, bl034, 2026-09-25, 2d
    BL-035 Zephyr WiFi + SMP over UDP (single build with :done, bl035, 2026-09-27, 4d
    BL-036 Zephyr phase acceptance run :done, bl036, 2026-10-01, 1d
    BL-064 Zephyr MCUboot swap breaks LABID UART RX inte :active, bl064, 2026-10-01, 2d
    BL-065 Zephyr OTA (UDP and BLE SMP) marked confirmed :done, bl065, 2026-10-01, 2d
    section P3 labflash CLI
    BL-040 labflash core config UID resolution re-enumer :done, bl040, 2026-09-22, 2d
    BL-041 identify info status measure :done, bl041, 2026-09-25, 1d
    BL-042 flash recover provision (USB) :done, bl042, 2026-09-24, 1d
    BL-044 update zephyr --transport ble|udp :done, bl044, 2026-10-02, 2d
    BL-045 build + sign orchestration :done, bl045, 2026-09-24, 1d
    BL-046 labflash mocked unit tests :done, bl046, 2026-10-04, 2d
    section P4 HIL tests + CI
    BL-050 HIL framework fixtures markers artifacts :done, bl050, 2026-10-06, 2d
    BL-051 HIL T01–T03 boot + update :bl051, 2026-10-08, 1d
    BL-052 HIL T04–T09 rollback security robustness :bl052, 2026-10-08, 2d
    BL-053 HIL T10–T15 LABID + identity + USB :bl053, 2026-10-08, 1d
    BL-054 (Stretch) HIL T17 power cut :bl054, 2026-10-08, 2d
    BL-055 build.yml cloud CI :done, bl055, 2026-10-02, 2d
    BL-056 hil.yml self-hosted runner on RPi4 :bl056, 2026-10-09, 2d
    BL-057b Full HIL suite green 3× in a row (Zephyr boa :bl057b, 2026-10-13, 2d
    BL-070 hil.yml self-hosted runner on the development :bl070, 2026-10-09, 4d
    section P5 Soak docs handover
    BL-060 Overnight soak ×100 :bl060, 2026-10-15, 1d
    BL-061 README quick start :bl061, 2026-10-15, 1d
    BL-062 Recovery runbook + adding-a-board guide :bl062, 2026-10-15, 1d
    BL-063 Final PLAN.md update :bl063, 2026-10-16, 1d
    BL-066 GitHub Pages project showcase & presentation :done, bl066, 2026-09-16, 2d
```

**Legend:** green = ✅ done · blue = 🔵 acceptance criteria pass, held only by a dependency · red = 🟥 blocked · plain = ⬜ todo · orange line = today.

### Root blockers — Zephyr track

None: nothing on this board is blocked.

### Ready to start — Zephyr track (todo, every dependency of this board done)

- **BL-052** [M] HIL T04–T09 rollback, security, robustness
- **BL-053** [S] HIL T10–T15 LABID + identity + USB
- **BL-054** [M] (Stretch) HIL T17 power cut

### Waiting-on — Zephyr track

| Ticket | Status | Waiting on (unfinished dependencies) |
|---|---|---|
| BL-051 HIL T01–T03 boot + update | ⬜ todo | BL-064[zephyr] 🔵 |
| BL-052 HIL T04–T09 rollback security robustness | ⬜ todo | — |
| BL-053 HIL T10–T15 LABID + identity + USB | ⬜ todo | — |
| BL-054 (Stretch) HIL T17 power cut | ⬜ todo | — |
| BL-056 hil.yml self-hosted runner on RPi4 | ⬜ todo | BL-051[zephyr] ⬜ |
| BL-057b Full HIL suite green 3× in a row (Zephyr boa | ⬜ todo | BL-051[zephyr] ⬜, BL-052[zephyr] ⬜, BL-053[zephyr] ⬜, BL-070[zephyr] ⬜ |
| BL-060 Overnight soak ×100 | ⬜ todo | BL-057b[zephyr] ⬜ |
| BL-061 README quick start | ⬜ todo | BL-057b[zephyr] ⬜ |
| BL-062 Recovery runbook + adding-a-board guide | ⬜ todo | BL-057b[zephyr] ⬜ |
| BL-063 Final PLAN.md update | ⬜ todo | BL-060[zephyr] ⬜ |
| BL-064 Zephyr MCUboot swap breaks LABID UART RX inte | 🔵 doing | — |
| BL-070 hil.yml self-hosted runner on the development | ⬜ todo | BL-051[zephyr] ⬜ |
