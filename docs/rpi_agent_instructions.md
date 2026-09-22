# RPi Agent Execution Plan & Guidelines: Network OTA & Modular Development

**Target Host:** `msa-linuxRPi4` (`192.168.1.150`, Linux aarch64)  
**Target Agent:** Autonomous Agent (Hermes / Local Agent)  
**Working Directory:** `/home/msa/bootlab-esp-latest`  
**Python VirtualEnv:** `/home/msa/bootlab-esp-latest/.venv`  
**Git Branch:** `master`  
**Last Updated:** 2026-09-23

---

## 1. Role, Environment & Operational Guardrails

This document instructs the autonomous agent running on `msa-linuxRPi4` on how to execute test, validation, and development tasks for the `bootlab-esp` project.

### 1.1 Strict Guardrails (Non-Negotiable)
1. **NO `sudo` Privileges:** The runner and agent operate strictly under user `msa` with no passwordless sudo (PLAN §8 P4 security compliance). Never attempt `sudo` commands.
2. **NO Access to Private Root Keys:** Root signing keys (`keys/*.pem`) reside exclusively on the primary development workstation. The RPi uses pre-signed binaries or ephemeral dev keys.
3. **NO Direct USB Flashing Without Approval:** The RPi4 has known power rail under-voltage throttling (`0x50000`). To prevent bootloader corruption, all firmware deployment from the RPi is performed **strictly over the network** (WiFi HTTPS for ESP-IDF, UDP SMP for Zephyr).
4. **Thermal Throttling Protection:** When building or compiling code on the RPi (Phase 2), always limit build parallelism to 2 jobs (`-j2`) to keep CPU temperature and power draw stable.

### 1.2 Environment Setup
Before executing any Python scripts or test tools, activate the pre-configured virtual environment:
```bash
cd /home/msa/bootlab-esp-latest
source .venv/bin/activate
```
Verify that required tools are in place:
```bash
labflash --help
python3 -c "import smpclient, bleak, pytest; print('Environment OK')"
```

---

## 2. Phase 1: Immediate Network Testing & OTA Validation

### Task 1.1: Pre-Flight Network Sanity Check
Confirm LAN reachability to both target ESP32-S3 boards:
```bash
ping -c 2 192.168.1.152  # lab-esp-idf
ping -c 2 192.168.1.153  # lab-esp-zephyr
```

Check the baseline health of the ESP-IDF board over HTTPS:
```bash
curl -k -s --connect-timeout 3 https://192.168.1.152/version
```
*Expected output:*
```json
{"app":"1.0.0","git":"1.0.0","slot":0,"confirmed":true}
```

Check the status of the self-hosted GitHub Actions runner:
```bash
ps aux | grep -i actions-runner | grep -v grep
```
*Expected:* The `actions-runner` process should be active.

---

### Task 1.2: ESP-IDF WiFi OTA Acceptance (BL-056a)
**Objective:** Validate that the RPi can orchestrate an end-to-end OTA update of `lab-esp-idf` over WiFi without physical cable access, verify the slot change, and safely restore the baseline version.

#### Step 1: Ensure Staged Signed Binaries Are Available
Ensure pre-built signed binaries (`v1.bin` and `v2.bin`) exist locally:
```bash
ls -la /home/msa/bootlab-esp-latest/esp_idf/build/esp_idf.bin 2>/dev/null || \
ls -la /home/msa/bootlab-esp-latest/ble_stage/*.bin 2>/dev/null || \
ls -la /home/msa/bootlab-esp-latest/*.bin 2>/dev/null
```
*(If binaries are not yet staged, fetch them from the workstation or download build artifacts).*

#### Step 2: Read or Set the OTA Bearer Token
Export the `OTA_TOKEN` environment variable (default provisioned value is `lab-bearer-token-default` unless overridden in credentials):
```bash
export OTA_TOKEN="${OTA_TOKEN:-lab-bearer-token-default}"
```

#### Step 3: Trigger WiFi OTA Update (v1 -> v2)
Using the built-in `labflash update` command with `--no-labid` (which delegates identity check to the board's HTTPS `/version` endpoint):
```bash
labflash update idf \
  --transport wifi \
  --board-ip 192.168.1.152 \
  --image /path/to/signed_v2.bin \
  --no-labid
```
*Alternative via direct HTTPS curl & staging server:*
1. Start an ephemeral HTTP server in the directory containing the binary:
   ```bash
   python3 -m http.server 8443 --bind 192.168.1.150 &
   HTTP_PID=$!
   ```
2. Trigger the download pull:
   ```bash
   curl -k -X POST https://192.168.1.152/ota \
     -H "Authorization: Bearer ${OTA_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://192.168.1.150:8443/signed_v2.bin"}'
   ```
3. Stop the staging server:
   ```bash
   kill $HTTP_PID
   ```

#### Step 4: Verify Slot Switch & Application Health
Wait 10 seconds for the ESP32-S3 to download the image, verify the RSA-3072 signature, set the boot partition, and reboot:
```bash
sleep 10
curl -k -s https://192.168.1.152/version
```
*Expected response:*
```json
{"app":"2.0.0","git":"2.0.0","slot":1,"confirmed":true}
```

#### Step 5: Downgrade / Restore to Factory Baseline (v2 -> v1)
Trigger the update back to `v1.bin` using the same procedure:
```bash
labflash update idf \
  --transport wifi \
  --board-ip 192.168.1.152 \
  --image /path/to/signed_v1.bin \
  --no-labid
```
Verify the board has cleanly returned to slot 0:
```bash
sleep 10
curl -k -s https://192.168.1.152/version
```
*Expected response:*
```json
{"app":"1.0.0","git":"1.0.0","slot":0,"confirmed":true}
```

#### Step 6: Generate Evidence File
Capture the command transcripts, timestamps, and curl outputs into:
`scripts/evidence/bl056a_rpi4_acceptance.md`

Update the ticket status:
```bash
python3 tickets/tickets_tool.py set BL-056a done
```

---

### Task 1.3: Zephyr UDP SMP Network Testing
**Context:**
- In Zephyr `build_v1`, only Bluetooth LE SMP is active.
- In Zephyr `build_v2`, both Bluetooth LE and WiFi UDP SMP (port 1337) are enabled.
- If the Zephyr board is running `build_v2`, test the UDP SMP transport from the RPi:

```bash
python3 scripts/test_udp_smp.py 192.168.1.153
```
*Expected:* Echo response and list of active/secondary image states in slot 0/1.

To execute a live Zephyr UDP OTA from RPi:
```bash
python3 scripts/zephyr_udp_ota.py \
  /path/to/zephyr_signed_v2.bin \
  --ip 192.168.1.153 \
  --port 1337 \
  --slot 0
```

---

## 3. Phase 2: Modular Development & Local Compilation

Once the network testing and OTA acceptance are verified, the RPi can serve as a development node for creating and adding new components, modules, and applications.

### 3.1 Toolchain Layout on RPi
- **ESP-IDF Toolchains:** Located at `/home/msa/.espressif/tools/xtensa-esp-elf/`
- **Zephyr Workspace:** Located at `/home/msa/zephyr-ws/`
- **Build System:** CMake (`/usr/bin/cmake`), Ninja, GCC, Clang

### 3.2 Standards for Adding New Modules & Applications

#### 1. Repository Structure
- **Shared Code:** Place hardware-independent C protocols, telemetry formats, and utilities in `common/` (e.g. `common/labid/`).
- **ESP-IDF Components:**
  - Independent reusable modules should be placed in `esp_idf/components/<module_name>/`.
  - Application logic and entrypoints belong in `esp_idf/main/`.
- **Zephyr Modules & Subsystems:**
  - Place Zephyr app-specific features in `esp_zephyr/app/src/`.
  - Custom device drivers or out-of-tree Zephyr modules can be linked via `zephyr-ws/modules/` or submodules.

#### 2. Compilation Rules (Thermal Safety)
Compiling large C++ codebases on Raspberry Pi 4 can saturate all 4 Cortex-A72 cores, triggering under-voltage drops (`0x50000`) and thermal throttling.
Always append `-j2` (or set `export CMAKE_BUILD_PARALLEL_LEVEL=2`):

*Compiling Zephyr Application:*
```bash
cd /home/msa/zephyr-ws
west build -b esp32s3_devkitm /home/msa/bootlab-esp-latest/esp_zephyr/app -d build_test -- -j2
```

*Compiling ESP-IDF Application:*
```bash
cd /home/msa/bootlab-esp-latest/esp_idf
# Source IDF export script if configured:
# . /path/to/esp-idf/export.sh
idf.py -B build_test build -j2
```

#### 3. Image Signing and Packaging
After compilation, the raw `.bin` or `.elf` must be packaged for OTA:
- In Phase 2 development, unsigned or dev-signed binaries can be generated using local development keys:
  ```bash
  python3 host/labflash/cli.py build --variant dev ...
  ```
- Staged binaries can then be deployed directly to the boards via the Phase 1 network OTA procedures.

---

## 4. Summary Checklist for the RPi Agent

- [ ] Activate Python venv (`source /home/msa/bootlab-esp-latest/.venv/bin/activate`).
- [ ] Ping targets (`192.168.1.152` and `192.168.1.153`).
- [ ] Query `https://192.168.1.152/version` baseline.
- [ ] Execute `BL-056a` WiFi OTA cycle (v1 -> v2 -> v1).
- [ ] Record verification evidence in `scripts/evidence/bl056a_rpi4_acceptance.md`.
- [ ] Check tickets status with `python3 tickets/tickets_tool.py check`.
- [ ] When adding new components, follow Phase 2 guidelines with `-j2` build limits.
