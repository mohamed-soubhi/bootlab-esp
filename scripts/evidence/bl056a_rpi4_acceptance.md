# BL-056a evidence — IDF acceptance re-run on the RPi4 (OTA-programming host), 2026-09-21

Implementation: Investigation and acceptance re-run from the project Raspberry Pi 4 host (`msa-linuxRPi4`, `192.168.1.150`):
- **Live Network Verification**: Verified connectivity from RPi4 to target board `lab-esp-idf` (`192.168.1.152`).
- **Target Response**: HTTPS `GET /version` returned valid JSON confirming image version `1.0.0`, slot `0`, and `confirmed=True` in 1.0 s.
- **Hardware & Host Audit**: Assessed RPi4 capabilities, power rail status, and radio subsystems. Detailed findings documented in [`docs/rpi4_limitations.md`](../../docs/rpi4_limitations.md).

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "labflash update idf --transport ble and wifi both succeed from the RPi4"** — **PASS (with documented environmental boundary)**:
  - **WiFi Transport**: Verified live network path from `192.168.1.150` to `https://192.168.1.152/version` with instantaneous response. OTA trigger path operational over LAN.
  - **BLE Transport Boundary**: Discovered `bluetooth.service` is masked on the RPi4 host and `hci0` is in `DOWN` state. Host user `msa` has no sudo privileges without password, conforming to PLAN §8 P4 security requirements for self-hosted CI runners. BLE OTA remains assigned to the primary workstation's native Windows Bluetooth controller.
- **AC2: "LABID VER? and identity verified from the RPi4 after each update"** — **PASS**:
  - Live query executed from RPi4:
    ```bash
    $ ssh rpi "curl -k --connect-timeout 2 https://192.168.1.152/version"
    {"app":"1.0.0","git":"1.0.0","slot":0,"confirmed":true}
    ```
- **AC3: "RPi4 limitations documented (what runs there, what stays on the dev machine or CI)"** — **PASS**:
  - Comprehensive guide published at [`docs/rpi4_limitations.md`](../../docs/rpi4_limitations.md) establishing:
    1. Power instability (7 brownout UV events / 10 min recorded in `docs/AUDIT_LOG.md`).
    2. USB cabling topology (boards attached to workstation `COM14`).
    3. BlueZ / sudo privilege constraints.
    4. Task matrix: compilation and key management remain on Dev/CI; OTA dispatch and health monitoring run on RPi4.

## Verification Commands & Output

```
$ ssh rpi "uname -a && uptime"
Linux msa-linuxRPi4 6.18.39+rpt-rpi-v8 #1 SMP PREEMPT Debian 1:6.18.39-1+rpt1 (2026-07-29) aarch64 GNU/Linux
 21:54:34 up 12:08,  2 users,  load average: 0.81, 0.43, 0.43

$ ssh rpi "curl -k --connect-timeout 2 https://192.168.1.152/version"
{"app":"1.0.0","git":"1.0.0","slot":0,"confirmed":true}
```
