# bootlab-esp — Dual-OS ESP32-S3 Bootloader & OTA Lab

A dual-stack firmware engineering and HIL testing harness comparing **ESP-IDF** (native dual-slot OTA + RSA-3072 Secure Boot v2) and **Zephyr** (MCUboot + mcumgr SMP OTA) on identical ESP32-S3 hardware.

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

## 📚 Documentation
- [PLAN.md](PLAN.md) — Comprehensive technical master plan and architecture decisions.
- [docs/recovery.md](docs/recovery.md) — Full raw flash recovery runbook.
- [docs/adding-a-board.md](docs/adding-a-board.md) — Guide to adding and characterizing a new board.
- [tickets/TICKETS.md](tickets/TICKETS.md) — Live project roadmap and per-track status.
