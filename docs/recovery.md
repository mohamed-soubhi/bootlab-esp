# Recovery — restore a board from its backup

Both boards are backed up as **full 16 MB flash images** in `backups/`:

| Board            | MAC                    | Backup image              | efuse dump              |
|------------------|------------------------|---------------------------|-------------------------|
| Board #1 Zephyr  | `ac:a7:04:2c:3b:04`    | `esp_ACA7042C3B04.bin`    | `efuse_ACA7042C3B04.txt`|
| Board #2 IDF     | `e0:72:a1:aa:23:90`    | `esp_E072A1AA2390.bin`    | `efuse_E072A1AA2390.txt`|

The `.sha256` files verify the images. eFuses (`efuse_*.txt`) are **read-only diagnostic
dumps only** — eFuses cannot be re-burned from them.

> ⚠️ **Board identity is by USB serial, not by port name.** Two ESP32-S3 boards have the
> same VID:PID (`303a:1001`), so before restoring you must confirm which board is on the
> bus by its **USB serial** (see `host/config/rig.yaml` and `host/udev/*.rules`). Restoring
> the wrong image bricks the wrong board.

## Prerequisites
- Python `esptool` **v5.4.0 or newer** — must be the venv one, **not** the Debian system
  `esptool` (v4.7.0 has a different CLI and will fail). Ensure resolution:
  ```bash
  export PATH="$HOME/bootlab-esp/.venv/bin:$PATH"
  command -v esptool        # must print .../.venv/bin/esptool
  esptool version           # must print esptool v5.4.0
  ```
  (The Debian `/usr/bin/esptool` is a known trap on this host — see
  `scripts/evidence/ZEPHYR_HELLO_BUILD_PROOF.md`.)

## Restore procedure (per board)

1. **Verify the backup checksum first:**
   ```bash
   cd ~/bootlab-esp/backups
   sha256sum -c esp_<MAC>.sha256          # replace <MAC> per board table above
   ```

2. **Put the target board into ROM download mode.**
   - Disconnect it, then hold the **BOOT** button (GPIO0 low) and plug in via USB,
     then release BOOT. It should enumerate as an Espressif device in download mode
     (esptool detects it at port `/dev/ttyACM*`; confirm by USB serial so you know
     you're on the right board — see rig.yaml).

3. **Write the full flash image back at offset 0** (v5.x syntax, hyphenated):
   ```bash
   cd ~/bootlab-esp/backups
   esptool --chip esp32s3 --before default-reset --after hard-reset write-flash \
     --flash-mode dio --flash-size 16MB 0x0 esp_<MAC>.bin
   ```
   > `--flash-size 16MB` and `--flash-mode dio` are accepted by esptool v5.4.0
   > (verified against `esptool write-flash --help`). The old underscore forms
   > (`write_flash`, `--flash_mode`, `--flash_size`, `default_reset`,
   > `hard_reset`) are **deprecated in v5** — avoid them. The write erases and
   > rewrites the whole device, so every partition returns to its backed-up state.
   > ⚠️ Caveat: this command has been verified for **flag-acceptance only**
   > (`esptool --help` parses cleanly) — it was **not** dry-run against a real
   > image write. If used in an actual emergency and something unexpected
   > happens, note that the syntax was checked but the full command was not
   > executed end-to-end.

4. **Verify** the write (optional but recommended):
   ```bash
   esptool --chip esp32s3 --before default-reset --after hard-reset verify-flash 0x0 esp_<MAC>.bin
   ```
   Compare against the `.sha256` of the on-disk image.

## Notes
- **Do NOT** restore Board #1's image onto Board #2 (or vice versa) — the images are
  board-specific (different MAC-derived identities and firmware).
- `backups/` holds both the images and the eFuse dumps. The eFuse dumps are for
  **documentation/diagnostics only**; if Secure Boot or flash encryption were ever
  enabled they would NOT be restorable from these files. (Both boards currently have
  Secure Boot OFF and flash encryption OFF.)
- If esptool fails early with `unrecognized arguments` it is almost certainly the
  Debian v4.7.0 binary — re-check `command -v esptool`.
- Nothing here is committed to git (`backups/` is gitignored, perms `700`/`600`).
