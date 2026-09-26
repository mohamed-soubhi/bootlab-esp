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

### Trap 20: An under-voltage RPi4 stalls a WiFi OTA mid-transfer (BL-060 Pi smoke run, 2026-09-24)
- **Symptom:** WiFi OTA served from the RPi4 stopped after 196,608 of 1,249,280 bytes
  (`host served: {'update.bin': 196608}`), slot stayed `0 -> 0`, `UPDATE FAILED`. The board's captured console
  simply ended at `esp_https_ota: Writing to <ota_1> ...` with no error line.
- **Evidence:** `vcgencmd get_throttled` was `0x50000` at idle (sticky history bits only) but `0x50005`
  on nearly every sample from 01:51:25 to 01:52:06 while a transfer ran (`0x1` under-voltage now,
  `0x4` throttled now). Same class of fault as `docs/rpi4_limitations.md` section 2.1.
- **Resolution / how to check:** Use the official 5.1 V / 3 A supply and a short cable, and put the ESP
  on a powered USB hub. Test with a loop that prints only when the LIVE bits are set:
  `while true; do v=$(vcgencmd get_throttled | cut -d= -f2); (( (v & 0x5) != 0 )) && echo "$(date +%T) $v"; sleep 0.5; done`.
  `0x10000`/`0x40000` are sticky until reboot, so ignore them. Do not trust Pi soak results until the loop
  stays silent through a full transfer. The Pi's `wlan0` link (6.5 MBit/s rx at -62 dBm) is a secondary suspect;
  wire it to Ethernet. Status: power cause is strongly indicated, not yet confirmed by a clean re-run.

### Trap 21: Python >= 3.13 rejects the lab Root CA, and `trigger()` reports it as "board never answered" (FIXED `13a1d2c`)
- **Symptom:** every `POST /ota` from the RPi4 (Python 3.13) failed with
  `ERROR: the board never answered POST /ota (timed out after retrying)`; `curl -k` to the same board worked.
- **Root cause:** Python 3.13's `ssl.create_default_context()` turns on `VERIFY_X509_STRICT`, which rejects
  a CA certificate without a `keyUsage` extension. The lab CA has only `Basic Constraints: CA:TRUE`.
  `WifiBoard.trigger()` swallows every `URLError` and returns `-1`, so the real
  `CERTIFICATE_VERIFY_FAILED ... CA cert does not include key usage extension` was invisible.
- **Misdiagnosis to avoid:** the board cert's SAN lists only `192.168.1.152`, and `curl --cacert` on
  `192.168.1.153` failed on that. It was NOT the cause: the client sets `check_hostname = False`. An
  `/etc/hosts` alias did nothing. Replay the exact request in a small script and print the exception.
- **Resolution:** `WifiBoard` clears `VERIFY_X509_STRICT` (chain verification against the pinned CA stays on;
  test `test_tls_context_does_not_require_ca_key_usage_extension`). Longer term: reissue the CA with
  `keyUsage = keyCertSign, cRLSign`.

### Trap 22: A host firewall silently blocks the board's OTA pull, so nothing is served (`host served: {}`)
- **Symptom:** the board accepted `POST /ota` (HTTP 202) and logged `OTA requested ... task created`, then
  `read error :-0x0050` and nothing more; the host logged `host served: {}`, slot `0 -> 0`.
- **Root cause:** the RPi4 runs ufw with `INPUT DROP`. The board's TCP SYNs to the host's OTA server on
  port 8443 were dropped (`journalctl -k | grep "UFW BLOCK" | grep SRC=<board ip>` showed `DPT=8443 ... SYN`).
  The `-0x0050` line also appears on a healthy run (the first probe connection), so it is not the signal.
- **Resolution:** `sudo ufw allow from <board ip> to any port 8443 proto tcp`. Keep it source-restricted.
  The Pi's rules live in `table ip filter` (iptables-nft); an `nft ... inet filter` rule fails with
  "No such file or directory" and never applied.

### Trap 23: A second board on a new host is not ready after `flash`: provisioning, deps and image layout (BL-060 Pi setup)
- **Symptom / fixes, in the order hit:**
  - `git clone` gives no secrets or builds: copy `credentials.env`, `keys/{ca,server_cert,server_key}.pem`,
    `esp_idf/build*/bootlab_idf_blink.bin` yourself. Never copy the RSA signing key (`idf_sbv2.pem`) to the Pi.
  - `pip install -e .` fails at the repo root: the project is `host/` (`pip install -e host`). `bleak` and
    `esp-idf-nvs-partition-gen` are NOT in `host/pyproject.toml`; install by hand (provisioning fails with
    `No module named 'esp_idf_nvs_partition_gen'`).
  - esptool cannot take `@flasher_args.json` (that JSON is not an argfile): pass explicit offsets
    (`0x0 bootloader.bin 0x8000 partition-table.bin 0xf000 ota_data_initial.bin 0x20000 app.bin`).
  - After flashing, the log says `WiFi unprovisioned: NVS namespace 'lab' not found`: WiFi credentials
    live in NVS, not in the firmware. Run `labflash provision idf --port <port> --env-file credentials.env`.
  - Default `host/config/rig.yaml` pins `idf` to board 1's MAC; a second board needs its own rig file
    (`--rig-config rig-pi.yaml`). `labflash flash idf` without `--port` would resolve board 1.
  - Right after a reset the USB-Serial-JTAG port re-enumerates, so `miniterm` dies with "device reports readiness
    to read but returned no data"; the boot log is printed once, so pulse RTS from a script to capture it.

### Trap 24: BLE OTA is ~7× slower than HTTPS and degrades over a long soak (BL-060 100-cycle run, 2026-09-24)
- **Observation, not a failure:** the 100-cycle IDF soak passed 100/100, but BLE cycles drift.
  WiFi: 50 cycles, 29.7-32.9 s each (~38 KB/s for the 1 249 280 B image), flat across 3 h 48 m.
  BLE: 50 cycles, 165.9-391.4 s each (3.1-7.4 KB/s, median 5.8), median 193.6 s in the first half of the run
  vs 280.5 s in the second half (+45 %); 5 cycles over 300 s (72, 75, 80, 83, 95), worst 391.4 s.
- **Why it matters for planning, not correctness:** BLE is the long pole. A soak with a high BLE share takes
  hours even though every cycle passes; BL-067's randomized 200-cycle soak should budget for the drift rather
  than the first-cycle rate.
- **Not yet root-caused.** Candidates, none ruled out: the notify-driven upload design (~1 progress notification
  per 1.8 s, connection interval flipping between 48 and 12 units), 2.4 GHz coexistence with the interleaved
  WiFi cycles, thermal drift, or the host-side BLE stack (`bleak` on Windows) rather than the board.
- **How to settle it:** run a BLE-only soak (no WiFi cycles interleaved) and compare the same drift curve; if it
  still drifts, watch `esp_ble` connection-interval / MTU negotiation in `console.log` and the host-side
  notification timing. Evidence for this run: `scripts/evidence/bl060_soak_2026-09-23d/`.

### Trap 25: Signed images are always a multiple of 4096 bytes (BL-069, 2026-09-25)
- **Symptom/Observation:** a signed IDF app image is always sector aligned. `espsecure` pads the data to a 4096
  multiple and appends a whole 4096-byte signature sector, so v1 is 1,249,280 B = 305 sectors. The bootloader reads
  only up to `ALIGN_UP(end,4096)` plus the signature block.
- **Cause:** the signing step rounds the data up and always reserves a full sector for the signature, so no normal
  build can emit an image whose size is not a 4096 multiple.
- **Resolution / How to avoid:** BLE OTA refuses non-aligned images host-side (`host/labflash/update.py`), and
  "non-aligned" test images cannot come from a normal build — they have to be synthesized deliberately.

### Trap 26: A post-signature trailer is invisible to the bootloader but `espsecure` refuses it (BL-069, 2026-09-25)
- **Symptom/Observation:** bytes appended after the signature sector are never read by the bootloader, so a trailer
  yields a valid image whose file size is not a 4096 multiple. `espsecure verify-signature` refuses such a file.
- **Cause:** the bootloader stops at `ALIGN_UP(end,4096)` plus the signature block, while `espsecure` validates the
  whole file, so trailing bytes break verification of an otherwise good image.
- **Resolution / How to avoid:** `labflash.imagefmt.verify_device_signature` strips the trailer before verifying.
  **NOT YET CONFIRMED ON HARDWARE** — Gate R1 (append 4096 B to v1, install over WiFi, expect boot + `confirmed=1`)
  is still pending, so treat this as design intent rather than verified behavior.

### Trap 27: An over-limit image fails in three places and the BLE symptom is silent (BL-069, 2026-09-25)
- **Symptom/Observation:** an over-limit image is rejected by BLE `ota_begin` (`fw_len` > partition size), by WiFi
  `esp_ota_begin`, and by the bootloader (FAIL_LOAD). Over BLE the transport still ACKs sectors, so there is no error
  message: the symptom is no reboot and a host-side timeout.
- **Cause:** the failure happens above the transport, so an ACKed sector carries no information about the rejection.
- **Resolution / How to avoid:** use a short timeout for images expected to be rejected, so the missing reboot shows
  up quickly instead of after the normal transfer budget.

### Trap 28: IDF's own size check refuses an over-partition build, and its error is on stdout (BL-069, 2026-09-25)
- **Symptom/Observation:** `check_sizes.py` fails the build when the signed image exceeds the 4 MB app partition, with
  the message "All app partitions are too small for binary ... size 0x...". That line goes to the build's STDOUT log
  while stderr only holds Kconfig notes.
- **Cause:** an error message assembled from stderr alone therefore hides the real cause of the build failure.
- **Resolution / How to avoid:** the too_big pool image is built against a temporary 5 MB partition table
  (`genvariants.BIG_PARTITIONS`), and `build_idf_image` now includes the last 40 stdout lines in `BuildError`.

### Trap 29: Image size grows in 64 KiB steps, so an exact byte target is not reachable (BL-069, 2026-09-25)
- **Symptom/Observation:** flash-mapped segments are 64 KiB aligned; a 4096-byte pad increase produced the same
  signed size (observed: pad 2,879,488 and 2,883,584 both gave 4,132,864 B).
- **Cause:** alignment rounds the pad away, so most requested byte sizes collapse onto the same image size.
- **Resolution / How to avoid:** the near_limit image targets a window just under 4 MiB (built: 4,132,864 B) and
  too_big a window just over (built: 4,263,936 B), via `genvariants.solve_pad` with `SIZE_WINDOW` = 64 KiB.

### Trap 30: Same seed, same image: compare `content_sha256`, not `sha256` (BL-069, 2026-09-25)
- **Symptom/Observation:** RSA-PSS signatures are salted, so two builds of the same seed differ in the signature
  sector only. Rebuilding pool image g00 into a different output directory gave byte-identical content for the first
  2,031,616 bytes and 388 differing bytes inside the signature sector.
- **Cause:** salted signing is non-deterministic by design, so whole-file `sha256` can never be reproducible.
- **Resolution / How to avoid:** the manifest carries `sha256` (whole file) and `content_sha256` (everything before
  the signature sector), and reproducibility is judged on `content_sha256`. Related trap found in the same work:
  `idf.py` runs from `esp_idf/`, so a relative `--out` path resolved against the wrong directory until
  `genvariants.run` made it absolute.

### Trap 31: A second open of a COM port that the run already holds is refused on Windows (BL-067, 2026-09-25)
- **Symptom:** every `no_confirm` cycle failed with `SerialException: could not open port 'COM14': PermissionError(13, 'Access is denied.')`
  (cycles 42 and 53 of the first BL-067 run); a smoke test without a `no_confirm` cycle passed, so it stayed hidden until then.
- **Cause:** `LiveBackend.reset()` opened the port itself, while the run's `SharedConsolePort` (continuous `console.log` capture) already held it.
- **Resolution:** `SharedConsolePort.hard_reset()` toggles DTR/RTS on the handle it already holds and `LiveBackend.reset()` uses it when a
  console port exists. Any new helper that talks to the board during a captured run must go through the shared handle.

### Trap 32: A board that is pending verify refuses OTA, so recovery must be a reset (BL-067, 2026-09-25)
- **Symptom:** after a `no_confirm` image booted, three restore-to-v1 OTAs failed, each stopping after 81,920 bytes served.
- **Cause:** ESP-IDF will not start an OTA while the running image is still pending verify; only a reset (the bootloader then rolls the image back) helps.
- **Resolution:** `_resync` and `LiveBackend.reset_to_v1` hard-reset a board that reports confirmed=0 and wait for the rollback before any OTA.

### Trap 33: `labflash update` reports FAIL when the version it sends is already running (BL-069 AC5 / BL-067, 2026-09-25)
- **Observation:** it recognises a finished install by the version changing, so re-sending the running version printed `[FAIL] slot flipped` even though
  the board installed the image correctly (two false FAILs in the BL-069 AC5 run).
- **Cause found in our own schedules:** BL-069's reversed second sweep starts with the image the first sweep ended on.
- **Resolution:** `pool_schedule` swaps neighbouring pairs instead of reversing; `soak_model.plan` never picks the running version.

### Trap 34: A LABID read that opens the serial port fresh can reset the board in the middle of an OTA (BL-069 follow-up, 2026-09-26; was "board accepts the trigger and never pulls")
- **Symptom:** `host served: {}` with the trigger accepted (HTTP 202) and the board unchanged, seen four times in two days (the first gate R1 attempt, a failed restore, two
  measurement runs), always fine on the next try; once the update process then hung for 7 hours.
- **Cause (proven):** `SerialLineTransport` opened the COM port with pyserial's defaults, which assert DTR/RTS on open, and on the USB-Serial-JTAG port that can reset the chip
  (PLAN R14). `labflash update` reads the board over serial WHILE the image downloads, so a reset mid-download killed the pull. The runners with the shared console port open
  (SharedConsolePort sets both lines inactive before opening) never showed it, which is why the failures clustered on the one-shot paths.
- **Fix and proof:** `SerialLineTransport` sets DTR/RTS inactive before the open (test first). The script that had failed every install then completed 4/4 with 0 retries.
- **Also fixed (Trap 35):** a reset leaves a half-open connection on the host; the OTA server used to wait on it forever.
- **Rule:** any code that opens the board's serial port must set dtr and rts to False before open().

### Trap 35: The local OTA server hung forever on a connection whose TLS handshake never finished (BL-069 AC5 and follow-up, 2026-09-25/26)
- **Symptom:** an update process hung for 7 hours (the board held an ESTABLISHED connection, the log stayed silent); earlier, after 12 good installs, three steps in a row failed within
  seconds with `PermissionError: [WinError 32] ... update.bin` (a stuck handler kept the file open) and aborted the first AC5 run.
- **Cause:** the server handshook TLS inside `accept()` on its single serving thread with no timeout, and `stop()` joined every handler thread, so one dead connection blocked all
  others and shutdown. The dead connection came from Trap 34 (a rebooted board leaves no FIN).
- **Fix:** handshake in the per-connection thread (`do_handshake_on_connect=False`) under a 60 s handler timeout, daemon handler threads, and no join on shutdown; a test with a
  client that connects and never speaks TLS reproduced the hang and now passes.
- **Mitigation kept:** `tests_hil/otaretry` still retries host-side trouble while the board is unchanged, and writes the traceback into `update.log`.

### Trap 36: The LED blink rate is quantized by the FreeRTOS tick (BL-069 follow-up, 2026-09-26)
- **Observation:** a pool image configured for a 269 ms half-period measured 1.917 Hz, not the nominal 1.859 Hz reported over LABID.
- **Cause:** `vTaskDelay(pdMS_TO_TICKS(ms))` at `CONFIG_FREERTOS_HZ=100` rounds down to 10 ms ticks, so 269 ms runs as 260 ms (1.923 Hz); measured rates follow that within ~1 %.
- **Consequence:** the `blink_hz` a generated image reports is up to ~3 % off for short periods; `labflash measure` with a tight tolerance can flag it. Not changed, documented.

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
