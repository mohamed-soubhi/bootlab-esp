# BL-056[idf] — hil.yml self-hosted runner on RPi4

**Date:** 2026-09-22
**Host:** `msa-linuxRPi4` (192.168.1.150)

## What was done

1. Registered a GitHub Actions self-hosted runner on `msa-linuxRPi4` as user `msa` (no sudo, no
   systemd service): downloaded `actions-runner-linux-arm64-2.337.0.tar.gz`, ran `./config.sh --url
   https://github.com/mohamed-soubhi/bootlab-esp --token <registration-token> --name rpi4-hil --labels
   hil --work _work`, then `nohup ./run.sh > run.log 2>&1 & disown` to survive the SSH session ending.
2. Confirmed registration via the GitHub API:
   ```
   {"labels":["self-hosted","Linux","ARM64","hil"],"name":"rpi4-hil","status":"online","busy":false}
   ```
3. Triggered `hil.yml` for real via `workflow_dispatch` (run `35763148956`, job `106865958695`):
   - `Verify runner isolation & security (PLAN §8 P4)` — **PASSED** (no sudo, `keys/` clean).
   - `Install dependencies` — **PASSED**.
   - `Run HIL tests (IDF track)` — **FAILED** cleanly: all 19 selected `idf` tests errored with
     `Failed: live HIL: board serial port not found (pass --port COMx, or use --mock-rig for a
     simulation)`. Nothing else broke; this is the fixture correctly refusing rather than
     silently falling back to a mock (`tests_hil/conftest.py::live_backend`).

## Why the pytest failure is expected, not a blocker for this ticket

No ESP32-S3 board is physically attached to the RPi4 (`docs/rpi4_limitations.md` Sec 2.2 — boards are
cabled to the Windows workstation, COM14). BL-056's AC is "HIL job runs on PR" + "runner has no sudo
and no access to keys/" — both demonstrated by the security-check and install steps passing for real
on this runner. Getting a board physically onto the RPi4 (plus unmasking Bluetooth, which needs sudo)
is BL-056a's scope, still blocked on owner action.

## Result

`BL-056[idf]` -> **done**. `BL-056[zephyr]` stays `todo` (Zephyr hold, BL-063b).
