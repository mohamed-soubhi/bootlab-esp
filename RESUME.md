# RESUME — bootlab-esp (checkpoint 2026-09-21)

Work and commit ONLY in `/home/msoubhi/bootlab-esp`. The owner's Windows copy
(`C:\MSA\embedded-OS\bootlab-esp`) is a scratch dir; never edit or push from it.

## Ticket state (from tickets.json)
- DONE: BL-001, 002, 003, 004, 006, 007, 010, 011, 012, 013, 040
- BLOCKED:
  - BL-020: all 4 ACs PASS with evidence (2026-09-21); blocked only on unfinished deps BL-005, BL-014.
  - BL-021: all 3 ACs PASS with evidence (2026-09-21); blocked only on dep BL-020.
  - BL-022: all 3 ACs PASS with live on-target evidence (2026-09-21); blocked only on dep BL-020.
  - BL-023: all 2 ACs PASS with live on-target evidence (2026-09-21); blocked only on dep BL-021.
  - BL-024: all 2 ACs PASS with live on-target evidence (2026-09-21); blocked only on dep BL-020.
  - BL-025: all 2 ACs PASS with live on-target evidence (2026-09-21); blocked only on dep BL-024.
  - BL-005: idf led_gpio=48 confirmed; zephyr led_gpio unknown (Zephyr hold); `psram_mode` unverified
    on both boards (the current IDF build does not enable PSRAM, so it cannot be detected yet).
  - BL-014: AC needs Zephyr native_sim + IDF linux builds; Zephyr on hold.
  - BL-041: host code done + mock-verified; live LABID firmware now running on IDF board.
  - BL-026: both ACs PASS with live on-target console evidence (2026-09-21); blocked only on deps BL-023/BL-025.
- TODO, IDF chain: BL-027 (IDF BLE OTA).
- Zephyr chain (BL-030 ...) stays on hold.

## BL-027 status (IN PROGRESS — firmware + host client built and unit-tested; NOT flashed, NO on-target result yet)
Done and pushed (HEAD ~ab048a2):
- `espressif/ble_ota` 0.1.18 pinned (ESCALATE gate cleared, see versions.env). Firmware: `esp_idf/main/app_ble_ota.[ch]`
  (flash write via esp_ota_*, `esp_ota_end` enforces the RSA signature, activation only after verification, GAP-disconnect
  listener discards a half-received image, app-owned `notify_sem` mutex the component links against),
  `sdkconfig.defaults` (NimBLE peripheral, 1 conn, SW coex, host stack 8192), wired in `app_main.c` after WiFi init.
  v1/v2 build clean (0 warnings; +131 KB; 72% of the slot free) and verify signed.
- Host client `host/labflash/idf_ble_ota.py` (protocol read from the component source; 15 pytest tests, no hardware).
  Runs NATIVELY on Windows: `C:\MSA\embedded-OS\bootlab-esp\.venv_win_ble\Scripts\python.exe` (bleak 3.0.2, pyserial 3.5).
  bleak verified to scan on the laptop's adapter (19 devices).
NEXT (each flash needs owner go-ahead; verify ID_SERIAL_SHORT E0:72:A1:AA:23:90 first):
1. Flash BLE-enabled v1 (`esp_idf/build`, per-dir sdkconfig; verify `CONFIG_BT_NIMBLE_ENABLED` AFTER building) to ota_0.
2. From Windows: `... idf_ble_ota.py --scan-only --board-mac E0:72:A1:AA:23:90` (BLE addr = base MAC + 2, so first 5 octets match).
3. AC1: v1 -> v2 -> v1 over BLE; evidence = board console (`serial_watch.py`) + `/version`.
4. AC2: WiFi stays connected during BLE OTA -- poll `/version` SPARINGLY (polling starves the board's TLS, see BL-026) and
   check the console for WiFi disconnect events.
5. AC3: `--abort-after N` -> console must show 'partial image discarded'; `/version` unchanged; then a clean OTA still works.
UNTESTED ON TARGET (fix if they fail): heap with WiFi+TLS+NimBLE; NimBLE host task stack for esp_ota_end; advertised
service UUID / name (client falls back to name `nimble-ble-ota`); MTU negotiation on Windows; first-sector ACK latency.
TRAPS: an existing `build*/sdkconfig` OVERRIDES sdkconfig.defaults (the BLE options were silently ignored until I
regenerated it) -- always verify options in `<dir>/sdkconfig` after building; the component needs an app-defined global
`notify_sem` or the link fails.

## BL-026 status (COMPLETE — both ACs pass with live on-target console evidence)
Evidence: `scripts/evidence/bl026_ota_acceptance.md`. Board left on **v1** (1.0.0, slot 0, confirmed).
- Firmware: `esp_https_ota` pull task in `esp_idf/main/app_http_server.c` (POST /ota -> 202, 409 if busy,
  pinned Lab Root CA); `PROJECT_VER` per variant; `sdkconfig.{v2,hang,no_confirm}` fragments.
- AC1 v1->v2 over WiFi: PASS (slot 0->1, app 2.0.0, confirmed, 4.20 Hz via `scripts/rate_check.py`).
- AC2 bad_sig refused: PASS. `bad_sig_key.bin` (foreign RSA key) = real signature rejection on the board;
  `bad_sig_tamper.bin` = rejected by image CHECKSUM only (integrity, not a signature test).
- LESSONS (do not repeat): (1) the first run failed because `tcp_forwarder.py` RST-truncated the download
  (fixed: half-close); (2) "bytes served" by the server does NOT prove the board received them, and polling
  `/version` during an OTA starves the board's TLS — refusal evidence must come from the board's console
  (`ota_check.py --console-log`); (3) the original `bad_sig.bin` (zeros in the empty signature blocks) was
  still validly signed; always confirm artifacts fail `espsecure verify-signature`.
- NOT covered: no_confirm/hang revert (rebuild `hang.bin` — the scratchpad one is a stale pre-WiFi build);
  tampered image with valid checksum + invalid signature.
- HOW TO RUN (WSL, everything Windows-side via `powershell.exe ... < /dev/null`):
  1. detach board: `powershell.exe -Command "usbipd detach --busid 7-4" < /dev/null`
  2. forwarder: `powershell.exe -Command "(Start-Process python -ArgumentList 'C:\MSA\embedded-OS\bootlab-esp\scripts\tcp_forwarder.py 8443 8443' -PassThru).Id" < /dev/null` (copy the script to that path first)
  3. console capture in background: `powershell.exe -Command "python C:\...\scripts\serial_watch.py COM14" < /dev/null > LOG &`
  4. `python3 scripts/ota_check.py --ip 192.168.1.152 --host-ip 192.168.1.134 --stage <images> --console-log LOG`
  5. stop leftovers: Get-CimInstance Win32_Process filtered on serial_watch|tcp_forwarder, Stop-Process.
  Images are built with per-dir sdkconfig and staged in a scratchpad dir (v1.bin v2.bin bad_sig_*.bin);
  keys stay in gitignored `keys/`, token in gitignored `credentials.env`.

## BL-025 status (COMPLETE — all 2 ACs pass with live on-target evidence)
- Generated Lab Root CA (`keys/ca.pem`) and ESP32 server certificate/key (`keys/server_cert.pem`,
  `keys/server_key.pem`) with SANs via `scripts/gen_tls_certs.sh`. All keys/certs remain gitignored.
- Enabled `CONFIG_ESP_HTTPS_SERVER_ENABLE=y` in `esp_idf/sdkconfig.defaults`.
- Embedded certificates into the binary via CMake `EMBED_TXTFILES` in `esp_idf/main/CMakeLists.txt`.
- Implemented `esp_idf/main/app_http_server.[ch]`: starts HTTPS server on port 443 on WiFi connect.
  - `GET /version`: returns JSON `{app, git, slot, confirmed}` matching `esp_app_desc` and LABID.
  - `POST /ota`: checks `Authorization: Bearer <token>` against NVS token; returns 202 Accepted
    on match, 401 Unauthorized on missing/wrong token.
- Built and signed `v1` firmware (size 987136 bytes, ELF SHA256 `a1532237f579fdeb72ba4e8510d943040478c554cd11743d1c1c7add02769680`).
- Flashed signed v1 app to `lab-esp-idf` (`E0:72:A1:AA:23:90`) after owner go-ahead.
- Live acceptance test runner `scripts/https_check.py` run on hardware (cross-checking with `COM14`):
  - AC1 (GET /version matches LABID VER.app): PASS (`app='688b8a6-dirty'`, `git='688b8a6'`, `slot=0`, `confirmed=True`).
  - AC2 (Wrong token -> 401): PASS (missing token -> 401, wrong token -> 401, valid token -> 202).
- Status set to 'blocked' solely because dep BL-024 is blocked on BL-020; all requirements satisfied.

## BL-024 status (COMPLETE — all 2 ACs pass with live on-target evidence)
- Host provisioning tool `host/labflash/provision.py` implemented: `labflash provision idf` writes
  SSID/PSK/token to NVS partition at offset 0x9000 using `nvs_partition_gen` and `esptool`.
  Unit tests in `host/tests/test_provision.py` (4/4 PASS). Added `labflash provision` CLI subcommand.
- ESP-IDF WiFi client implemented in `esp_idf/main/app_wifi.[ch]`: reads NVS namespace `lab` keys
  `ssid`, `psk`, `token`, configures WiFi STA mode, connects to AP, logs IP on `IP_EVENT_STA_GOT_IP`.
  Sensitive stack buffers (`psk`, `wifi_config_t`) wiped with `memset` immediately after use.
- Built and signed `v1` firmware with WiFi support (size 856064 bytes, ELF SHA256 `6f7be3cba67c6e87faf24d5a1a4b7e23f245b207383f45dd999f6d0ae2ed0806`).
- Flashed signed v1 app and provisioned NVS partition at offset 0x9000 to `lab-esp-idf` (`E0:72:A1:AA:23:90`)
  after owner go-ahead.
- Live acceptance test runner `scripts/wifi_check.py` run natively on Windows (`COM14`):
  - AC1 (Board joins WiFi after reboot): PASS, connected to AP `DIGIFIBRA-ubEU`, DHCP assigned IP `192.168.1.152`.
  - AC2 (No credentials in source or logs): PASS, zero PSK or token in console logs or tracked git files.
- Status set to 'blocked' solely because dep BL-020 is blocked on BL-005/BL-014; all requirements satisfied.

## BL-023 status (COMPLETE — all 2 ACs pass with live on-target evidence)
- Self-test health check task implemented in `esp_idf/main/app_main.c`: waits for >= 5 s uptime and >= 5
  LED toggles, then calls `esp_ota_mark_app_valid_cancel_rollback()` and sets `s_confirmed = true`.
- Gated confirmed reporting in `esp_idf/components/labid_port/labid_port.c` on app self-test state and
  OTA partition state. In `no_confirm` builds (`CONFIG_APP_VARIANT_NO_CONFIRM=y`), the health task is
  omitted, so `s_confirmed` remains false indefinitely.
- Both variants compiled cleanly and signed with RSA-3072 using per-dir sdkconfig (PLAN R15):
  - `v1`: `esp_idf/build/`, ELF SHA `4089eadf96bc09b627c80d7bfa91c111f2ca1e427dfb3c0cd8976cbfaf7b6c48`.
  - `no_confirm`: `esp_idf/build_no_confirm/`, ELF SHA `5ac89aa2f56966ac945e23d468d28e0205998ada5bb65422f1d2352b20cb3e45`.
- Live acceptance test runner `scripts/confirm_check.py` run natively on Windows (`COM14`) after flashing
  each variant to `/dev/lab-esp-idf` (`E0:72:A1:AA:23:90`) with owner go-ahead. ALL PASS:
  - AC1 (VER? confirmed=1 after 5 s): PASS (v1: confirmed=0 at 1037 ms -> confirmed=1 at 5566 ms, toggles=12).
  - AC2 (no_confirm stays confirmed=0): PASS (no_confirm: confirmed=0 at 1002 ms -> confirmed=0 at 5529 ms, toggles=12).
- Status set to 'blocked' solely because dep BL-021 is blocked on BL-020; all requirements satisfied.

## BL-021 status (COMPLETE — all 3 ACs pass with evidence)
- partitions.csv configured per PLAN Sec 4.2: 16 MB flash layout with dual 4MB slots (ota_0, ota_1),
  otadata (0xF000), nvs (0x9000), phy_init (0x11000), storage (spiffs, 0x820000).
- sdkconfig.defaults configured with CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y,
  CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT=y, CONFIG_SECURE_SIGNED_APPS_RSA_SCHEME=y,
  CONFIG_SECURE_BOOT_SIGNING_KEY="../keys/idf_sbv2.pem".
- Removed temporary blink_diag logging from app_main.c.
- AC1 (Signed build succeeds): PASS, build produced signed bootlab_idf_blink.bin; verified with
  `espsecure verify-signature` (RSA signature block 0 valid and verified).
- AC2 (Forbidden-config grep passes): PASS, CONFIG_SECURE_BOOT=n, CONFIG_SECURE_FLASH_ENC_ENABLED=n,
  CONFIG_BOOTLOADER_APP_ANTI_ROLLBACK=n.
- AC3 (efuse-summary unchanged after flash): PASS, flashed bootloader, partition table, ota_data_initial,
  and signed app to lab-esp-idf (E0:72:A1:AA:23:90); pre-flash efuse summary (scripts/evidence/efuse_pre_bl021.txt)
  and post-flash efuse summary (scripts/evidence/efuse_post_bl021.txt) are bit-for-bit identical with SHA256
  83e95198dedc0db5507df44ad6e75f181fea26a9d1ecd6cf71f401b85bde2a34.
- Status set to 'blocked' solely because dep BL-020 is blocked; all requirements satisfied.

## BL-022 status (COMPLETE — steps A, B, C, D done & verified on target)
- A: `common/labid/{include/labid_dispatch.h,src/labid_dispatch.c}` + device-mode parser
  (`labid_parser_init_device`: CRC-less requests, trailing CR, drop-until-newline, error reasons).
  20 new Unity tests (`common/labid/tests/test_dispatch.c`) + 26 legacy pass; ASan/UBSan clean;
  line coverage 99.0% dispatch / 95.5% parser. Branch-taken coverage gap of labid_dispatch.c
  (71.6%) explicitly waived due to defensive guards; core paths live-verified.
- B: `esp_idf/components/labid_port/` (driver RX task prio 2, providers, ANNOUNCE ~1 s after start,
  one-fputs atomic frames, LF TX endings), wired in `esp_idf/main/app_main.c`;
  `esp_idf/CMakeLists.txt` adds `EXTRA_COMPONENT_DIRS ../common/labid`.
- C: v1 builds clean with a per-dir sdkconfig; variant verified after build (V1, GPIO48).
- D: Flashed to lab-esp-idf (`E0:72:A1:AA:23:90`) after owner go-ahead. Acceptance checker run
  natively on Windows (`scripts/labid_check.py COM14`). ALL PASS:
  - AC1 (ANNOUNCE <= 2 s): PASS, announced at ~995 ms uptime (board=idf, uid=E072A1AA2390).
  - AC2 (ID?, VER?, STATE? <= 100 ms): PASS, 20 runs each; medians 2.7-3.3 ms, max <= 4.6 ms.
  - AC3 (garbage -> ERR, no reset): PASS, all 4 garbage patterns produce corresponding ERR frame;
    board does not reset (uptime preserved, reset=por, rx_err=4).
- Ticket status set to 'blocked' solely because dep BL-020 is blocked; all requirements satisfied.

NEXT:
- BL-026 (IDF WiFi OTA pull via esp_https_ota)
- BL-041 (host identify/measure verification against live LABID)

## Hardware state (2026-09-21)
- idf board: `/dev/lab-esp-idf`, USB serial `E0:72:A1:AA:23:90`, usbipd busid 7-4, Windows COM14.
  Flashed with BL-025 v1 signed build (HTTPS control server on port 443, WiFi STA connected to IP 192.168.1.152,
  NVS credentials provisioned at 0x9000, dual OTA partitions, rollback enabled, 1 Hz blink on GPIO48, confirms after 5s).
  After BL-026 the board runs v1 1.0.0 in slot 0 (WHITE blink: the old firmware). The LED COLOR scheme (PLAN 5.3.1:
  amber pending / green v1 / blue v2 / red hang / magenta bad_sig) is built for v1+v2 in `esp_idf/build`, `build_v2`
  but NOT flashed yet; flashing needs owner go-ahead and a visual check (a v1->v2 OTA should read green, amber, blue).
- zephyr board: `/dev/lab-esp-zephyr`, USB serial `AC:A7:04:2C:3B:04`, busid 6-3. Untouched.

## Settled findings (see PLAN Sec 9)
- R14: opening the port over usbipd/WSL2 resets the board (`rst:0x15`). Native Windows serial with
  DTR/RTS inactive does NOT. Flash from WSL; observe serial on Windows (`scripts/serial_watch.py COM14`).
  Not a blocker on the RPi4 rig.
- R15: per-variant `-B` build dirs share one `esp_idf/sdkconfig`. Always build with
  `-DSDKCONFIG=<dir>/sdkconfig`, verify the variant AFTER building, then confirm on target via the
  boot log (`App version`, `Compile time`, `ELF SHA256`).
- Hang variant: task WDT panic at ~5.0 s (`rst:0xc`, PC in `task_wdt_timeout_handling`).
- v2 / no_confirm / bad_sig builds predate R15: rebuild with per-dir sdkconfig before flashing them.
- PowerShell / usbipd interop from WSL2: `powershell.exe` blocks indefinitely in WSL2 unless stdin is
  redirected with `< /dev/null`. Can switch the IDF board (`busid 7-4`) directly from WSL bash:
  - Attach to WSL2: `powershell.exe -Command "usbipd attach --wsl --busid 7-4" < /dev/null`
  - Detach to Windows: `powershell.exe -Command "usbipd detach --busid 7-4" < /dev/null`

## HARD RULES STILL IN FORCE
- Zephyr hold: do NOT touch ~/zephyr-ws, no Zephyr build.
- NO flash/write/erase without explicit per-instance owner go-ahead. Verify board identity
  (`ID_SERIAL_SHORT`) before every flash.
- Every "done" needs fresh pasted evidence, not summaries.
- Verify surprising results directly before reporting.
- Never burn eFuses; never commit keys/, backups/, *.pem.

## Known environment traps
- PowerShell from WSL2: always redirect stdin (`< /dev/null`) when invoking `powershell.exe` from bash
  subshells to prevent hangs waiting on standard input.
- esptool: venv 5.4.0 = ~/bootlab-esp/.venv/bin/esptool (HAS elf2image);
  Debian /usr/bin/esptool 4.7.0 shadows it if .venv/bin not first on PATH.
  Export: `export PATH="$HOME/bootlab-esp/.venv/bin:$PATH"`.
- ESP-IDF v6.0.3 lives at `~/tools/esp-idf` (`. ~/tools/esp-idf/export.sh`).
- west topdir = ~/zephyr-ws (NOT the git repo); on hold.
- `ls` in this shell is aliased to eza and breaks on some args; use `command ls`.
- Untracked build artifacts (`bootloader/`, `tools/`, `common/labid/tests/build_audit/`) are not committed.
- Many tracked files show as modified from file-mode changes only (NTFS/WSL); content is unchanged.
