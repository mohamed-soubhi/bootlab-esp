# Operations Console (Web Dashboard) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight, real-time web operations console in `tools/dashboard/` accessible via `labflash gui` or standalone script to run firmware diagnostics, builds, flashing, dual-transport OTA, and HIL test suites with live streaming ANSI console output.

**Architecture:** Python standard library `http.server.ThreadingHTTPServer` backend serving a single-page Cyber Matrix frontend with Server-Sent Events (SSE) for line-by-line terminal log streaming. A thread-safe process runner enforces hardware mutual exclusion and manages subprocess trees.

**Tech Stack:** Python 3.10+, `http.server`, `subprocess`, `threading`, Server-Sent Events (SSE), Vanilla HTML5/CSS3/ES6, `pytest`.

**Spec:** [`docs/superpowers/specs/2026-09-23-web-dashboard-design.md`](file:///home/msoubhi/bootlab-esp/docs/superpowers/specs/2026-09-23-web-dashboard-design.md)

## Global Constraints

- **No heavy runtime dependencies:** Use Python standard library (`http.server`, `subprocess`, `threading`, `json`, `queue`); do NOT add FastAPI, Flask, or Uvicorn to runtime dependencies.
- **Design System Consistency:** Frontend MUST use the Cyber Matrix design tokens from `docs/index.html` (`Inter` typography, `JetBrains Mono` code, emerald/cyan accents, dark/light theme).
- **Process Safety:** Hardware commands MUST be guarded by a single-execution mutex lock to prevent COM port access collisions (`Access is denied`).
- **Whitelisted Tool Execution:** Only tools registered in `tools_registry.py` may be executed; no arbitrary shell strings (`shell=False`).
- **Clean Subprocess Abort:** Process termination must signal the process group (`start_new_session=True`) with `SIGINT` before escalating to `SIGTERM`.

---

## File Structure

```
tools/dashboard/
├── __init__.py               # Package marker
├── tools_registry.py         # Catalog of tools, categories, argument schemas, command builder
├── runner.py                 # Thread-safe subprocess runner with mutex lock & event queue
├── server.py                 # Threading HTTPServer, SSE broker, and REST routing
└── static/
    ├── index.html            # Single-page dashboard UI (Cyber Matrix layout)
    ├── style.css             # CSS tokens, layout grids, ANSI color styles
    └── app.js                # State management, SSE consumer, ANSI parser, action handlers

host/labflash/
├── gui_cmd.py                # Command handler for 'labflash gui'
└── __main__.py               # Argument parser registration for 'gui' subcommand

host/tests/
├── test_dashboard_registry.py  # Unit tests for tool catalog and argument builder
├── test_dashboard_runner.py    # Unit tests for process runner, mutex lock, and abort
└── test_dashboard_server.py    # Unit tests for HTTP endpoints and SSE streaming
```

---

### Task 1: Tool Registry & Command Line Builder

**Files:**
- Create: `tools/dashboard/__init__.py`
- Create: `tools/dashboard/tools_registry.py`
- Test: `host/tests/test_dashboard_registry.py`

**Interfaces:**
- Produces:
  - `TOOL_CATEGORIES: list[dict]`
  - `TOOLS: dict[str, ToolDefinition]`
  - `get_tool(tool_id: str) -> ToolDefinition | None`
  - `build_command(tool_id: str, params: dict) -> list[str]`
  - `detect_boards() -> list[dict]` (scans serial ports and basic ping/version check)

- [ ] **Step 1: Write the failing tests for tool registry and command builder**

Create `host/tests/test_dashboard_registry.py`:
```python
import sys
from pathlib import Path
import pytest

# Ensure repo root and host are in PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from tools.dashboard.tools_registry import (
    TOOLS,
    TOOL_CATEGORIES,
    get_tool,
    build_command,
    detect_boards,
)


def test_tool_catalog_structure():
    assert len(TOOL_CATEGORIES) >= 4
    categories = [c["id"] for c in TOOL_CATEGORIES]
    assert "diagnostics" in categories
    assert "build_flash" in categories
    assert "ota" in categories
    assert "tests" in categories


def test_get_tool():
    tool = get_tool("doctor")
    assert tool is not None
    assert tool.id == "doctor"
    assert tool.category == "diagnostics"

    assert get_tool("nonexistent_tool") is None


def test_build_command_doctor():
    cmd = build_command("doctor", {})
    assert sys.executable in cmd[0]
    assert "-m" in cmd
    assert "labflash" in cmd
    assert "doctor" in cmd


def test_build_command_identify_with_port():
    cmd = build_command("identify", {"port": "COM14"})
    assert "identify" in cmd
    assert "--port" in cmd
    assert "COM14" in cmd


def test_build_command_ota_wifi():
    cmd = build_command("update_wifi", {"variant": "v2", "target": "192.168.1.152"})
    assert "update" in cmd
    assert "--transport" in cmd
    assert "wifi" in cmd
    assert "--variant" in cmd
    assert "v2" in cmd
    assert "--target" in cmd
    assert "192.168.1.152" in cmd


def test_build_command_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        build_command("invalid_xyz", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_registry.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.dashboard'`

- [ ] **Step 3: Implement `tools/dashboard/__init__.py` and `tools/dashboard/tools_registry.py`**

Create `tools/dashboard/__init__.py`:
```python
"""bootlab-esp Operations Console Package."""
```

Create `tools/dashboard/tools_registry.py`:
```python
"""Catalog of tools, categories, and command line builders for the Operations Console."""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclasses.dataclass(frozen=True)
class Parameter:
    name: str
    label: str
    param_type: str  # "text", "select", "number", "boolean"
    default: Any
    options: list[str] = dataclasses.field(default_factory=list)
    description: str = ""
    required: bool = False


@dataclasses.dataclass(frozen=True)
class ToolDefinition:
    id: str
    name: str
    category: str
    description: str
    command_template: list[str]
    parameters: list[Parameter] = dataclasses.field(default_factory=list)
    safety_level: str = "safe"  # "safe", "power_sensitive", "destructive"


TOOL_CATEGORIES = [
    {"id": "diagnostics", "name": "Diagnostics & Health", "icon": "🔍"},
    {"id": "build_flash", "name": "Build & Flash", "icon": "🔨"},
    {"id": "ota", "name": "OTA Deployments", "icon": "🚀"},
    {"id": "tests", "name": "HIL Test Suites", "icon": "🧪"},
]

TOOLS: dict[str, ToolDefinition] = {
    # 1. Diagnostics
    "doctor": ToolDefinition(
        id="doctor",
        name="Environment Doctor Check",
        category="diagnostics",
        description="Verify host environment, python packages, and USB tool availability.",
        command_template=[sys.executable, "-m", "labflash", "doctor"],
        parameters=[],
    ),
    "resolve": ToolDefinition(
        id="resolve",
        name="Resolve Board Device Ports",
        category="diagnostics",
        description="Scan and resolve device serial port paths by USB serial number.",
        command_template=[sys.executable, "-m", "labflash", "resolve"],
        parameters=[],
    ),
    "identify": ToolDefinition(
        id="identify",
        name="Identify Board (LABID)",
        category="diagnostics",
        description="Query board identity, firmware variant, and running slot over serial.",
        command_template=[sys.executable, "-m", "labflash", "identify"],
        parameters=[
            Parameter(name="port", label="Serial Port", param_type="text", default="", description="e.g. COM14 or /dev/ttyACM0 (empty for auto-detect)"),
        ],
    ),
    "info": ToolDefinition(
        id="info",
        name="Show Board Info & Runtime State",
        category="diagnostics",
        description="Inspect hardware architecture, memory heap, and software git commit.",
        command_template=[sys.executable, "-m", "labflash", "info"],
        parameters=[
            Parameter(name="port", label="Serial Port", param_type="text", default="", description="Optional port"),
        ],
    ),
    "measure": ToolDefinition(
        id="measure",
        name="Measure LED Blink Frequency",
        category="diagnostics",
        description="Measure physical hardware toggle rate using LABID toggle counters.",
        command_template=[sys.executable, "-m", "labflash", "measure"],
        parameters=[
            Parameter(name="port", label="Serial Port", param_type="text", default="", description="Optional port"),
            Parameter(name="duration", label="Duration (seconds)", param_type="number", default=3, description="Sampling window in seconds"),
        ],
    ),
    "https_check": ToolDefinition(
        id="https_check",
        name="Check HTTPS /version Endpoint",
        category="diagnostics",
        description="Poll live target /version endpoint over WiFi HTTPS.",
        command_template=[sys.executable, "scripts/https_check.py"],
        parameters=[
            Parameter(name="ip", label="Target IP", param_type="text", default="192.168.1.152", description="IP address of ESP-IDF target", required=True),
        ],
    ),

    # 2. Build & Flash
    "build_idf": ToolDefinition(
        id="build_idf",
        name="Build & Sign ESP-IDF Firmware",
        category="build_flash",
        description="Build ESP-IDF firmware binary and generate cryptographic signatures.",
        command_template=[sys.executable, "-m", "labflash", "build", "--target", "esp-idf"],
        parameters=[
            Parameter(name="variant", label="Variant", param_type="select", default="v1", options=["v1", "v2"], description="Firmware version/variant"),
        ],
    ),
    "build_zephyr": ToolDefinition(
        id="build_zephyr",
        name="Build & Sign Zephyr RTOS Image",
        category="build_flash",
        description="Compile Zephyr MCUboot-compatible signed application binary.",
        command_template=[sys.executable, "-m", "labflash", "build", "--target", "zephyr"],
        parameters=[
            Parameter(name="variant", label="Variant", param_type="select", default="v1", options=["v1", "v2"], description="Firmware version/variant"),
        ],
    ),
    "flash": ToolDefinition(
        id="flash",
        name="Factory Flash Target (USB)",
        category="build_flash",
        description="Write factory bootloader, partition table, and v1 app to target via USB.",
        command_template=[sys.executable, "-m", "labflash", "flash"],
        safety_level="power_sensitive",
        parameters=[
            Parameter(name="target", label="Stack", param_type="select", default="esp-idf", options=["esp-idf", "zephyr"]),
            Parameter(name="variant", label="Variant", param_type="select", default="v1", options=["v1", "v2"]),
            Parameter(name="port", label="Serial Port", param_type="text", default=""),
        ],
    ),
    "recover": ToolDefinition(
        id="recover",
        name="Erase & Full Recover Target",
        category="build_flash",
        description="Completely erase flash memory and restore clean factory state.",
        command_template=[sys.executable, "-m", "labflash", "recover"],
        safety_level="destructive",
        parameters=[
            Parameter(name="target", label="Stack", param_type="select", default="esp-idf", options=["esp-idf", "zephyr"]),
            Parameter(name="port", label="Serial Port", param_type="text", default=""),
        ],
    ),

    # 3. OTA Updates
    "update_wifi": ToolDefinition(
        id="update_wifi",
        name="ESP-IDF WiFi OTA (HTTPS Pull)",
        category="ota",
        description="Start ephemeral HTTPS server, trigger POST /ota, and verify slot swap.",
        command_template=[sys.executable, "-m", "labflash", "update", "--transport", "wifi"],
        parameters=[
            Parameter(name="variant", label="Target Variant", param_type="select", default="v2", options=["v1", "v2"]),
            Parameter(name="target", label="Target IP", param_type="text", default="192.168.1.152", required=True),
        ],
    ),
    "update_ble": ToolDefinition(
        id="update_ble",
        name="ESP-IDF BLE OTA (NimBLE Push)",
        category="ota",
        description="Stream signed firmware packets over NimBLE GATT characteristics.",
        command_template=[sys.executable, "-m", "labflash", "update", "--transport", "ble"],
        parameters=[
            Parameter(name="variant", label="Target Variant", param_type="select", default="v2", options=["v1", "v2"]),
            Parameter(name="port", label="Verification Serial Port", param_type="text", default=""),
        ],
    ),
    "update_zephyr_udp": ToolDefinition(
        id="update_zephyr_udp",
        name="Zephyr UDP SMP OTA (Port 1337)",
        category="ota",
        description="Dispatch signed MCUboot image via MCUmgr UDP SMP protocol.",
        command_template=[sys.executable, "scripts/zephyr_udp_ota.py"],
        parameters=[
            Parameter(name="ip", label="Target IP", param_type="text", default="192.168.1.153", required=True),
            Parameter(name="variant", label="Variant", param_type="select", default="v2", options=["v1", "v2"]),
        ],
    ),
    "update_zephyr_ble": ToolDefinition(
        id="update_zephyr_ble",
        name="Zephyr BLE SMP OTA",
        category="ota",
        description="Stream MCUboot image over Bluetooth LE SMP service.",
        command_template=[sys.executable, "scripts/zephyr_ble_ota.py"],
        parameters=[
            Parameter(name="variant", label="Variant", param_type="select", default="v2", options=["v1", "v2"]),
        ],
    ),

    # 4. HIL Tests
    "test_hil_all": ToolDefinition(
        id="test_hil_all",
        name="Run Full HIL Acceptance Suite",
        category="tests",
        description="Execute complete hardware test matrix (T01–T15) with live reporting.",
        command_template=[sys.executable, "-m", "pytest", "tests_hil/", "-v"],
        parameters=[],
    ),
    "test_hil_boot": ToolDefinition(
        id="test_hil_boot",
        name="HIL Boot & OTA Tests (T01–T03)",
        category="tests",
        description="Verify factory boot, WiFi update, and BLE update slot flips.",
        command_template=[sys.executable, "-m", "pytest", "tests_hil/test_t01_t03_boot.py", "-v"],
        parameters=[],
    ),
    "test_hil_security": ToolDefinition(
        id="test_hil_security",
        name="HIL Security & Rollback Tests (T04–T09)",
        category="tests",
        description="Verify bad signature rejection, watchdog rollback, and auth gates.",
        command_template=[sys.executable, "-m", "pytest", "tests_hil/test_t04_t09_security.py", "-v"],
        parameters=[],
    ),
}


def get_tool(tool_id: str) -> ToolDefinition | None:
    return TOOLS.get(tool_id)


def build_command(tool_id: str, params: dict[str, Any]) -> list[str]:
    tool = get_tool(tool_id)
    if not tool:
        raise ValueError(f"Unknown tool: {tool_id}")

    cmd = list(tool.command_template)

    for p in tool.parameters:
        val = params.get(p.name, p.default)
        if val is None or val == "":
            continue

        if p.name == "port":
            cmd.extend(["--port", str(val)])
        elif p.name == "variant":
            if "--variant" not in cmd:
                cmd.extend(["--variant", str(val)])
        elif p.name == "target":
            if "--target" not in cmd:
                cmd.extend(["--target", str(val)])
        elif p.name == "ip":
            if "--ip" not in cmd and "--target" not in cmd:
                cmd.extend(["--ip", str(val)])
        elif p.name == "duration":
            cmd.extend(["--duration", str(val)])

    return cmd


def detect_boards() -> list[dict[str, Any]]:
    """Quick discovery of connected hardware ports and network reachability."""
    detected = []

    # 1. Serial device scan via pyserial / serial.tools
    try:
        from serial.tools import list_ports
        for port in list_ports.comports():
            # Check for ESP32-S3 USB JTAG/CDC (VID: 0x303A)
            is_esp = (port.vid == 0x303A) or ("USB" in (port.description or "").upper())
            detected.append({
                "type": "serial",
                "device": port.device,
                "description": port.description or "Serial Port",
                "is_esp": is_esp,
            })
    except ImportError:
        pass

    # 2. Network targets default health probe
    known_targets = [
        {"stack": "ESP-IDF", "ip": "192.168.1.152", "hostname": "lab-esp-idf"},
        {"stack": "Zephyr RTOS", "ip": "192.168.1.153", "hostname": "lab-esp-zephyr"},
    ]
    for target in known_targets:
        detected.append({
            "type": "network",
            "stack": target["stack"],
            "ip": target["ip"],
            "hostname": target["hostname"],
        })

    return detected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_registry.py -v`  
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/dashboard/__init__.py tools/dashboard/tools_registry.py host/tests/test_dashboard_registry.py
git commit -m "feat(dashboard): implement tool catalog, parameters, and command builder"
```

---

### Task 2: Process Runner Engine & Concurrency Lock

**Files:**
- Create: `tools/dashboard/runner.py`
- Test: `host/tests/test_dashboard_runner.py`

**Interfaces:**
- Produces:
  - `class JobStatus(enum.Enum): PENDING, RUNNING, PASSED, FAILED, ABORTED`
  - `class ProcessRunner:`
    - `start_job(tool_id: str, params: dict, cwd: str | None) -> str (job_id)`
    - `abort_active_job() -> bool`
    - `get_active_job() -> dict | None`
    - `get_history() -> list[dict]`
    - `subscribe_events() -> queue.Queue`
    - `unsubscribe_events(q: queue.Queue)`

- [ ] **Step 1: Write the failing tests for process runner engine**

Create `host/tests/test_dashboard_runner.py`:
```python
import sys
import time
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from tools.dashboard.runner import ProcessRunner, JobStatus


def test_runner_executes_simple_job():
    runner = ProcessRunner()
    q = runner.subscribe_events()

    job_id = runner.start_job("doctor", {})
    assert job_id is not None
    assert runner.is_running()

    # Wait for completion
    timeout = 10
    start = time.time()
    events = []
    while runner.is_running() and (time.time() - start < timeout):
        time.sleep(0.1)

    while not q.empty():
        events.append(q.get_nowait())

    runner.unsubscribe_events(q)
    assert not runner.is_running()
    history = runner.get_history()
    assert len(history) >= 1
    assert history[0]["job_id"] == job_id
    assert history[0]["status"] in [JobStatus.PASSED.value, JobStatus.FAILED.value]


def test_runner_enforces_mutex():
    runner = ProcessRunner()
    job_1 = runner.start_job("doctor", {})
    assert runner.is_running()

    with pytest.raises(RuntimeError, match="A job is already running"):
        runner.start_job("doctor", {})

    # Wait for finish
    while runner.is_running():
        time.sleep(0.05)


def test_runner_can_abort_job():
    runner = ProcessRunner()
    # Run a long measure or doctor
    job_id = runner.start_job("measure", {"duration": 10})
    time.sleep(0.2)
    assert runner.is_running()

    aborted = runner.abort_active_job()
    assert aborted is True

    time.sleep(0.5)
    assert not runner.is_running()
    history = runner.get_history()
    assert history[0]["status"] == JobStatus.ABORTED.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_runner.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.dashboard.runner'`

- [ ] **Step 3: Implement `tools/dashboard/runner.py`**

Create `tools/dashboard/runner.py`:
```python
"""Subprocess execution engine with concurrency lock and streaming event dispatch."""

from __future__ import annotations

import enum
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from tools.dashboard.tools_registry import build_command, get_tool

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


class ProcessRunner:
    def __init__(self, cwd: Path | None = None) -> None:
        self._cwd = cwd or REPO_ROOT
        self._lock = threading.Lock()
        self._active_proc: subprocess.Popen | None = None
        self._active_job: dict[str, Any] | None = None
        self._history: list[dict[str, Any]] = []
        self._subscribers: list[queue.Queue] = []
        self._subscribers_lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self._active_proc is not None and self._active_proc.poll() is None

    def get_active_job(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_job:
                return dict(self._active_job)
            return None

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def subscribe_events(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe_events(self, q: queue.Queue) -> None:
        with self._subscribers_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        payload = {"event": event_type, "data": data, "timestamp": time.time()}
        with self._subscribers_lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass

    def start_job(self, tool_id: str, params: dict[str, Any]) -> str:
        with self._lock:
            if self._active_proc is not None and self._active_proc.poll() is None:
                raise RuntimeError("A job is already running. Please wait or cancel the active job.")

            cmd = build_command(tool_id, params)
            tool = get_tool(tool_id)
            tool_name = tool.name if tool else tool_id

            job_id = f"job-{int(time.time() * 1000)}"
            start_time = time.time()

            # Set execution environment with PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{self._cwd / 'host'}:{self._cwd}:{env.get('PYTHONPATH', '')}"
            env["PYTHONUNBUFFERED"] = "1"

            # Preexec for process group creation on POSIX
            kwargs: dict[str, Any] = {
                "cwd": str(self._cwd),
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
            }
            if sys.platform != "win32":
                kwargs["start_new_session"] = True
            else:
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

            try:
                proc = subprocess.Popen(cmd, **kwargs)
            except Exception as e:
                self._broadcast("status", {
                    "job_id": job_id,
                    "status": JobStatus.FAILED.value,
                    "error": str(e),
                })
                raise

            job_info = {
                "job_id": job_id,
                "tool_id": tool_id,
                "tool_name": tool_name,
                "cmd": cmd,
                "cmd_str": " ".join(cmd),
                "params": params,
                "status": JobStatus.RUNNING.value,
                "start_time": start_time,
                "end_time": None,
                "exit_code": None,
                "output_lines": [],
            }

            self._active_proc = proc
            self._active_job = job_info

            # Start background reader thread
            t = threading.Thread(
                target=self._reader_loop,
                args=(proc, job_id, start_time),
                daemon=True,
            )
            t.start()

            self._broadcast("status", {
                "job_id": job_id,
                "tool_name": tool_name,
                "cmd": " ".join(cmd),
                "status": JobStatus.RUNNING.value,
            })

            return job_id

    def _reader_loop(self, proc: subprocess.Popen, job_id: str, start_time: float) -> None:
        output_lines: list[str] = []
        try:
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    elapsed = round(time.time() - start_time, 2)
                    output_lines.append(line)
                    self._broadcast("log", {
                        "job_id": job_id,
                        "line": line,
                        "elapsed": elapsed,
                    })
        except Exception:
            pass
        finally:
            exit_code = proc.wait()
            end_time = time.time()
            elapsed = round(end_time - start_time, 2)

            with self._lock:
                status = JobStatus.PASSED.value if exit_code == 0 else JobStatus.FAILED.value
                if self._active_job and self._active_job.get("status") == JobStatus.ABORTED.value:
                    status = JobStatus.ABORTED.value

                if self._active_job and self._active_job.get("job_id") == job_id:
                    self._active_job["status"] = status
                    self._active_job["exit_code"] = exit_code
                    self._active_job["end_time"] = end_time
                    self._active_job["elapsed"] = elapsed
                    self._active_job["output_lines"] = output_lines
                    self._history.insert(0, dict(self._active_job))
                    # Retain last 20 jobs
                    self._history = self._history[:20]

                    self._active_proc = None

            self._broadcast("status", {
                "job_id": job_id,
                "status": status,
                "exit_code": exit_code,
                "elapsed": elapsed,
            })

    def abort_active_job(self) -> bool:
        with self._lock:
            if self._active_proc is None or self._active_proc.poll() is not None:
                return False

            proc = self._active_proc
            if self._active_job:
                self._active_job["status"] = JobStatus.ABORTED.value

        try:
            if sys.platform != "win32":
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            else:
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        except Exception:
            proc.terminate()

        # Give it up to 2 seconds to release port before killing
        def _force_kill():
            time.sleep(2.0)
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        threading.Thread(target=_force_kill, daemon=True).start()
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_runner.py -v`  
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/dashboard/runner.py host/tests/test_dashboard_runner.py
git commit -m "feat(dashboard): implement thread-safe process runner with mutex and streaming"
```

---

### Task 3: Backend HTTP Server & SSE Event Broker

**Files:**
- Create: `tools/dashboard/server.py`
- Test: `host/tests/test_dashboard_server.py`

**Interfaces:**
- Produces:
  - `class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler)`
  - `run_server(host: str, port: int, open_browser: bool) -> None`
  - Routes:
    - `GET /` -> static HTML
    - `GET /api/tools` -> json
    - `GET /api/boards` -> json
    - `POST /api/run` -> json `{ "job_id": ... }`
    - `POST /api/abort` -> json `{ "aborted": true }`
    - `GET /api/history` -> json
    - `GET /api/stream` -> Server-Sent Events

- [ ] **Step 1: Write the failing tests for HTTP server and endpoints**

Create `host/tests/test_dashboard_server.py`:
```python
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from tools.dashboard.server import make_server


@pytest.fixture(scope="module")
def server_url():
    server = make_server(host="127.0.0.1", port=8989)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    yield "http://127.0.0.1:8989"
    server.shutdown()


def test_get_root_serves_html(server_url):
    req = urllib.request.Request(f"{server_url}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "<title>" in content or "bootlab-esp" in content


def test_get_tools_endpoint(server_url):
    req = urllib.request.Request(f"{server_url}/api/tools")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "categories" in data
        assert "tools" in data
        assert len(data["tools"]) >= 5


def test_get_boards_endpoint(server_url):
    req = urllib.request.Request(f"{server_url}/api/boards")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "boards" in data
        assert isinstance(data["boards"], list)


def test_run_and_history_lifecycle(server_url):
    payload = json.dumps({"tool_id": "doctor", "params": {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url}/api/run",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "job_id" in data
        job_id = data["job_id"]

    # Check history
    time.sleep(1.0)
    req_hist = urllib.request.Request(f"{server_url}/api/history")
    with urllib.request.urlopen(req_hist) as resp:
        hist_data = json.loads(resp.read().decode("utf-8"))
        assert "history" in hist_data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_server.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.dashboard.server'`

- [ ] **Step 3: Implement `tools/dashboard/server.py`**

Create `tools/dashboard/server.py`:
```python
"""Lightweight HTTP server with Server-Sent Events broker for the Operations Console."""

from __future__ import annotations

import argparse
import http.server
import json
import queue
import socketserver
import sys
import webbrowser
from pathlib import Path
from typing import Any

from tools.dashboard.runner import ProcessRunner
from tools.dashboard.tools_registry import (
    TOOL_CATEGORIES,
    TOOLS,
    detect_boards,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
GLOBAL_RUNNER = ProcessRunner()


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            return self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif self.path == "/style.css":
            return self._serve_file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
        elif self.path == "/app.js":
            return self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        elif self.path == "/api/tools":
            return self._send_json({
                "categories": TOOL_CATEGORIES,
                "tools": {
                    k: {
                        "id": v.id,
                        "name": v.name,
                        "category": v.category,
                        "description": v.description,
                        "safety_level": v.safety_level,
                        "parameters": [
                            {
                                "name": p.name,
                                "label": p.label,
                                "type": p.param_type,
                                "default": p.default,
                                "options": p.options,
                                "description": p.description,
                                "required": p.required,
                            }
                            for p in v.parameters
                        ],
                    }
                    for k, v in TOOLS.items()
                },
            })
        elif self.path == "/api/boards":
            return self._send_json({"boards": detect_boards()})
        elif self.path == "/api/history":
            return self._send_json({
                "history": GLOBAL_RUNNER.get_history(),
                "active_job": GLOBAL_RUNNER.get_active_job(),
            })
        elif self.path == "/api/stream":
            return self._handle_sse_stream()
        else:
            return super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/run":
            body = self._read_json_body()
            tool_id = body.get("tool_id")
            params = body.get("params", {})

            if not tool_id:
                return self._send_error_json("Missing 'tool_id' parameter", 400)

            try:
                job_id = GLOBAL_RUNNER.start_job(tool_id, params)
                return self._send_json({"job_id": job_id, "status": "running"})
            except RuntimeError as e:
                return self._send_error_json(str(e), 409)
            except Exception as e:
                return self._send_error_json(str(e), 500)

        elif self.path == "/api/abort":
            aborted = GLOBAL_RUNNER.abort_active_job()
            return self._send_json({"aborted": aborted})
        else:
            self.send_error(404, "Endpoint not found")

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404, f"File not found: {path.name}")
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _handle_sse_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        event_queue = GLOBAL_RUNNER.subscribe_events()
        try:
            # Send initial keep-alive
            self.wfile.write(b": keep-alive\n\n")
            self.wfile.flush()

            while True:
                try:
                    payload = event_queue.get(timeout=1.0)
                    evt = payload.get("event", "message")
                    data = json.dumps(payload.get("data", {}))
                    msg = f"event: {evt}\ndata: {data}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive comment
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            GLOBAL_RUNNER.unsubscribe_events(event_queue)


def make_server(host: str = "127.0.0.1", port: int = 8080) -> socketserver.ThreadingTCPServer:
    # Allow address reuse
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    return socketserver.ThreadingTCPServer((host, port), DashboardRequestHandler)


def run_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    server = make_server(host=host, port=port)
    url = f"http://{host}:{port}"
    print(f"\n=======================================================")
    print(f" ⚡ bootlab-esp Operations Console")
    print(f" Listening on: {url}")
    print(f" Press Ctrl+C to stop.")
    print(f"=======================================================\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down Operations Console...")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="bootlab-esp Operations Console")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)
```

- [ ] **Step 4: Create static placeholder files so HTTP tests can serve root**

Create `tools/dashboard/static/index.html` (minimal stub for test pass):
```html
<!DOCTYPE html>
<html>
<head><title>bootlab-esp Operations Console</title></head>
<body><h1>bootlab-esp</h1></body>
</html>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_server.py -v`  
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add tools/dashboard/server.py tools/dashboard/static/index.html host/tests/test_dashboard_server.py
git commit -m "feat(dashboard): implement HTTP server and SSE streaming event endpoints"
```

---

### Task 4: Frontend UI (Cyber Matrix Theme, ANSI Terminal & Controls)

**Files:**
- Modify: `tools/dashboard/static/index.html`
- Create: `tools/dashboard/static/style.css`
- Create: `tools/dashboard/static/app.js`

**Interfaces:**
- Produces:
  - Responsive Cyber Matrix dark/light theme matching `docs/index.html`
  - Targets Auto-Discovery bar
  - Category Workspace Tabs (Diagnostics, Build/Flash, OTA, Tests)
  - Tool Parameter Cards & Instant Run Buttons
  - Live ANSI Terminal Console with Autoscroll & Copy Log
  - Real-time Connection Indicator & Job Cancellation

- [ ] **Step 1: Implement `tools/dashboard/static/index.html`**

Write `tools/dashboard/static/index.html`:
```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>bootlab-esp — Operations Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <!-- Header -->
  <header class="app-header">
    <div class="header-brand">
      <span class="brand-badge">HIL LAB</span>
      <h1 class="brand-title">bootlab-esp <span>// OPERATIONS CONSOLE</span></h1>
    </div>
    <div class="header-actions">
      <div id="connection-status" class="status-pill offline">
        <span class="status-dot"></span> <span id="status-text">Connecting...</span>
      </div>
      <button class="btn-theme" onclick="toggleTheme()" title="Toggle Dark/Light Mode">🌓</button>
    </div>
  </header>

  <!-- Main Container -->
  <main class="dashboard-grid">
    <!-- TOP: Target Discovery Bar -->
    <section class="targets-bar card">
      <div class="targets-header">
        <div class="section-title">
          <span>📡 Target Hardware &amp; Network Interfaces</span>
        </div>
        <button class="btn-pill" onclick="refreshBoards()">↻ Scan Targets</button>
      </div>
      <div id="targets-list" class="targets-chips">
        <span class="text-muted">Scanning for USB and network devices...</span>
      </div>
    </section>

    <!-- MIDDLE: Workspaces & Parameters -->
    <section class="workspaces card">
      <!-- Category Tabs -->
      <div class="tab-pills" id="category-tabs">
        <!-- Rendered by app.js -->
      </div>

      <!-- Tool Selector & Action Grid -->
      <div class="workspace-body">
        <div class="tools-list" id="tools-container">
          <!-- Rendered by app.js -->
        </div>

        <div class="tool-params-panel" id="params-panel">
          <div class="params-header">
            <h3 id="selected-tool-name">Select a Tool</h3>
            <span id="selected-tool-badge" class="badge-tag"></span>
          </div>
          <p id="selected-tool-desc" class="text-secondary">Choose a diagnostic, build, update, or test tool from the left.</p>
          
          <form id="tool-form" onsubmit="event.preventDefault(); runSelectedTool();">
            <div id="dynamic-params" class="params-grid">
              <!-- Dynamically populated parameters -->
            </div>
            
            <div class="form-actions">
              <button type="submit" id="btn-run" class="btn-primary" disabled>
                <span>▶ Run Tool</span>
              </button>
              <button type="button" id="btn-abort" class="btn-danger hidden" onclick="abortJob()">
                <span>⏹ Stop / Abort</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </section>

    <!-- BOTTOM: Live Terminal Console & History -->
    <section class="console-section card">
      <div class="console-header">
        <div class="console-title">
          <span>⚡ Live Terminal Log Stream</span>
          <span id="job-timer" class="mono text-muted">0.00s</span>
        </div>
        <div class="console-controls">
          <label class="toggle-label">
            <input type="checkbox" id="autoscroll-toggle" checked> Autoscroll
          </label>
          <button class="btn-pill" onclick="copyConsoleLog()">Copy Log</button>
          <button class="btn-pill" onclick="clearConsoleLog()">Clear</button>
        </div>
      </div>
      
      <div id="terminal-window" class="terminal-body mono">
        <div class="terminal-welcome">
          bootlab-esp Operations Console ready.<br>
          Select a tool and click "Run Tool" to stream live execution logs.
        </div>
      </div>
    </section>
  </main>

  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Implement `tools/dashboard/static/style.css`**

Write `tools/dashboard/static/style.css`:
```css
/* ==========================================================================
   bootlab-esp Operations Console — Cyber Matrix Design System
   ========================================================================== */
:root {
  --bg-primary: #0a0e14;
  --bg-secondary: #111822;
  --bg-card: #121a24;
  --bg-surface: #172230;
  --bg-surface-hover: #1c2a3b;
  --text-primary: #f0fdf4;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --text-contrast: #ffffff;
  --border-color: #1e293b;
  --border-subtle: rgba(255, 255, 255, 0.08);

  --accent-primary: #10b981;
  --accent-neon: #00ff88;
  --accent-cyan: #38bdf8;
  --accent-amber: #f59e0b;
  --accent-rose: #f43f5e;
  --accent-violet: #a855f7;

  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-full: 9999px;

  --font-heading: 'Inter', system-ui, -apple-system, sans-serif;
  --font-body: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

[data-theme="light"] {
  --bg-primary: #f8fafc;
  --bg-secondary: #ffffff;
  --bg-card: #ffffff;
  --bg-surface: #f1f5f9;
  --bg-surface-hover: #e2e8f0;
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #64748b;
  --text-contrast: #0f172a;
  --border-color: #cbd5e1;
  --border-subtle: rgba(0, 0, 0, 0.08);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font-body);
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: 16px 24px;
  min-height: 100vh;
}

/* Header */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 18px;
}
.header-brand { display: flex; align-items: center; gap: 10px; }
.brand-badge {
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-cyan));
  color: #000;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 800;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
}
.brand-title {
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 20px;
  color: var(--text-contrast);
}
.brand-title span { color: var(--accent-cyan); font-weight: 600; font-size: 16px; }

.header-actions { display: flex; align-items: center; gap: 12px; }
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  border: 1px solid var(--border-color);
  background: var(--bg-surface);
}
.status-pill.online { color: var(--accent-neon); border-color: var(--accent-primary); }
.status-pill.offline { color: var(--accent-rose); border-color: var(--accent-rose); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

.btn-theme {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  color: var(--text-contrast);
  padding: 6px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
}

/* Layout */
.dashboard-grid { display: flex; flex-direction: column; gap: 16px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
}

/* Targets Bar */
.targets-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.section-title { font-family: var(--font-heading); font-weight: 700; font-size: 15px; color: var(--text-contrast); }
.targets-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.target-chip {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 6px 12px;
  font-size: 12.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.target-chip strong { color: var(--accent-cyan); font-family: var(--font-mono); }

/* Workspaces */
.tab-pills { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 12px; }
.tab-btn {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 6px 14px;
  border-radius: var(--radius-full);
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.tab-btn:hover { background: var(--bg-surface-hover); color: var(--text-contrast); }
.tab-btn.active {
  background: var(--accent-primary);
  color: #000;
  border-color: var(--accent-primary);
  font-weight: 700;
}

.workspace-body { display: grid; grid-template-columns: 320px 1fr; gap: 20px; }
@media (max-width: 900px) { .workspace-body { grid-template-columns: 1fr; } }

.tools-list { display: flex; flex-direction: column; gap: 8px; max-height: 380px; overflow-y: auto; }
.tool-item {
  padding: 10px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s;
}
.tool-item:hover { border-color: var(--accent-cyan); background: var(--bg-surface-hover); }
.tool-item.active { border-color: var(--accent-primary); background: rgba(16, 185, 129, 0.12); }
.tool-item-title { font-weight: 700; font-size: 13.5px; color: var(--text-contrast); margin-bottom: 3px; }
.tool-item-desc { font-size: 11.5px; color: var(--text-muted); line-height: 1.4; }

.tool-params-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  flex-direction: column;
}
.params-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.params-header h3 { font-family: var(--font-heading); font-weight: 700; font-size: 17px; color: var(--text-contrast); }
.badge-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: rgba(56, 189, 248, 0.15);
  color: var(--accent-cyan);
}

.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }
@media (max-width: 600px) { .params-grid { grid-template-columns: 1fr; } }
.form-group label { display: block; font-size: 11.5px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; }
.form-group input, .form-group select {
  width: 100%;
  padding: 8px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-contrast);
  font-family: var(--font-mono);
  font-size: 12.5px;
}
.form-group input:focus, .form-group select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-actions { display: flex; gap: 10px; margin-top: auto; padding-top: 14px; }
.btn-primary {
  background: var(--accent-primary);
  color: #000;
  border: none;
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 13.5px;
  padding: 10px 18px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-danger {
  background: var(--accent-rose);
  color: #fff;
  border: none;
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 13.5px;
  padding: 10px 18px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.hidden { display: none !important; }

.btn-pill {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  cursor: pointer;
}
.btn-pill:hover { color: var(--text-contrast); background: var(--bg-surface-hover); }

/* Terminal Console */
.console-section { display: flex; flex-direction: column; }
.console-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.console-title { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 14px; color: var(--text-contrast); }
.console-controls { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--text-muted); }
.toggle-label { cursor: pointer; display: flex; align-items: center; gap: 4px; }

.terminal-body {
  background: #05080c;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 14px;
  height: 340px;
  overflow-y: auto;
  font-size: 12.5px;
  line-height: 1.6;
  color: #cbd5e1;
  white-space: pre-wrap;
  word-break: break-all;
}
.terminal-welcome { color: var(--text-muted); font-style: italic; }

.log-pass { color: var(--accent-neon); }
.log-warn { color: var(--accent-amber); }
.log-fail { color: var(--accent-rose); }
.log-cyan { color: var(--accent-cyan); }
.mono { font-family: var(--font-mono); }
.text-muted { color: var(--text-muted); }
.text-secondary { color: var(--text-secondary); font-size: 12.5px; }
```

- [ ] **Step 3: Implement `tools/dashboard/static/app.js`**

Write `tools/dashboard/static/app.js`:
```javascript
// =============================================================================
// bootlab-esp Operations Console Application Engine
// =============================================================================

let categories = [];
let tools = {};
let activeCategory = "diagnostics";
let selectedToolId = null;
let eventSource = null;
let autoscroll = true;
let jobStartTime = null;
let timerInterval = null;

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initEventSource();
  loadTools();
  refreshBoards();

  document.getElementById("autoscroll-toggle").addEventListener("change", (e) => {
    autoscroll = e.target.checked;
  });
});

// Theme Management
function initTheme() {
  const saved = localStorage.getItem("bootlab_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("bootlab_theme", next);
}

// SSE Connection
function initEventSource() {
  const statusEl = document.getElementById("connection-status");
  const statusText = document.getElementById("status-text");

  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/stream");

  eventSource.onopen = () => {
    statusEl.className = "status-pill online";
    statusText.innerText = "Online";
  };

  eventSource.onerror = () => {
    statusEl.className = "status-pill offline";
    statusText.innerText = "Reconnecting...";
  };

  eventSource.addEventListener("log", (e) => {
    const data = JSON.parse(e.data);
    appendTerminalLine(data.line);
  });

  eventSource.addEventListener("status", (e) => {
    const data = JSON.parse(e.data);
    handleJobStatusUpdate(data);
  });
}

// Load Tools Catalog
async function loadTools() {
  try {
    const res = await fetch("/api/tools");
    const data = await res.json();
    categories = data.categories;
    tools = data.tools;
    renderCategories();
    selectCategory(categories[0]?.id || "diagnostics");
  } catch (err) {
    appendTerminalLine(`\x1b[31m[ERROR] Failed to load tools catalog: ${err.message}\x1b[0m\n`);
  }
}

function renderCategories() {
  const tabs = document.getElementById("category-tabs");
  tabs.innerHTML = "";
  categories.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = `tab-btn ${cat.id === activeCategory ? "active" : ""}`;
    btn.innerText = `${cat.icon} ${cat.name}`;
    btn.onclick = () => selectCategory(cat.id);
    tabs.appendChild(btn);
  });
}

function selectCategory(catId) {
  activeCategory = catId;
  renderCategories();

  const container = document.getElementById("tools-container");
  container.innerHTML = "";

  const catTools = Object.values(tools).filter((t) => t.category === catId);
  catTools.forEach((tool, index) => {
    const item = document.createElement("div");
    item.className = `tool-item ${tool.id === selectedToolId ? "active" : ""}`;
    item.innerHTML = `
      <div class="tool-item-title">${tool.name}</div>
      <div class="tool-item-desc">${tool.description}</div>
    `;
    item.onclick = () => selectTool(tool.id);
    container.appendChild(item);

    if (index === 0 && (!selectedToolId || !tools[selectedToolId] || tools[selectedToolId].category !== catId)) {
      selectTool(tool.id);
    }
  });
}

function selectTool(toolId) {
  selectedToolId = toolId;
  const tool = tools[toolId];
  if (!tool) return;

  document.querySelectorAll(".tool-item").forEach((el) => {
    el.classList.toggle("active", el.querySelector(".tool-item-title")?.innerText === tool.name);
  });

  document.getElementById("selected-tool-name").innerText = tool.name;
  document.getElementById("selected-tool-desc").innerText = tool.description;
  const badge = document.getElementById("selected-tool-badge");
  badge.innerText = tool.safety_level.toUpperCase();
  badge.className = `badge-tag ${tool.safety_level === "destructive" ? "log-fail" : tool.safety_level === "power_sensitive" ? "log-warn" : ""}`;

  const paramsContainer = document.getElementById("dynamic-params");
  paramsContainer.innerHTML = "";

  tool.parameters.forEach((p) => {
    const group = document.createElement("div");
    group.className = "form-group";
    const label = document.createElement("label");
    label.innerText = p.label;

    let input;
    if (p.type === "select") {
      input = document.createElement("select");
      input.name = p.name;
      p.options.forEach((opt) => {
        const option = document.createElement("option");
        option.value = opt;
        option.innerText = opt;
        if (opt === p.default) option.selected = true;
        input.appendChild(option);
      });
    } else {
      input = document.createElement("input");
      input.type = p.type === "number" ? "number" : "text";
      input.name = p.name;
      input.value = p.default !== undefined ? p.default : "";
      if (p.description) input.placeholder = p.description;
    }

    group.appendChild(label);
    group.appendChild(input);
    paramsContainer.appendChild(group);
  });

  document.getElementById("btn-run").disabled = false;
}

// Target Detection
async function refreshBoards() {
  const container = document.getElementById("targets-list");
  container.innerHTML = '<span class="text-muted">Scanning hardware ports and network...</span>';

  try {
    const res = await fetch("/api/boards");
    const data = await res.json();
    container.innerHTML = "";

    if (!data.boards || data.boards.length === 0) {
      container.innerHTML = '<span class="text-muted">No hardware serial or network targets found.</span>';
      return;
    }

    data.boards.forEach((b) => {
      const chip = document.createElement("div");
      chip.className = "target-chip";
      if (b.type === "serial") {
        chip.innerHTML = `<span>🔌</span> <strong>${b.device}</strong> (${b.description})`;
      } else {
        chip.innerHTML = `<span>🌐</span> <strong>${b.ip}</strong> (${b.stack} // ${b.hostname})`;
      }
      container.appendChild(chip);
    });
  } catch (err) {
    container.innerHTML = `<span class="log-fail">Scan failed: ${err.message}</span>`;
  }
}

// Command Execution
async function runSelectedTool() {
  if (!selectedToolId) return;

  const form = document.getElementById("tool-form");
  const formData = new FormData(form);
  const params = {};
  formData.forEach((val, key) => {
    params[key] = val;
  });

  const btnRun = document.getElementById("btn-run");
  const btnAbort = document.getElementById("btn-abort");

  btnRun.classList.add("hidden");
  btnAbort.classList.remove("hidden");

  clearConsoleLog();
  appendTerminalLine(`\x1b[36m$ labflash ${selectedToolId} [executing...]\x1b[0m\n\n`);

  jobStartTime = Date.now();
  startTimer();

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_id: selectedToolId, params }),
    });

    if (!res.ok) {
      const err = await res.json();
      appendTerminalLine(`\x1b[31m[ERROR] ${err.error || "Execution failed"}\x1b[0m\n`);
      stopTimer();
      btnRun.classList.remove("hidden");
      btnAbort.classList.add("hidden");
    }
  } catch (e) {
    appendTerminalLine(`\x1b[31m[ERROR] Network error: ${e.message}\x1b[0m\n`);
    stopTimer();
    btnRun.classList.remove("hidden");
    btnAbort.classList.add("hidden");
  }
}

async function abortJob() {
  try {
    await fetch("/api/abort", { method: "POST" });
    appendTerminalLine(`\n\x1b[33m[!] Abort signal dispatched to runner.\x1b[0m\n`);
  } catch (e) {
    appendTerminalLine(`\x1b[31m[ERROR] Failed to send abort: ${e.message}\x1b[0m\n`);
  }
}

function handleJobStatusUpdate(data) {
  if (data.status === "passed") {
    appendTerminalLine(`\n\x1b[32m✔ Completed successfully with exit code 0 (${data.elapsed}s)\x1b[0m\n`);
    finishJobUI();
  } else if (data.status === "failed") {
    appendTerminalLine(`\n\x1b[31m✘ Failed with exit code ${data.exit_code} (${data.elapsed}s)\x1b[0m\n`);
    finishJobUI();
  } else if (data.status === "aborted") {
    appendTerminalLine(`\n\x1b[33m⏹ Job was aborted by user (${data.elapsed}s)\x1b[0m\n`);
    finishJobUI();
  }
}

function finishJobUI() {
  stopTimer();
  document.getElementById("btn-run").classList.remove("hidden");
  document.getElementById("btn-abort").classList.add("hidden");
}

function startTimer() {
  stopTimer();
  const timerEl = document.getElementById("job-timer");
  timerInterval = setInterval(() => {
    if (!jobStartTime) return;
    const elapsed = ((Date.now() - jobStartTime) / 1000).toFixed(2);
    timerEl.innerText = `${elapsed}s`;
  }, 100);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

// ANSI Escape Code Parser for HTML Output
function parseAnsi(text) {
  let clean = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  // Simple ANSI replacements for common colors
  clean = clean.replace(/\x1b\[32m/g, '<span class="log-pass">');
  clean = clean.replace(/\x1b\[31m/g, '<span class="log-fail">');
  clean = clean.replace(/\x1b\[33m/g, '<span class="log-warn">');
  clean = clean.replace(/\x1b\[36m/g, '<span class="log-cyan">');
  clean = clean.replace(/\x1b\[1m/g, '<strong style="color:#fff">');
  clean = clean.replace(/\x1b\[0m/g, "</span>");
  // Strip unhandled escape sequences
  clean = clean.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
  return clean;
}

function appendTerminalLine(text) {
  const terminal = document.getElementById("terminal-window");
  terminal.innerHTML += parseAnsi(text);
  if (autoscroll) {
    terminal.scrollTop = terminal.scrollHeight;
  }
}

function clearConsoleLog() {
  document.getElementById("terminal-window").innerHTML = "";
  document.getElementById("job-timer").innerText = "0.00s";
}

function copyConsoleLog() {
  const terminal = document.getElementById("terminal-window");
  navigator.clipboard.writeText(terminal.innerText);
}
```

- [ ] **Step 4: Verify static assets are correctly served**

Run: `PYTHONPATH=. .venv/bin/pytest host/tests/test_dashboard_server.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/dashboard/static/
git commit -m "feat(dashboard): build responsive Cyber Matrix UI with live ANSI terminal"
```

---

### Task 5: CLI Integration (`labflash gui`) & End-to-End Verification

**Files:**
- Create: `host/labflash/gui_cmd.py`
- Modify: `host/labflash/__main__.py`
- Test: `host/tests/test_gui_cli.py`

**Interfaces:**
- Produces:
  - Subcommand `labflash gui` with `--host`, `--port`, and `--no-browser` flags
  - Seamless redirection from `labflash` CLI to `tools/dashboard/server.py:run_server`

- [ ] **Step 1: Write test for `labflash gui` CLI argument parsing**

Create `host/tests/test_gui_cli.py`:
```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "host"))

from labflash.__main__ import build_parser


def test_labflash_gui_subcommand_registered():
    parser = build_parser()
    args = parser.parse_args(["gui", "--port", "9090", "--no-browser"])
    assert args.command == "gui"
    assert args.port == 9090
    assert args.no_browser is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=host:.:. .venv/bin/pytest host/tests/test_gui_cli.py -v`  
Expected: FAIL with `error: invalid choice: 'gui'`

- [ ] **Step 3: Implement `host/labflash/gui_cmd.py` and register in `host/labflash/__main__.py`**

Create `host/labflash/gui_cmd.py`:
```python
"""GUI subcommand integration for labflash."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def run_gui(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> int:
    """Launch the bootlab-esp Operations Console."""
    # Ensure dashboard package can be loaded
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        from tools.dashboard.server import run_server
        run_server(host=host, port=port, open_browser=open_browser)
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to start Operations Console: {e}", file=sys.stderr)
        return 1
```

Modify `host/labflash/__main__.py`:
Register the `gui` subcommand in `build_parser()` and dispatch in `main()`:
```python
    # gui subcommand
    gui_p = subparsers.add_parser(
        "gui",
        help="launch the bootlab-esp web operations console",
        description="Launch local browser operations console to run and monitor tools.",
    )
    gui_p.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    gui_p.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    gui_p.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
```
And in `main()` dispatch:
```python
    elif args.command == "gui":
        from labflash.gui_cmd import run_gui
        return run_gui(host=args.host, port=args.port, open_browser=not args.no_browser)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=host:. .venv/bin/pytest host/tests/test_gui_cli.py -v`  
Expected: PASS

- [ ] **Step 5: Run full test suite across all dashboard components**

Run: `PYTHONPATH=host:. .venv/bin/pytest host/tests/test_dashboard*.py host/tests/test_gui_cli.py -v`  
Expected: 100% PASS

- [ ] **Step 6: Commit**

```bash
git add host/labflash/gui_cmd.py host/labflash/__main__.py host/tests/test_gui_cli.py
git commit -m "feat(cli): wire 'labflash gui' subcommand to Operations Console"
```
