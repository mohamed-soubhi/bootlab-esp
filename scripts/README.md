# scripts/

- `versions.env` — pinned dependency versions (source of truth for BL-002).
- `check_env.sh` — verifies all tools present and matching `versions.env`.
- `gen_keys.sh` — generates lab signing keys (BL-006); refuses to overwrite.
- `build_all.sh` — build orchestration.
- `reattach-boards.ps1` (Windows) — reattaches both ESP32-S3 boards to WSL2 via `usbipd`; run as Administrator on the Windows host whenever the boards drop off the usbipd bridge.
- `check-boards.sh` (WSL2/Linux) — read-only board visibility + identity check; run after `reattach-boards.ps1` to verify from the Linux side (lsusb, udev symlinks, USB-serial-vs-MAC per PLAN.md R13, `labflash resolve`).
- `serial_watch.py` (Windows/any) — reconnecting serial monitor: `python serial_watch.py COM14`. Waits for the port, streams the console, survives unplug/replug; DTR/RTS forced inactive before open. Use natively on Windows (not over usbipd, see PLAN.md R14). Ctrl+C to exit.
- `evidence/` — dated evidence files backing ticket "done" claims.
