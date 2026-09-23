# Lessons Learned Retrospective — ESP-IDF & Zephyr Tracks

**Document:** `docs/LESSONS_LEARNED.md`  
**Date:** 2026-09-21 (ESP-IDF track), updated 2026-09-23 (Zephyr track, Sections 4-5)  
**Author:** Pair Programming Agent & System Auditor  
**Status:** ESP-IDF track complete — Owner Reviewed. Zephyr track in progress.  
**Context:** BL-063a / Milestone gate between ESP-IDF Track and Zephyr Track; Sections 4-5 added during
live Zephyr HIL work (BL-050/051/064/065).

---

## 1. Introduction & Objectives

This retrospective documents the operational findings, risk outcomes, and technical traps encountered throughout the completion of the ESP-IDF track (Epics E1–E5, BL-020 through BL-063).

Per PLAN §8.0 owner replan decisions, the IDF track was completed first to harden tooling, establish rigorous verification patterns, and isolate hardware/platform quirks. The lessons synthesized here directly inform and shape the execution of the upcoming Zephyr track (P2, BL-030+) before any Zephyr implementation begins.

---

## 2. Risk Outcomes Matrix (R1 through R15)

Every project risk defined in PLAN §9 was evaluated and verified against real target behavior during the IDF track:

| Risk | Original Risk Description | IDF Track Outcome | Zephyr Track Implication | Concrete Action & Gate |
|------|---------------------------|-------------------|--------------------------|------------------------|
| **R1** | MCUboot lacks swap-with-revert on ESP32-S3 | N/A to IDF (IDF used native dual OTA partitions with anti-rollback). | **Materialized, but not as predicted.** Swap-with-revert IS supported (`move` algorithm, verified live: `Swap type: test` -> `Starting swap using move algorithm` -> real boot). The actual risk was different: a **host-side protocol bug** (`ImageStatesWrite(confirm=True)` sent before the new image ever booted, BL-065) made MCUboot silently skip the swap while its own bookkeeping claimed success. Fixed. A SEPARATE, still-open issue (BL-064) is that a completed swap boot breaks the LABID UART RX interrupt in a way a direct flash never does — root cause not found as of 2026-09-23. | **See Section 4/5** for the full BL-064/BL-065 writeup and current status. |
| **R2** | BLE + WiFi memory / coexistence in one build | **PASS in IDF.** NimBLE + WiFi STA + HTTPS server run simultaneously within 8 MB Octal PSRAM. | Zephyr BT controller + native WiFi stack heap usage must be budgeted upfront. | **Checklist Item:** Verify Zephyr heap telemetry post-boot with both radios active. |
| **R3** | Hardware Secure Boot vs software signing | **PASS in IDF.** `CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT=y` with RSA-3072 verified without touching eFuses. | MCUboot signature verification (`CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256`) must verify in software without burning eFuses. | **Checklist Item:** Verify `sysbuild.conf` ECDSA key verification without hardware crypto eFuse flags. |
| **R4** | Accidental eFuse burn | **ZERO eFuses burned.** Bit-for-bit identical eFuse summaries verified before and after all flashing (BL-021, BL-028). | Must maintain strict prohibition of burning commands. | **Tool Action:** CI grep `scripts/check_forbidden_configs.sh` blocks any commit with eFuse burn commands or hardware secure boot. |
| **R5** | Identical boards swapped or wrong image flashed | **PASS.** Pre-write UID resolution in `labflash` cleanly aborted write attempts when board target mismatched. | Zephyr flashing must enforce identical UID checks before `west flash`. | **Tool Action:** `labflash flash` and `labflash update` check target UID against `rig.yaml` before executing any write. |
| **R6** | USB re-enumeration changes `ttyACMx` | **PASS.** Port re-resolution by UID in $\le 5$ s verified over 50 reboot cycles (BL-053). Windows `COM14` remained static. | Zephyr tests must use UID resolution rather than hardcoded tty paths. | **Tool Action:** `labflash.core.resolve_board()` retries UID query over 5-second window post-reboot. |
| **R7** | USB power budget / brownouts | **PASS on dev workstation; FAIL on RPi4.** RPi4 showed 7 brownout UV events / 10 min. Dev workstation showed 0 brownouts. | All flashing and heavy compilation must stay on dev machine; RPi4 limited to OTA dispatch. | **Plan Action:** Codified in `docs/rpi4_limitations.md`. Zephyr builds stay on workstation/CI. |
| **R8** | BlueZ flakiness / adapter hangs | **Bypassed on dev host via Windows native Bleak.** RPi4 BlueZ service is masked. | Windows Python with `bleak` is the primary BLE runner; RPi4 requires manual unmasking if used. | **Tool Action:** Host BLE scripts run via Windows Python 3.12 (`.venv_win_ble`). |
| **R9** | LABID frames interleaved with logs | **PASS.** One-fputs atomic frame writes under console lock prevented frame interleaving across 1,000 queries. | **PASS in Zephyr too** -- `CONFIG_SHELL=n` set from the start (`esp_zephyr/app/prj.conf`); `labid_port_zephyr.c`'s IRQ-driven RX + ring buffer never showed frame interleaving in any test. | Checklist item followed correctly; not the source of BL-064 (see Section 4). |
| **R10** | Console shell eats RX bytes | **PASS.** Dedicated ESP-IDF UART RX task (priority 2) read raw bytes cleanly. | **Mostly PASS, with a real caveat found live.** The IRQ-driven ring buffer (`uart_irq_callback_user_data_set` + `uart_irq_rx_enable`) works correctly on v1 and any direct-flashed build. It stops firing entirely (`irq=0, rx=0` forever) specifically after a real MCUboot swap boot -- an unresolved interaction, not a shell/console-intercept issue. See Section 4. | Checklist item ("wire raw UART callback") was done correctly; the bug is downstream of it. |
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

### Trap 8a: `keys/` private material never synced to the Windows mirror, so WiFi OTA fails instantly (BL-060)
- **Symptom:** BL-060's live soak on Windows aborted after 3 consecutive failures. The first two (WiFi transport, `variant=v2`) failed in 0.0-0.2 s with `update raised FileNotFoundError: [Errno 2] No such file or directory` -- no output at all, not even the "Updating ... over wifi" print.
- **Root cause:** `keys/` holds two classes of file: public certs (`ca.pem`, `server_cert.pem`, ...) that get `cp`'d to the Windows mirror piecemeal, and private keys (`server_key.pem`, `ca.key`, ...) that never did, because syncing has always been "copy the files I just fixed", not "copy the whole dir". `OtaServer.start()` (`host/labflash/idf_wifi_ota.py`) calls `ssl.SSLContext.load_cert_chain(certfile, keyfile)` before any progress output is printed, so a missing `server_key.pem` on Windows raised `FileNotFoundError` immediately, before the HTTPS OTA server ever started listening. BLE cycles don't build an `OtaServer` at all, so they were unaffected -- which is why only the WiFi cycles died and did so instantly.
- **Resolution:** `cp` the missing private keys (`server_key.pem`, `ca.key`) from the WSL repo's `keys/` to the Windows mirror's `keys/`. These are self-signed test-only keys (not a real secret), so a plain copy is safe.
- **Prevention:** When syncing "just the fixed files" to the Windows mirror, remember `keys/` is a directory whose *entire* contents (including files with restrictive `.rw-------` perms) matter to the live rig -- a partial sync there fails silently and only surfaces as an opaque `FileNotFoundError` deep inside `ssl`.

### Trap 8b: A clean OTA swap can still get reported as "FAILED" if a query's response races unsolicited device chatter on a shared port (BL-060, FIXED)
- **Symptom:** BL-060's soak cycle 3 (BLE, `v2`) ran the full 656 s of real hardware time -- all 305 sectors sent, board verified and rebooted -- and `update.log` still recorded `before: app=1.0.0 slot=0; after: app=1.0.0 slot=0` -> `UPDATE FAILED`. But `console.log`'s raw serial capture shows the board's own LABID `$LAB,VER` frames going `app=2.0.0,confirmed=0` at `22:25:36` and `app=2.0.0,confirmed=1` by `22:25:40` -- i.e. the swap succeeded and was confirmed within 6 s of reboot, while the host's `_poll()` (`host/labflash/update.py`) kept reading stale `app=1.0.0` for its entire 240 s timeout budget. Reproduced again on the very next soak run as an outright `KeyError: 'app'` in `board unreadable before update`.
- **Root cause, confirmed:** `query()` in `host/labflash/identify.py` sends e.g. `VER?` and returns whatever complete frame comes off the transport next, without checking its type. The IDF firmware broadcasts periodic unsolicited `VER`/`ID` pairs on its own, on the SAME wire `SharedConsolePort` (Trap 13) keeps continuously open. Before BL-060, each query opened/closed its own short-lived port, so almost never raced this. Once the port became shared and persistent, `get_version()` could receive a stray `ID` frame instead of the `VER` reply -- explaining both the `KeyError: 'app'` (an ID frame has no `app` field) and the "still pending verify" false failures (a stale/mismatched frame's stale `confirmed` value).
- **Resolution:** `query()` now checks the returned frame's type against what was requested and keeps waiting (within the same deadline) if it doesn't match, instead of returning the first frame it sees. Regression test: `host/tests/test_identify.py::test_query_skips_unsolicited_frame_of_a_different_type`.

---

## 4. Zephyr Track Traps (added 2026-09-23, live HIL work on lab-esp-zephyr)

### Trap 9: Live console capture needs a SHARED connection, not a second reader (BL-060)
- **Symptom:** `tests_hil/conftest.py`'s live `serial_capture` fixture was a stub -- "raw console not
  captured" -- because Windows COM ports are exclusive-access: a standalone second reader (like
  `scripts/serial_watch.py`) run alongside a live LABID test fails to open the port at all. Every prior
  LABID transport also opened and closed the port per query, so nothing was listening -- and console
  bytes were dropped -- during the gaps between queries, including exactly the moments (OTA apply,
  bootloader transitions) that needed to be seen.
- **Resolution:** Built `SharedConsolePort` (`host/labflash/serial_console.py`): opens the port ONCE
  and keeps it open for the whole test/run. A background thread continuously drains bytes into (a) a
  timestamped `console.log` and (b) an in-memory queue a `read1()`/`write()` transport adapter drains,
  so existing LABID query code works unmodified against the same handle instead of racing a second one.
  `close()` is a no-op (existing call sites close after every query); `shutdown()` actually releases the
  port, called once at the very end. This is what made every console-log excerpt in Sections 4-5
  possible.

### Trap 10: "Continuous reset" was a held BOOT button, not a firmware crash
- **Symptom:** Board appeared to be connecting/disconnecting on USB repeatedly, looking exactly like a
  firmware crash loop. Console watchers and `usbipd list` showed it cycling.
- **Resolution:** Actually the board was manually placed in ROM download/bootloader mode (BOOT button
  or GPIO0 jumper still held from an earlier recovery attempt), which presents a different USB identity
  than the running app -- every attempted reset just re-entered the bootloader. `esptool --before
  no-reset chip-id` connecting successfully without ever resetting is the tell: if the ROM bootloader
  answers immediately, the chip was already sitting in it. Always check "is anything physically holding
  BOOT/GPIO0" before assuming a firmware fault.

### Trap 11: Windows `usbipd bind --force` silently breaks native serial access
- **Symptom:** `usbipd list` showed a board's busid as `Shared (forced)`; Windows-native `pyserial`
  could not open the port (`FileNotFoundError` even though `Win32_PnPEntity` showed it present, or
  later `PermissionError(13, Access is denied)`).
- **Resolution:** A forced usbipd bind replaces the port's normal Windows driver with usbipd's own
  passthrough stub, even when not actively attached to WSL2. `usbipd unbind --busid <n>` (needs an
  elevated shell) restores the normal `usbser` driver and native access. `usbipd bind`/`unbind`/
  `bind --force` all require administrator privileges; plain `usbipd attach --wsl` does not.

### Trap 12: Stray `serial_watch.py` processes silently hold the port exclusively
- **Symptom:** A live test failed with `PermissionError(13, Access is denied)` opening a COM port that
  `usbipd list` and Device Manager both showed as present and healthy.
- **Resolution:** Windows COM ports are exclusive-access; an earlier diagnostic `serial_watch.py`
  session that didn't get cleanly killed (e.g. a backgrounded `Start-Process` that "looked" dead but
  wasn't) keeps holding the handle. `tasklist | findstr python` /
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId,CommandLine`
  finds them by command line; `taskkill /F /PID <n>` clears them.

### Trap 13: A held-open shared serial connection races an internal one-shot connection (BL-060 follow-up)
- **Symptom:** After wiring `SharedConsolePort` (a persistent connection held open for the whole test,
  so `console.log` captures continuously), every live OTA update started throwing
  `PermissionError`/`Access is denied` even though it worked before that change.
- **Resolution:** `run_update`/`run_update_zephyr`'s own internal pre/post LABID snapshot opened a
  SECOND, separate one-shot `SerialLineTransport` on the same port -- harmless when the console reader
  was a stub, a hard conflict once something else genuinely holds the port. Fix: thread the same
  `transport_factory` through so every caller reuses the one open connection instead of racing a
  second `open()`.

### Trap 14: `ImageStatesWrite(confirm=True)` sent too early skips the real MCUboot swap
- **Symptom:** A Zephyr SMP OTA (UDP or BLE) reported 100% uploaded and "marked permanent/confirmed",
  reset the device -- but the board came back still running the OLD image. The SMP layer's own
  `ImageStatesRead()` claimed the new image was "active", directly contradicting LABID (whose version
  string is baked into the actual running binary and cannot be faked).
- **Resolution:** `confirm=True` sent immediately after upload, before the new image had ever booted,
  let MCUboot update its own image-list bookkeeping to claim success without ever performing the
  physical slot swap. The correct sequence is `confirm=False` (marks the image test/pending, which is
  what makes MCUboot actually swap and boot into it as a trial), then let the device's own self-test
  logic call `boot_write_img_confirmed()` after it boots and passes health checks. Verified live: real
  boot log shows `Swap type: test` -> `Starting swap using move algorithm` -> genuine boot into the new
  image, self-test PASSED, confirmed. This is BL-065.

### Trap 15: An MCUboot swap boot traps unread USB FIFO bytes and starves edge-triggered RX interrupts
- **Symptom:** After Trap 14 was fixed and a real swap genuinely completes, the newly-booted image's
  LABID console UART RX interrupt never fires (`irq=0, rx=0` in the app's own instrumented heartbeat
  log, indefinitely). Reads (device -> host) still work; only writes (host -> device) are affected,
  timing out at the Windows serial driver level.
- **Investigation & Root Cause:**
  1. Isolated the `ws2812_i2s` DMA pool exhaustion under 4Hz calls (Trap 15a: mitigated via 1000ms LED hardware rate limit).
  2. Isolated the remaining post-swap failure to the USB-Serial-JTAG hardware and MCUboot boot sequence:
     - In Zephyr's `serial_esp32_usb.c`, `SERIAL_OUT_RECV_PKT` is an **edge-triggered packet reception interrupt**, not a level-sensitive FIFO non-empty interrupt.
     - During the 10-15s MCUboot move-swap, host polling (`VER?\r\n`) fills the 64-byte hardware RX FIFO.
     - MCUboot jumps to Zephyr (`((void (*)(void))entry_addr)()`) without resetting peripherals.
     - When Zephyr starts, `serial_esp32_usb_irq_rx_enable()` runs `clr_intsts_mask(SERIAL_OUT_RECV_PKT)`, clearing the interrupt status while unread bytes remain in the FIFO.
     - With data in the FIFO, the USB controller NAKs subsequent host packets. With no new packets arriving, the edge interrupt never triggers, leaving the RX loop starved forever. Direct flash worked only because `esptool` asserts DTR/RTS, issuing a hardware reset with an empty FIFO right before boot.
- **Resolution:** In `labid_port_zephyr.c`:
  1. Drain and flush pre-boot FIFO data during `labid_port_init()` before and after interrupt enable.
  2. Implement hybrid 20ms fallback polling under `irq_lock()` in `labid_thread_entry()` to guarantee unserviced bytes are drained and USB endpoints are freed even if an edge interrupt is missed.
  3. Start servicing RX immediately from boot, decoupling the 1.5s ANNOUNCE window. This is BL-064.

### Trap 16: `LiveBackend`'s hand-built test `Namespace` silently drifted from the real CLI
- **Symptom:** Every live zephyr OTA attempt through the test harness crashed with
  `AttributeError: 'Namespace' object has no attribute 'udp_port'` (then `'confirm_timeout'`), even
  though the same operation worked fine from the real `labflash` CLI.
- **Resolution:** `tests_hil/live_backend.py`'s `LiveBackend.update()` builds its own `argparse.Namespace`
  by hand instead of going through `host/labflash/__main__.py`'s real argument parser, so it silently
  fell out of sync when Zephyr UDP/BLE support added new CLI flags (`--udp-port`, `--confirm-timeout`)
  with defaults. Any code path that hand-constructs a `Namespace` to stand in for real CLI args needs
  to be kept in lockstep with the CLI's own defaults, or built from the parser itself.

### Trap 17: Zephyr's real per-variant build convention is `build_<variant>`, not IDF's `build`
- **Symptom:** `LiveBackend.image_for("v1")` for the zephyr board resolved to a stale, tiny (137 KB)
  pre-BLE/WiFi build from initial bring-up instead of the current ~736 KB image, because the shared
  `VARIANT_DIRS = {"v1": "build", ...}` mapping was written for IDF's convention (`esp_idf/build/`) and
  silently carried over to Zephyr, where every OTHER variant already used `build_v2`/`build_hang`/etc.
  Lesson: a variant-to-directory convention that's correct for one board target should not be assumed
  correct for another just because the dict is shared.
- **Resolution:** Prefer `build_v1` first for zephyr (matching the uniform `build_<variant>` pattern),
  falling back to the legacy path.

### Trap 18: A native-Windows Python venv can end up empty/broken silently
- **Symptom:** `.venv_win_ble\Scripts\python.exe` produced "The system cannot find the path specified"
  -- a raw OS error, not a Python one. `dir .venv_win_ble` showed only a stray `Lib\` folder: no
  `Scripts\`, no `pyvenv.cfg`, no interpreter.
- **Resolution:** The venv was simply broken/incomplete (cause not determined -- possibly an
  interrupted `venv` creation from an earlier session). No repair path for a partial venv; delete and
  recreate (`python -m venv .venv_win_ble` + `pip install -e host pytest bleak smpclient`). Also worth
  checking for a second, WRONG-platform venv under a similar name (`.venv` in this repo turned out to
  be a WSL/Linux venv, identifiable by its `lib64/` layout -- Windows venvs use `Lib\site-packages`).

### Trap 19: Two agents sharing one working directory can silently fold each other's uncommitted work into a commit
- **Symptom:** A commit (`d308248`) appeared with a Zephyr-focused message ("complete Zephyr phase
  acceptance run") but its diff also included unrelated IDF-track `tickets.json`/evidence-file changes
  that had been made moments earlier in the same session and not yet committed.
- **Resolution:** When two agent sessions (or a human and an agent) operate on the exact same working
  directory rather than separate clones, a broad `git commit`/`git add -A` by either one can sweep up
  the other's staged-but-uncommitted work. If it's already pushed, don't rewrite shared history to
  "fix" the attribution -- the content is still correct, just filed under the wrong commit title; note
  it and move on. If caught before pushing, `git reset --soft HEAD~1` and re-commit as separate,
  correctly-scoped commits. Always `git status`/`git log -3` before assuming a clean starting point when
  two sessions might share a directory.

## 5. Zephyr Track Status Summary (as of 2026-09-23)

| Item | Status |
|------|--------|
| BL-050 (HIL dummy test, both boards) | Done |
| BL-051 (T01-T03 boot/update) | idf done; zephyr blocked on Trap 14 |
| BL-056 (RPi4 self-hosted runner) | idf done (runner registered, verified); zephyr n/a until a board is attached to the RPi4 |
| BL-064 (LABID dies after v2 build) | Two bugs: mem_slab exhaustion fixed; MCUboot-swap-vs-LABID fixed |
| BL-065 (MCUboot never swaps) | Fixed and verified live |

Full per-ticket evidence for the Zephyr track's HIL work: `scripts/evidence/bl050_zephyr_dummy_hil_2026-09-22/`,
`scripts/evidence/bl064_zephyr_labid_rx_irq_dead.md`, `scripts/evidence/bl056_rpi4_runner.md`.

---

## 6. Required Actions for the Zephyr Track (P2 Bring-Up Checklist)

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

## 7. Owner Review & Sign-Off

- **Reviewer:** Mohamed Soubhi (Project Owner)  
- **Decision:** ESP-IDF Track technical achievements, test evidence, and lessons learned accepted in full.  
- **Gate Status:** BL-063a accepted. Proceed to final HTML presentation (BL-063b) to officially lift the Zephyr development gate.
