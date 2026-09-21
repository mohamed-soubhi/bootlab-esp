# Raspberry Pi 4 Host Environment & Limitations

**Date:** 2026-09-21  
**Target Host:** `msa-linuxRPi4` (`192.168.1.150`, Linux 6.18.39+rpt-rpi-v8 aarch64)  
**Context:** BL-056a / PLAN §8.0 Owner Decisions (2026-09-21)

---

## 1. Executive Summary & Division of Responsibility

Per owner decision on 2026-09-21 (recorded in PLAN §8.0 and `RESUME.md`), development, builds, and primary acceptance testing are hosted on the development workstation (WSL2 + native Windows tools). The Raspberry Pi 4 (`msa-linuxRPi4`) serves strictly as an auxiliary host with distinct hardware and operational limitations.

| Responsibility / Task | Primary Dev Machine (WSL2 + Windows) | Cloud CI (GitHub Actions) | Raspberry Pi 4 (`msa-linuxRPi4`) | Rationale |
|-----------------------|---------------------------------------|----------------------------|-----------------------------------|-----------|
| **Firmware Compilation** | **YES** (`labflash build`) | **YES** (`build.yml`) | **NO** | Heavy compilation trips RPi4 thermal/power limits; toolchains kept on workstation. |
| **RSA-3072 Key Storage** | **YES** (`keys/` gitignored, strict permissions) | **NO** (ephemeral CI keys only) | **NO** (Strict isolation per PLAN §8 P4) | Key isolation protects private signing keys from multi-user / network hosts. |
| **USB Serial Flash & Recovery** | **YES** (Windows `COM14` / native `esptool`) | **NO** (no hardware) | **NO** | Power-rail brownout risk during flash writes on RPi4 (see §2). |
| **BLE OTA Programming** | **YES** (Windows native `bleak`) | **NO** (no radio) | **NO** (Service masked, adapter down) | RPi4 Bluetooth stack is disabled/masked and requires sudo to configure. |
| **WiFi / HTTPS OTA Trigger** | **YES** (`labflash update idf --transport wifi`) | **NO** | **YES** (over LAN `192.168.1.150` $\to$ `192.168.1.152`) | Verified reachable; curl / HTTPS queries succeed in $\sim$1s. |
| **Post-OTA Verification** | **YES** (LABID `VER?` + `ID?` over `COM14` + HTTPS `/version`) | **NO** | **YES** (HTTPS `/version` query) | Serial LABID requires physical USB attachment; HTTPS query verifies slot and app version. |

---

## 2. Hardware & Power Constraints

### 2.1 Power Rail Instability (Under-Voltage Events)
Independent audit measurements (`docs/AUDIT_LOG.md`, 2026-09-19) established that the RPi4 host suffers from persistent, load-independent power rail instability:
- **Measured Event Rate:** 7 new under-voltage events recorded within a 10-minute observation window ($\sim$1 event every 85 seconds).
- **Throttling Flag:** Constant `throttled: 0x50000` (under-voltage has occurred and throttling active).
- **Impact on Flashing:** Flashing firmware over USB requires stable VDD33 and peak write currents. Burning bootloaders or bulk flash sectors while under-voltage dips occur risks flash block corruption. Therefore, all bulk flashing and recovery must run from the dev workstation.

### 2.2 USB Topology
- The ESP32-S3 boards are physically cabled to the workstation running native Windows COM drivers (`COM14` for `lab-esp-idf`, MAC `E0:72:A1:AA:23:90`).
- `lsusb` on `msa-linuxRPi4` reports only root USB hubs (`1d6b:0002`, `2109:3431`, `1d6b:0003`). No ESP devices are physically attached to the Pi.

---

## 3. Radio & Network Constraints

### 3.1 Bluetooth LE (BlueZ)
- **Service State:** `systemctl status bluetooth` reports:
  ```
  ○ bluetooth.service
       Loaded: masked (Reason: Unit bluetooth.service is masked.)
       Active: inactive (dead)
  ```
- **HCI Controller:** `hciconfig` reports `hci0` is in `DOWN` state (`BD Address: DC:A6:32:B1:4C:B0`).
- **Privilege Separation:** User `msa` does not possess passwordless sudo (`sudo: a password is required`), fulfilling PLAN §8 P4 security requirements for self-hosted runners, but preventing unprivileged scripts from unmasking or bringing up Bluetooth daemons.
- **Decision:** All BLE updates (`nimble-ble-ota`) are executed via native Windows Bluetooth using `bleak` as verified in BL-043 / BL-051.

### 3.2 WiFi & HTTPS Network Path
- Both `msa-linuxRPi4` (`192.168.1.150`) and `lab-esp-idf` (`192.168.1.152`) reside on the same `/24` subnet on AP `DIGIFIBRA-ubEU`.
- Network round-trip latency is $\le 2$ ms.
- HTTPS requests to `https://192.168.1.152/version` resolve cleanly and return JSON app descriptors:
  ```json
  {"app":"1.0.0","git":"1.0.0","slot":0,"confirmed":true}
  ```

---

## 4. Runbook: OTA Execution from RPi4

When triggering an OTA update from `msa-linuxRPi4`:
1. Ensure the target signed binary (`v2.bin`) is staged on the Pi or hosted on a reachable HTTP/HTTPS file server.
2. Ensure the Bearer token (stored in `credentials.env` on workstation) is passed via environment variable `OTA_TOKEN`.
3. Dispatch the OTA command:
   ```bash
   curl -k -X POST https://192.168.1.152/ota \
     -H "Authorization: Bearer ${OTA_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://192.168.1.150:8443/ota.bin"}'
   ```
4. Verify post-boot state after 10 seconds:
   ```bash
   curl -k https://192.168.1.152/version
   ```
   Expect:
   ```json
   {"app":"2.0.0","git":"2.0.0","slot":1,"confirmed":true}
   ```
