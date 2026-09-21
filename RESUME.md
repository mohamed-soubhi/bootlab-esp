# RESUME — bootlab-esp (checkpoint 2026-09-21)

Work and commit ONLY in `/home/msoubhi/bootlab-esp`. The owner's Windows copy
(`C:\MSA\embedded-OS\bootlab-esp`) is a scratch dir; never edit or push from it.

## Ticket state (from tickets.json)
- DONE: BL-001, 002, 003, 004, 006, 007, 010, 011, 012, 013, 040
- BLOCKED:
  - BL-020: all 4 ACs PASS with evidence (2026-09-21); blocked only on unfinished deps BL-005, BL-014.
  - BL-005: idf led_gpio=48 confirmed; zephyr led_gpio unknown (Zephyr hold); `psram_mode` unverified
    on both boards (the current IDF build does not enable PSRAM, so it cannot be detected yet).
  - BL-014: AC needs Zephyr native_sim + IDF linux builds; Zephyr on hold.
  - BL-041: host code done + mock-verified; needs real LABID firmware (BL-022) for IDF-only closure.
- TODO, IDF chain: BL-022 (LABID on USB-Serial-JTAG) -> BL-021 (partitions/signing/rollback) -> BL-024.
- Zephyr chain (BL-030 ...) stays on hold.

## BL-022 status (IN PROGRESS — steps A, B, C done; step D pending)
Done and pushed (HEAD ~800ede0):
- A: `common/labid/{include/labid_dispatch.h,src/labid_dispatch.c}` + device-mode parser
  (`labid_parser_init_device`: CRC-less requests, trailing CR, drop-until-newline, error reasons).
  20 new Unity tests (`common/labid/tests/test_dispatch.c`) + 26 legacy pass; ASan/UBSan clean;
  line coverage 99.0% dispatch / 95.5% parser. GAP: dispatch branch-taken coverage 71.6% (< BL-011's 90%).
- B: `esp_idf/components/labid_port/` (driver RX task prio 2, providers, ANNOUNCE ~1 s after start,
  one-fputs atomic frames, LF TX endings), wired in `esp_idf/main/app_main.c`;
  `esp_idf/CMakeLists.txt` adds `EXTRA_COMPONENT_DIRS ../common/labid`; `common/labid/CMakeLists.txt`
  builds labid_dispatch.c in both IDF and Zephyr branches (Zephyr NOT built — hold).
- C: v1 builds clean with a per-dir sdkconfig; variant verified after build (V1, GPIO48).
- Host: `identify.SerialLineTransport` holds DTR/RTS inactive before open (R14). No host pytest suite exists.

NEXT (step D) — needs explicit owner go-ahead to flash E0:72:A1:AA:23:90:
1. Verify `ID_SERIAL_SHORT` of /dev/lab-esp-idf, then from WSL:
   `. ~/tools/esp-idf/export.sh && cd esp_idf && idf.py -B build -p /dev/lab-esp-idf flash`
   (rebuild first if needed: `idf.py -B build -DSDKCONFIG=build/sdkconfig -DSDKCONFIG_DEFAULTS=sdkconfig.defaults build`;
   confirm `build/config/sdkconfig.h` says CONFIG_APP_VARIANT_V1 AFTER the build).
2. `usbipd.exe detach --busid 7-4`; owner replugs the board.
3. Owner runs on Windows: `python scripts\labid_check.py COM14` (then replug for the ANNOUNCE check).
   Confirm on-target from the boot log that App version / Compile time / ELF SHA256 match the new build.
4. UNTESTED ON TARGET (fix if they fail): USB-Serial-JTAG driver install alongside the console VFS;
   frame vs log interleaving; ANNOUNCE reaching a host that opens the port after ~600 ms.
5. If all ACs pass with pasted evidence: record in tickets.json (BL-022 desc), raise or waive the
   branch-coverage gap, `tickets_tool.py render/csv/check`, commit, push. Then BL-021, BL-041 (IDF-only).
   BL-022 cannot be set `done` while dep BL-020 is not done (BL-020 waits on BL-005/BL-014).
- Cosmetic: `app_main.c` still has the TEMPORARY blink_diag logging (3 lines/s); removable now.

## Hardware state (2026-09-21)
- idf board: `/dev/lab-esp-idf`, USB serial `E0:72:A1:AA:23:90`, usbipd busid 7-4, Windows COM14.
  Flashed with the **v1** build (blinks 1 Hz on GPIO48).
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
