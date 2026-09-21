# Lessons Learned Retrospective — ESP-IDF Track

**Document:** `docs/LESSONS_LEARNED.md`  
**Date:** 2026-09-21  
**Author:** Pair Programming Agent & System Auditor  
**Status:** Complete — Owner Reviewed  
**Context:** BL-063a / Milestone gate between ESP-IDF Track and Zephyr Track

---

## 1. Introduction & Objectives

This retrospective documents the operational findings, risk outcomes, and technical traps encountered throughout the completion of the ESP-IDF track (Epics E1–E5, BL-020 through BL-063).

Per PLAN §8.0 owner replan decisions, the IDF track was completed first to harden tooling, establish rigorous verification patterns, and isolate hardware/platform quirks. The lessons synthesized here directly inform and shape the execution of the upcoming Zephyr track (P2, BL-030+) before any Zephyr implementation begins.

---

## 2. Risk Outcomes Matrix (R1 through R15)

Every project risk defined in PLAN §9 was evaluated and verified against real target behavior during the IDF track:

| Risk | Original Risk Description | IDF Track Outcome | Zephyr Track Implication | Concrete Action & Gate |
|------|---------------------------|-------------------|--------------------------|------------------------|
| **R1** | MCUboot lacks swap-with-revert on ESP32-S3 | N/A to IDF (IDF used native dual OTA partitions with anti-rollback). | **Highest risk for Zephyr.** Overwrite-only mode leaves boards unrecoverable if new firmware fails. | **Plan Action:** P2 Step 1 must explicitly verify swap-with-revert on hardware before writing app code. Escalate to owner if absent. |
| **R2** | BLE + WiFi memory / coexistence in one build | **PASS in IDF.** NimBLE + WiFi STA + HTTPS server run simultaneously within 8 MB Octal PSRAM. | Zephyr BT controller + native WiFi stack heap usage must be budgeted upfront. | **Checklist Item:** Verify Zephyr heap telemetry post-boot with both radios active. |
| **R3** | Hardware Secure Boot vs software signing | **PASS in IDF.** `CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT=y` with RSA-3072 verified without touching eFuses. | MCUboot signature verification (`CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256`) must verify in software without burning eFuses. | **Checklist Item:** Verify `sysbuild.conf` ECDSA key verification without hardware crypto eFuse flags. |
| **R4** | Accidental eFuse burn | **ZERO eFuses burned.** Bit-for-bit identical eFuse summaries verified before and after all flashing (BL-021, BL-028). | Must maintain strict prohibition of burning commands. | **Tool Action:** CI grep `scripts/check_forbidden_configs.sh` blocks any commit with eFuse burn commands or hardware secure boot. |
| **R5** | Identical boards swapped or wrong image flashed | **PASS.** Pre-write UID resolution in `labflash` cleanly aborted write attempts when board target mismatched. | Zephyr flashing must enforce identical UID checks before `west flash`. | **Tool Action:** `labflash flash` and `labflash update` check target UID against `rig.yaml` before executing any write. |
| **R6** | USB re-enumeration changes `ttyACMx` | **PASS.** Port re-resolution by UID in $\le 5$ s verified over 50 reboot cycles (BL-053). Windows `COM14` remained static. | Zephyr tests must use UID resolution rather than hardcoded tty paths. | **Tool Action:** `labflash.core.resolve_board()` retries UID query over 5-second window post-reboot. |
| **R7** | USB power budget / brownouts | **PASS on dev workstation; FAIL on RPi4.** RPi4 showed 7 brownout UV events / 10 min. Dev workstation showed 0 brownouts. | All flashing and heavy compilation must stay on dev machine; RPi4 limited to OTA dispatch. | **Plan Action:** Codified in `docs/rpi4_limitations.md`. Zephyr builds stay on workstation/CI. |
| **R8** | BlueZ flakiness / adapter hangs | **Bypassed on dev host via Windows native Bleak.** RPi4 BlueZ service is masked. | Windows Python with `bleak` is the primary BLE runner; RPi4 requires manual unmasking if used. | **Tool Action:** Host BLE scripts run via Windows Python 3.12 (`.venv_win_ble`). |
| **R9** | LABID frames interleaved with logs | **PASS.** One-fputs atomic frame writes under console lock prevented frame interleaving across 1,000 queries. | Zephyr shell must be disabled on the LABID UART or use isolated raw printks. | **Checklist Item:** In Zephyr `prj.conf`, disable `CONFIG_SHELL` on console UART. |
| **R10** | Console shell eats RX bytes | **PASS.** Dedicated ESP-IDF UART RX task (priority 2) read raw bytes cleanly. | Zephyr console UART must feed dedicated ring buffer without shell intercept. | **Checklist Item:** Wire raw UART callback in Zephyr LABID port module. |
| **R11** | Self-hosted runner exposure | **PASS.** `hil.yml` enforces passwordless sudo check (`sudo -n true` must fail) and keys isolation check. | Same security boundaries apply to Zephyr HIL runs. | **Tool Action:** `.github/workflows/hil.yml` security gate runs on all PRs. |
| **R12** | Self-reported blink hides real fault | **PASS.** Dual verification: LABID `measure` (hardware toggle frequency) matched visual and timing specs (1.00 Hz vs 4.19 Hz). | Zephyr blink must count hardware toggles inside the timer ISR. | **Checklist Item:** Implement `toggles` counter in Zephyr LED PWM/GPIO callback. |
| **R13** | USB serial descriptor across boots | **PASS.** ESP32-S3 native USB-Serial-JTAG device descriptor consistently presents chip MAC (`E0:72:A1:AA:23:90`). | Verify Zephyr CDC_ACM or USB-Serial-JTAG driver preserves chip MAC as USB serial string. | **Checklist Item:** Verify `dmesg` / `usbipd` serial descriptor under Zephyr firmware. |
| **R14** | ESP32-S3 resets into bootloader on port open | **ISOLATED.** Root cause is `usbipd-win` / WSL2 bridge dropping DTR/RTS during port attach. Native Windows serial open does not reset. | Never monitor active running firmware from WSL2 `/dev/ttyACMx`; always monitor via native Windows COM14. | **Checklist Item:** Always keep serial watch on native Windows host (`serial_watch.py COM14`). |
| **R15** | Shared `sdkconfig` across CMake `-B` dirs | **ISOLATED & FIXED.** CMake `-B build_*` directories overwrote root `sdkconfig`. Fixed with `-DSDKCONFIG=<dir>/sdkconfig`. | Zephyr uses `sysbuild` and per-application `prj.conf`, but build directories must remain isolated. | **Tool Action:** `labflash build` automatically injects per-dir configuration paths and checks output symbols. |

---

## 3. Technical Traps Encountered & Solutions

### Trap 1: WSL2 / usbipd Bridge Reset-on-Open (PLAN R14)
- **Symptom:** Opening `/dev/ttyACM0` in WSL2 via `idf.py monitor`, `minicom`, or `pyserial` caused an immediate chip reset into ROM bootloader (`rst:0x15 USB_UART_CHIP_RESET`).
- **Detour Caused:** Produced a false diagnosis during initial bring-up where an LED latched state was mistaken for a wrong GPIO assignment (GPIO38 vs GPIO48).
- **Resolution:** Decouple serial monitoring from WSL2. Use Windows-native Python script `scripts/serial_watch.py COM14` with DTR/RTS set to 0. USB attach/detach commands driven cleanly via PowerShell stdin redirection (`< /dev/null`).

### Trap 2: Shared `sdkconfig` Contamination across Variants (PLAN R15)
- **Symptom:** Running `idf.py -B build_hang` modified the shared `esp_idf/sdkconfig`. A subsequent build in `build/` silently picked up the HANG symbols, resulting in a production v1 firmware that entered an unexpected watchdog reboot loop.
- **Resolution:** Enforce per-directory configuration via `-DSDKCONFIG=<dir>/sdkconfig` and delete any root `esp_idf/sdkconfig`. Implemented post-build symbol verification in `labflash.build` to assert that `CONFIG_APP_VARIANT_*=y` matches the intended artifact before signing.

### Trap 3: Fatal Assertions on Optional Subsystems
- **Symptom:** Initial BLE firmware panicked on boot with `BLE_INIT: hci inits failed` because `ESP_ERROR_CHECK()` was called on Bluetooth controller initialization. This completely broke the WiFi OTA fallback, requiring a physical USB recovery flash.
- **Resolution:** Optional subsystems (BLE, sensors) must fail gracefully without aborting the main application or connectivity tasks. Replace `ESP_ERROR_CHECK()` with error logging on all non-essential hardware initialization.

### Trap 4: NimBLE Component Dependency Gaps
- **Symptom:** Linking `espressif/ble_ota` failed with undefined reference to `notify_sem` and missed radio initialization.
- **Resolution:** The application must explicitly initialize the ESP32 Bluetooth controller (`esp_bt_controller_init`/`enable`), initialize NimBLE host stack, and provide the application-level synchronization semaphore (`notify_sem`) expected by the component.

### Trap 5: Software Reset vs. Hardware Reset Behavior
- **Symptom:** Host scripts waiting for USB port disconnection after an OTA update hung indefinitely because ESP32-S3 software reset (`esp_restart()`) does NOT drop the USB-Serial-JTAG bus.
- **Resolution:** Only physical hardware resets or brownout power cuts drop the USB device. Host tools must not wait for port disconnection; instead, they must listen for the `$LAB,ANNOUNCE` frame or poll the version endpoint over network/serial.

### Trap 6: False Proof of OTA Rejection ("Vacuous Evidence")
- **Symptom:** During negative testing of corrupted or foreign-key signed images, the host server reported "all bytes served", which was mistakenly recorded as rejection evidence. However, TCP RST truncation had occurred, and the board had never processed the image header.
- **Resolution:** Server-side metrics are invalid for acceptance proof. Refusal evidence must be proven directly by on-target firmware logs (`Secure boot signature verification failed` in console) and confirmed by query of `$LAB,VER?` and HTTPS `/version` showing slot and version unchanged.

### Trap 7: Resource Starvation from Aggressive Polling
- **Symptom:** Polling `GET /version` at 100 ms intervals during an active WiFi OTA transfer starved the ESP32-S3 network buffers and caused mbedTLS handshake drops and OTA connection timeouts.
- **Resolution:** Keep verification polling sparse during active transfers ($\ge 2$ s intervals) and poll heavily only after the transfer completes.

### Trap 8: Octal PSRAM Timing & Initialization
- **Symptom:** ESP32-S3 boards ship with differing PSRAM interfaces (Quad vs Octal). Specifying Quad PSRAM on an Octal board causes silent memory corruption or initialization failure.
- **Resolution:** Verified via hardware detection that `lab-esp-idf` features 8 MB Octal PSRAM (AP_3v3 vendor chip). Enabled octal PSRAM mode with memory self-test in early bootloader.

---

## 4. Required Actions for the Zephyr Track (P2 Bring-Up Checklist)

Before beginning Zephyr implementation, the following checklist items are mandated:

1. **[ ] MCUboot Swap-with-Revert Verification (P2 Step 1 Gate):**
   - Build standalone MCUboot for ESP32-S3.
   - Flash to target board and verify in console logs that image swap with automatic rollback on test image failure is fully supported.
   - If only overwrite mode is supported, stop immediately and escalate to project owner.
2. **[ ] Disable Shell on Console UART:**
   - In Zephyr `prj.conf`, ensure `CONFIG_SHELL=n` on the port used for LABID communication to avoid character loss or prompt pollution.
3. **[ ] Non-Fatal Radio Initialization:**
   - Ensure Bluetooth LE and WiFi initialization in Zephyr check return codes and log warnings rather than invoking `k_panic()` or kernel faults.
4. **[ ] Isolated Build Directories:**
   - Use dedicated `west build -d build_<variant>` directories and verify `.config` symbol outputs before testing.
5. **[ ] Serial Monitoring via Windows COM Port:**
   - Maintain physical serial connection to Windows host and monitor via native tools to avoid WSL2 USB reset triggers.

---

## 5. Owner Review & Sign-Off

- **Reviewer:** Mohamed Soubhi (Project Owner)  
- **Decision:** ESP-IDF Track technical achievements, test evidence, and lessons learned accepted in full.  
- **Gate Status:** BL-063a accepted. Proceed to final HTML presentation (BL-063b) to officially lift the Zephyr development gate.
