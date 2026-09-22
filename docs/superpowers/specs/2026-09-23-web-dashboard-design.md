# Specification: bootlab-esp Operations Console (Web Dashboard)

**Document:** `docs/superpowers/specs/2026-09-23-web-dashboard-design.md`  
**Date:** 2026-09-23  
**Status:** Approved for Implementation  
**Type:** Architectural (New Subsystem)  

---

## 1. Overview & Objective

The `bootlab-esp` project features a suite of host CLI tools (`labflash`), Python diagnostic scripts (`scripts/`), and Hardware-in-the-Loop pytest suites (`tests_hil/`). Currently, running these tools requires terminal commands and separate log monitoring.

This specification defines the **Operations Console**, a lightweight, standalone web dashboard and API server located in `tools/dashboard/`, with a seamless shortcut integrated into `labflash gui`. It allows embedded developers, test engineers, and stakeholders to:
1. Scan and inspect physical target boards over USB serial and local LAN.
2. Trigger builds, factory flashes, recoveries, and dual-transport OTA deployments (WiFi HTTPS, NimBLE BLE, Zephyr UDP/BLE SMP).
3. Execute HIL test suites (T01–T15) and soak tests with real-time streaming console logs and ANSI color rendering.
4. Capture and export execution evidence directly from the browser.

---

## 2. Architectural Design

```
+--------------------------------------------------------------------------+
|                            Browser UI (HTML/CSS/JS)                      |
|                  Cyber Matrix Theme (Inter + JetBrains Mono)             |
|   [Target Status Bar]  [Workspace Cards]  [Live ANSI Terminal]  [History]  |
+--------------------------------------------------------------------------+
                                  ▲   │
                  REST API (JSON) │   │ SSE Log Stream (/api/stream)
                                  │   ▼
+--------------------------------------------------------------------------+
|                  tools/dashboard/server.py (HTTP + SSE Broker)           |
|                                                                          |
|   • GET  /                  -> Serves static dashboard                   |
|   • GET  /api/tools         -> Tool catalog & parameter schemas          |
|   • GET  /api/boards        -> Auto-detects COM ports & LAN targets      |
|   • POST /api/run           -> Dispatches background process             |
|   • POST /api/abort         -> Terminates active process group           |
|   • GET  /api/stream        -> Server-Sent Events line-by-line stream    |
|   • GET  /api/history       -> Past execution runs & exit statuses       |
+--------------------------------------------------------------------------+
                                      │
                                      ▼
+--------------------------------------------------------------------------+
|                  tools/dashboard/runner.py (Process Engine)              |
|                                                                          |
|   • Hardware Mutex Lock (prevents COM port collisions)                   |
|   • Non-blocking subprocess execution (shell=False)                      |
|   • Stdout/Stderr line-buffering & timestamp tagging                     |
|   • Graceful SIGINT -> SIGTERM process group cleanup                     |
+--------------------------------------------------------------------------+
                                      │
                   Executes against target infrastructure:
           ┌──────────────────────────┼──────────────────────────┐
           ▼                          ▼                          ▼
   host/labflash CLI          scripts/*.py tools         tests_hil/ (pytest)
```

---

## 3. Directory & File Layout

```
bootlab-esp/
├── tools/
│   └── dashboard/
│       ├── __init__.py           # Package marker
│       ├── server.py             # Threading HTTP server + SSE broker
│       ├── runner.py             # Non-blocking subprocess execution engine
│       ├── tools_registry.py     # Tool definitions, parameters, and categories
│       └── static/               # Frontend assets
│           ├── index.html        # Dashboard single-page application
│           ├── style.css         # Cyber Matrix theme (matches docs/index.html)
│           └── app.js            # State management, SSE streaming, ANSI parser
├── host/
│   └── labflash/
│       ├── gui_cmd.py            # CLI integration: 'labflash gui' subcommand
│       └── __main__.py           # Registers 'gui' parser arguments
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-09-23-web-dashboard-design.md
```

---

## 4. Component Specifications

### 4.1 CLI Integration (`host/labflash/gui_cmd.py` & `__main__.py`)
* Command syntax:
  ```bash
  labflash gui [--port 8080] [--host 127.0.0.1] [--no-browser]
  ```
* Standalone execution:
  ```bash
  python tools/dashboard/server.py [--port 8080] [--host 127.0.0.1]
  ```
* Binds to `--host` (default `127.0.0.1`, supports `0.0.0.0` for lab network access).
* Unless `--no-browser` is specified, automatically opens `http://<host>:<port>` in the default browser.

### 4.2 Backend Server (`tools/dashboard/server.py`)
* Built with Python's standard library `http.server.ThreadingHTTPServer` to guarantee zero extra heavy runtime dependencies.
* Implements MIME type handling for HTML, CSS, JS, SVG, and JSON.
* **Server-Sent Events (SSE)**: `/api/stream` endpoint maintains an open connection (`text/event-stream`, `Cache-Control: no-cache`), broadcasting queue events:
  * `event: log` -> `{ "text": "...", "timestamp": 12.4, "stream": "stdout" }`
  * `event: status` -> `{ "job_id": "...", "state": "running|passed|failed|aborted", "code": 0 }`

### 4.3 Process Runner & Safety Mutex (`tools/dashboard/runner.py`)
* **Hardware Lock**: Only one command touching hardware/serial ports can run concurrently. Attempting to start a second returns HTTP 409 Conflict.
* **Subprocess Management**: Spawns processes using `subprocess.Popen` with `start_new_session=True` (or Windows creation flags) so child processes can be terminated cleanly.
* **Cancellation**: `POST /api/abort` sends `SIGINT` first, allowing drivers to release COM ports, followed by process group kill if still active after 3 seconds.

### 4.4 Tool Registry (`tools/dashboard/tools_registry.py`)
Defines the catalog of runnable tools:
1. **Diagnostics**:
   * `doctor`: `python -m labflash doctor`
   * `resolve`: `python -m labflash resolve`
   * `identify`: `python -m labflash identify [--port PORT]`
   * `info`: `python -m labflash info [--port PORT]`
   * `measure`: `python -m labflash measure [--port PORT] [--duration SEC]`
   * `https_check`: `python scripts/https_check.py [--ip IP]`
2. **Build & Flash**:
   * `build_idf`: `python -m labflash build --target esp-idf [--variant v1|v2]`
   * `build_zephyr`: `python -m labflash build --target zephyr`
   * `flash`: `python -m labflash flash --target esp-idf [--variant v1|v2] [--port PORT]`
   * `recover`: `python -m labflash recover --target esp-idf [--variant v1] [--port PORT]`
   * `provision`: `python -m labflash provision --ssid SSID --password PASS --token TOKEN [--port PORT]`
3. **OTA Deployments**:
   * `update_wifi`: `python -m labflash update --transport wifi --variant v2 --target IP`
   * `update_ble`: `python -m labflash update --transport ble --variant v2 [--port PORT]`
   * `update_zephyr_udp`: `python scripts/zephyr_udp_ota.py [--ip IP] [--file FILE]`
   * `update_zephyr_ble`: `python scripts/zephyr_ble_ota.py [--file FILE]`
4. **HIL Test Suites**:
   * `test_hil_all`: `pytest tests_hil/ -v`
   * `test_hil_boot`: `pytest tests_hil/test_t01_t03_boot.py -v`
   * `test_hil_security`: `pytest tests_hil/test_t04_t09_security.py -v`
   * `test_hil_stress`: `pytest tests_hil/test_t10_t15_stress.py -v`

### 4.5 Frontend User Experience (`static/`)
* **Header & Theme**: Cyber Matrix dark/light mode toggle synced with localStorage.
* **Live Targets Bar**: Auto-refresh button running background scan of connected COM ports and active LAN IP pings.
* **Tool Workspace Tabs**: Tabbed interface grouping tools by domain (Diagnostics, Build/Flash, OTA, Tests) with parameter forms and instant "Run" button.
* **Live Terminal Window**:
  * Black terminal container (`JetBrains Mono`, 13px) with autoscroll.
  * Lightweight client-side ANSI-to-HTML parser rendering color codes (`32m` green, `33m` amber, `31m` red, `36m` cyan).
  * Elapsed timer display and "Stop Job" button.
  * "Copy Output" and "Clear" actions.
* **Run History**: Side drawer displaying last 10 runs with execution duration and exit code pills.

---

## 5. Security & Guardrails

1. **Whitelisting**: Only commands registered in `tools_registry.py` can be executed. Arbitrary shell command execution is prohibited.
2. **Path Sanitization**: All file parameters are validated within project bounds to prevent directory traversal.
3. **RPi4 Under-Voltage Protection**: Flashing commands detect if host is `msa-linuxRPi4` and require explicit confirmation, avoiding USB write brownout corruption (`0x50000`).

---

## 6. Verification & Test Plan

1. **Unit Testing**:
   * Test `tools_registry.py` validation and argument formatting.
   * Test `runner.py` process lifecycle (start, capture stdout, capture stderr, cancel, exit code).
   * Test `server.py` routing, parameter parsing, and SSE event streaming.
2. **Integration Testing**:
   * Launch `python tools/dashboard/server.py --port 8899 --no-browser` in test mode.
   * Run a mock tool (`doctor` or simulated identify), verify SSE logs are received by client.
   * Verify abort mechanism kills process and releases mutex.
3. **CLI Verification**:
   * Run `labflash gui --help` and verify options are recognized.
