# bootlab-esp — Dual-OS ESP32-S3 Bootloader & Resilient OTA Testbed

<div align="center">

[![Live Web Hub](https://img.shields.io/badge/🌐_Live_Web_Hub-Interactive_Lab-10b981?style=for-the-badge&logo=github)](https://mohamed-soubhi.github.io/bootlab-esp/)
[![Slide Deck](https://img.shields.io/badge/🖥️_Slide_Deck-Acceptance_Presentation-38bdf8?style=for-the-badge&logo=reveal.js)](https://mohamed-soubhi.github.io/bootlab-esp/presentation.html)
[![400 Soak Cycles](https://img.shields.io/badge/Soak_Cycles-400_Parallel_(100%25_Pass)-00ff88?style=for-the-badge&logo=espressif)](docs/presentation/evidence/RESULTS_INDEX.md)
[![Zero eFuse Risk](https://img.shields.io/badge/eFuse_Risk-Zero_(100%25_Reversible)-blue?style=for-the-badge&logo=shield)](PLAN.md)
[![CI Matrix](https://img.shields.io/badge/CI_Matrix-5%2F5_Green-brightgreen?style=for-the-badge&logo=githubactions)](https://github.com/mohamed-soubhi/bootlab-esp/actions)

<p align="center">
  A production-proven dual-stack firmware engineering and Hardware-in-the-Loop (HIL) testbed comparing<br/>
  <strong>ESP-IDF</strong> (native dual-slot OTA + anti-rollback + Secure Boot v2) and <strong>Zephyr RTOS</strong> (MCUboot swap-with-revert + MCUmgr SMP)<br/>
  on dual physical ESP32-S3 target silicon.
</p>

</div>

---

## 🎯 Interactive Demo & Showcase Links

| Asset | Description | Direct Link |
| :--- | :--- | :--- |
| 🌐 **Interactive Web Hub** | Full system overview, dual-OS matrix, and interactive engineering war-story deep dives. | [**mohamed-soubhi.github.io/bootlab-esp/**](https://mohamed-soubhi.github.io/bootlab-esp/) |
| 🖥️ **Presentation Deck** | 12-slide acceptance slide deck with target architecture, LABID framing, and test pyramid. | [**Open Standalone Deck**](https://mohamed-soubhi.github.io/bootlab-esp/presentation.html) |
| 🔬 **Raw Silicon Evidence Index** | Auditable hardware logs, JSONL execution records, and terminal captures for every soak cycle. | [**docs/presentation/evidence/RESULTS_INDEX.md**](docs/presentation/evidence/RESULTS_INDEX.md) |
| 📑 **35 Technical Traps & Lessons** | Low-level engineering retrospectives on WinRT GATT caching, COM port locks, and serial reset traps. | [**docs/LESSONS_LEARNED.md**](docs/LESSONS_LEARNED.md) |

---

## 📊 Hardware Verification & Soak Test Results

Every claim in this repository is backed by raw hardware logs recorded on real silicon (Board 1 `UID E072A1AA2390`, Board 2 `UID ACA7042C3B04`):

| # | Milestone & Scope | Execution Target | Outcome | Evidence Directory |
|---|---|---|---|---|
| **1** | **BL-060 Initial Soak** (100 cycles) | 50 WiFi HTTPS + 50 BLE OTA (v1 $\leftrightarrow$ v2) | **100 / 100 cycles (100% pass)**, 0 aborts, 3h 48m runtime | [`scripts/evidence/bl060_soak_2026-09-23d/`](scripts/evidence/bl060_soak_2026-09-23d/) |
| **2** | **BL-069 Signed Image Pool** | 13 signed images (9 valid, 2 trailers, 2 boundary) | **Signed off**: Both OTA slots verified over WiFi & BLE | [`scripts/evidence/bl069_pool_2026-09-25/`](scripts/evidence/bl069_pool_2026-09-25/) |
| **3** | **BL-067 Heavy Randomized Soak** | 200 random cycles (WiFi/BLE, valid + corrupt + hang) | **200 / 200 cycles matched model**, 100% recovery to golden slot | [`scripts/evidence/bl067_20260925/`](scripts/evidence/bl067_20260925/) |
| **4** | **BL-072 Dual-Board Parallel Soak** | 400 cycles (200 cycles per board simultaneously) | **400 / 400 cycles passed (200/200 on BOTH boards)**, 0 retries | [`scripts/evidence/bl072_two_boards_2026-09-26/`](scripts/evidence/bl072_two_boards_2026-09-26/) |
| **5** | **OTA Reset Mid-Download Root Cause** | Serial open pulsed DTR/RTS during OTA stream | **Root cause fixed**: 4/4 installs verified cleanly (Traps 34–35) | [`scripts/evidence/bl069_followup_ota_root_cause_2026-09-26/`](scripts/evidence/bl069_followup_ota_root_cause_2026-09-26/) |

---

## 🏛️ Dual-OS Architecture Comparison

| Architectural Dimension | ESP-IDF (FreeRTOS Track) | Zephyr RTOS (MCUboot Track) |
| :--- | :--- | :--- |
| **Bootloader** | Espressif 2nd-stage bootloader | MCUboot (Swap with Revert mode) |
| **App Partition Layout** | Dual 2.5 MB slots (`ota_0`, `ota_1`) | Primary + Secondary slot swap mechanics |
| **Cryptographic Signatures** | RSA-3072 / RSA-PSS (Secure Boot v2) | ECDSA P-256 (`imgtool` signed) |
| **Broadband Wi-Fi OTA** | HTTPS pull with Bearer token authentication | MCUmgr SMP over UDP (port 1337) |
| **Enclosure Bluetooth OTA** | NimBLE GATT push (UUID-based data chunks) | MCUmgr SMP over BLE |
| **Wire Telemetry Protocol** | LABID C99 ASCII framing (`$LAB,CMD*CS\n`) | Shared identical LABID C99 wire engine |
| **Rollback Handshake** | Boot self-test confirms via `esp_ota_mark_app_valid_cancel_rollback()` | `mcumgr image test` $\rightarrow$ self-test $\rightarrow$ `confirm` |
| **eFuse Policy** | **Zero eFuses burned** (100% lab reversible) | **Zero eFuses burned** (100% lab reversible) |

---

## ⚡ Quick Start: First OTA in < 5 Minutes (ESP-IDF Track)

### 1. Installation & Environment

Clone the repository and install the `labflash` host management CLI:
```bash
git clone https://github.com/mohamed-soubhi/bootlab-esp.git
cd bootlab-esp
pip install -e host
```

### 2. Identify Connected Hardware

Connect your ESP32-S3 via USB-C and run the hardware discovery tool:
```bash
python -m labflash identify
```
*Output:*
```
Board      Port             UID              MCU          Board Name
-----------------------------------------------------------------
idf        COM14            E072A1AA2390     esp32s3      idf
```

### 3. Check Factory Firmware & Blink Rate

Query live board identity, firmware slot, and verify the 1.00 Hz factory blink rate:
```bash
python -m labflash info idf
python -m labflash measure idf --expect-hz 1.0
```
*Output:*
```
=== idf on COM14 ===
Identity : UID=E072A1AA2390 MCU=esp32s3 HW=esp32s3_devkitc OS=idf-v6.0.3 Flash=16384KB
Version  : App=1.0.0 Git=1.0.0 Slot=0 Confirmed=1 Variant=v1
[PASS] toggles delta=10 in 5.00s = 1.00 Hz (expected 10 toggles, 1.0 Hz, tolerance +/- 1)
```

### 4. Perform Your First OTA Update (T02)

#### Option A: Over BLE
Transmit signed v2 firmware directly over Bluetooth Low Energy:
```bash
python -m labflash update idf \
  --image esp_idf/build_v2/bootlab_idf_blink.bin \
  --transport ble \
  --board-mac E0:72:A1:AA:23:90
```

#### Option B: Over WiFi / HTTPS
Serve signed v2 firmware via local HTTPS server and trigger update over WiFi:
```bash
python -m labflash update idf \
  --image esp_idf/build_v2/bootlab_idf_blink.bin \
  --transport wifi \
  --board-ip 192.168.1.152 \
  --token lab-bearer-token-secret-12345
```

*Expected Verification:*
```
image version 2.0.0; before: app=1.0.0 slot=0; after: app=2.0.0 slot=1
[PASS] running the new image: board reports '2.0.0', image is '2.0.0'
[PASS] slot flipped: slot 0 -> 1
[PASS] confirmed: self-test confirmed the image
[PASS] identity (uid): board E072A1AA2390, expected E072A1AA2390
UPDATE OK
```

### 5. Verify 4.00 Hz Blink Rate on v2
```bash
python -m labflash measure idf --expect-hz 4.0 --tolerance 2
```
*Output:*
```
[PASS] toggles delta=42 in 5.00s = 4.19 Hz (expected 40 toggles, 4.0 Hz, tolerance +/- 2)
```

### 6. Downgrade Back to Factory v1 (T03)
```bash
python -m labflash update idf \
  --image esp_idf/build/bootlab_idf_blink.bin \
  --transport wifi \
  --board-ip 192.168.1.152 \
  --token lab-bearer-token-secret-12345
```

---

## 🧪 Running the HIL Test Suite

Run the full Hardware-In-the-Loop test suite covering T01–T17:
```bash
# Mock mode (hardware-independent, CI-safe)
PYTHONPATH="host:." pytest tests_hil -v --mock-rig

# Live target mode (against connected hardware rig)
PYTHONPATH="host:." pytest tests_hil -v
```

---

## 🔒 Security & Architecture Guardrails

- **Zero eFuse Risk**: Permanent hardware eFuse write operations are strictly forbidden and blocked in CI.
- **Isolated Multi-Variant Builds (PLAN R15)**: Each firmware variant (`v1`, `v2`, `no_confirm`, `hang`, `bad_sig`) builds into its own isolated `-B build_*` directory with isolated sdkconfig.
- **Hardware Pre-Write Verification**: `labflash flash` and `labflash update` strictly verify MAC/serial before issuing erase or write commands.
- **Safe State Rollback**: All unconfirmed images automatically roll back to slot 0 upon watchdog timeout or reboot.

---

## 📚 Documentation & Technical References

- [PLAN.md](PLAN.md) — Comprehensive technical master plan and architecture decisions.
- [docs/LESSONS_LEARNED.md](docs/LESSONS_LEARNED.md) — 35 real-world traps, hardware bugs, and permanent defenses.
- [docs/presentation/evidence/RESULTS_INDEX.md](docs/presentation/evidence/RESULTS_INDEX.md) — Full hardware evidence catalog.
- [docs/recovery.md](docs/recovery.md) — Full raw flash recovery runbook.
- [docs/adding-a-board.md](docs/adding-a-board.md) — Guide to adding and characterizing a new board.
- [tickets/TICKETS.md](tickets/TICKETS.md) — Live project roadmap and per-track status.
