# scripts/

- `versions.env` — pinned dependency versions (source of truth for BL-002).
- `check_env.sh` — verifies all tools present and matching `versions.env`.
- `gen_keys.sh` — generates lab signing keys (BL-006); refuses to overwrite.
- `gen_tls_certs.sh` — generates lab Root CA and ESP32 server TLS certificates (BL-025); refuses to overwrite.
- `build_all.sh` — build orchestration.
- `reattach-boards.ps1` (Windows) — reattaches both ESP32-S3 boards to WSL2 via `usbipd`; run as Administrator on the Windows host whenever the boards drop off the usbipd bridge.
- `check-boards.sh` (WSL2/Linux) — read-only board visibility + identity check; run after `reattach-boards.ps1` to verify from the Linux side (lsusb, udev symlinks, USB-serial-vs-MAC per PLAN.md R13, `labflash resolve`).
- `serial_watch.py` (Windows/any) — reconnecting serial monitor: `python serial_watch.py COM14`. Waits for the port, streams the console, survives unplug/replug; DTR/RTS forced inactive before open. Use natively on Windows (not over usbipd, see PLAN.md R14). Ctrl+C to exit.
- `labid_check.py` (Windows/RPi4) — BL-022 live acceptance check: `python scripts\labid_check.py COM14`. Verifies ANNOUNCE <= 2 s, ID?/VER?/STATE? <= 100 ms, garbage -> ERR with no reset. Run natively, not over usbipd (PLAN R14).
- `confirm_check.py` (Windows/RPi4) — BL-023 live confirmation check: `python scripts\confirm_check.py COM14 <v1|no_confirm>`.
- `wifi_check.py` (Windows/RPi4) — BL-024 WiFi STA and NVS provisioning checker: `python scripts\wifi_check.py COM14`.
- `https_check.py` (Linux/Windows) — BL-025 HTTPS control server checker: `python scripts/https_check.py [--ip <IP>] [--com <COM_PORT>]`.
- `ota_check.py` (WSL/Linux) — BL-026 live acceptance: serves OTA images over HTTPS, triggers `POST /ota`, checks v1->v2 (slot flip, confirmed), and that `bad_sig` images are fully downloaded yet refused with the running image unchanged. Needs `tcp_forwarder.py` running on Windows when the server is in WSL2.
- `tcp_forwarder.py` (Windows) — forwards a LAN port to the same port inside WSL2 (NAT mode) so the board can reach a server running in WSL2.
- `rate_check.py` (Windows/any) — measures the LED blink rate from LABID's toggle counter: `python scripts\rate_check.py COM14 --expect-hz 4`. Self-contained (pyserial only); DTR/RTS held inactive before open.
- `labid_query.py` (Windows/any) — sends one LABID request and prints the reply with its CRC verified: `python scripts\labid_query.py COM14 VER?` (also `ID?`, `STATE?`, `HELLO`). Self-contained (pyserial only).
- `labid_check.py` now holds one connection and waits for the next boot `ANNOUNCE` (`--wait SECONDS`), so any reset works: RST, replug, OTA reboot or watchdog. A software reset does NOT drop the ESP32-S3 USB port, so waiting for the port to disappear never fires.
- `evidence/` — dated evidence files backing ticket "done" claims.

## USBIPD Switching between WSL2 and Windows (from WSL)

To attach or detach the IDF board (`busid 7-4`) directly from the WSL2 bash shell without switching windows:

```bash
# Attach board to WSL2 (makes it available as /dev/lab-esp-idf)
powershell.exe -Command "usbipd attach --wsl --busid 7-4" < /dev/null

# Detach board back to Windows (makes it available as COM14)
powershell.exe -Command "usbipd detach --busid 7-4" < /dev/null
```

> **NOTE:** Stdin redirection `< /dev/null` is required when invoking `powershell.exe` from WSL2 subprocesses to prevent PowerShell from hanging waiting on standard input.

