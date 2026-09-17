# RESUME — bootlab-esp (checkpoint before reboot, 2026-09-17 ~03:05)

## Committed state
- HEAD: `2d4f948` Save: AUDIT_LOG.md + IDF host-test scaffolding (from killed job, reviewed)
- Working tree: CLEAN.
- Recently: BL-014 -> blocked (d438880); BL-014 ESP_PLATFORM fix (874acd0);
  check_env.sh mcuboot path fix (aff41ee); BL-004 done (bc2a802).

## Ticket state (verified from tickets.json)
- DONE: BL-001, BL-002, BL-004, BL-006, BL-010, BL-011, BL-012, BL-013
- BLOCKED: BL-003 (needs 2 boards + brown-out AC), BL-005 (LED GPIO/PSRAM need flash),
  BL-007 (needs 2 boards enumerated), BL-014 (AC needs Zephyr native_sim + IDF linux builds)
- TODO: everything gated behind (a) Zephyr hold [item 4] or (b) hardware/power.

## ON REBOOT — next steps (owner approved option 1: boards READ-ONLY, no flash)
1. get_throttled expected 0x0 after fresh reboot (owner says don't re-verify; proceed).
2. Boards SHOULD be attached read-only (owner connecting). Confirm via `lsusb`:
   expect 303a:1001 (USB JTAG/serial) + 303a:4001 (Espressif Device).
3. Re-verify BL-007 (labflash doctor): AC = "Reports 2 ESP USB devices, BT adapter,
   WiFi" + "Non-zero exit on any missing item". Run: `cd host && PYTHONPATH=$PWD
   python3 -m labflash doctor`.
4. If BL-007 passes -> re-attempt BL-003 (udev symlinks /dev/lab-esp-zephyr +
   /dev/lab-esp-idf exist; survive replug+swap; NO brown-out resets over 10 min).
5. Then unlock host chain BL-040/041/042/045/046 (labflash core, host-only).

## HARD RULES STILL IN FORCE
- Zephyr hold (item 4): do NOT touch ~/zephyr-ws, no Zephyr build, do not cite the
  old contested "success".
- NO flash/write/erase without explicit per-instance owner go-ahead.
- Every "done" needs fresh pasted evidence, not summaries.
- Verify surprising results directly before reporting.

## Known environment traps
- esptool: venv 5.4.0 = ~/bootlab-esp/.venv/bin/esptool (HAS elf2image);
  Debian /usr/bin/esptool 4.7.0 shadows it if .venv/bin not first on PATH.
  Export: `export PATH="$HOME/bootlab-esp/.venv/bin:$PATH"`.
- west topdir = ~/zephyr-ws (NOT the git repo). check_env.sh resolves mcuboot at
  $WESTROOT/bootloader/mcuboot.
- Models migrated: default + all cron -> deepseek-v4.1-flash (deepseek-v4-flash retired).
