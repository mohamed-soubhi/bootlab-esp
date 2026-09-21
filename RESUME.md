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
  - BL-005: idf led_gpio=48 confirmed; zephyr led_gpio unknown (Zephyr hold); `psram_mode` unverified
    on both boards (the current IDF build does not enable PSRAM, so it cannot be detected yet).
  - BL-014: AC needs Zephyr native_sim + IDF linux builds; Zephyr on hold.
  - BL-041: host code done + mock-verified; live LABID firmware now running on IDF board.
- TODO, IDF chain: BL-025 (IDF HTTPS control server (/ota, /version)) -> BL-026 (IDF WiFi OTA pull).
- Zephyr chain (BL-030 ...) stays on hold.

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
- BL-025 (IDF HTTPS control server (/ota, /version))
- BL-041 (host identify/measure verification against live LABID)

## Hardware state (2026-09-21)
- idf board: `/dev/lab-esp-idf`, USB serial `E0:72:A1:AA:23:90`, usbipd busid 7-4, Windows COM14.
  Flashed with BL-024 v1 signed build (WiFi STA support, NVS credentials provisioned at 0x9000,
  dual OTA partitions, rollback enabled, 1 Hz blink on GPIO48, confirms after 5s). Connected to WiFi.
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

## HARD RULES STILL IN FORCE
- Zephyr hold: do NOT touch ~/zephyr-ws, no Zephyr build.
- NO flash/write/erase without explicit per-instance owner go-ahead. Verify board identity
  (`ID_SERIAL_SHORT`) before every flash.
- Every "done" needs fresh pasted evidence, not summaries.
- Verify surprising results directly before reporting.
- Never burn eFuses; never commit keys/, backups/, *.pem.

## Known environment traps
- esptool: venv 5.4.0 = ~/bootlab-esp/.venv/bin/esptool (HAS elf2image);
  Debian /usr/bin/esptool 4.7.0 shadows it if .venv/bin not first on PATH.
  Export: `export PATH="$HOME/bootlab-esp/.venv/bin:$PATH"`.
- ESP-IDF v6.0.3 lives at `~/tools/esp-idf` (`. ~/tools/esp-idf/export.sh`).
- west topdir = ~/zephyr-ws (NOT the git repo); on hold.
- `ls` in this shell is aliased to eza and breaks on some args; use `command ls`.
- Untracked build artifacts (`bootloader/`, `tools/`, `common/labid/tests/build_audit/`) are not committed.
- Many tracked files show as modified from file-mode changes only (NTFS/WSL); content is unchanged.
