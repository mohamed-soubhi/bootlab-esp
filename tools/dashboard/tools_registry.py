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

    # 4. HIL & Unit Tests
    "test_host_units": ToolDefinition(
        id="test_host_units",
        name="Host Package Unit Tests (Mocked)",
        category="tests",
        description="Run the 207 fast mocked unit tests (core, CLI, dashboard, update, labid) — no hardware required.",
        command_template=[sys.executable, "-m", "pytest", "host/tests/", "-v"],
        parameters=[],
    ),
    "test_hil_all": ToolDefinition(
        id="test_hil_all",
        name="Run Full HIL Acceptance Suite",
        category="tests",
        description="Execute complete hardware test matrix (T01–T15) with live reporting.",
        command_template=[sys.executable, "-m", "pytest", "tests_hil/", "-v"],
        parameters=[
            Parameter(
                name="mock_rig",
                label="Simulated Rig (--mock-rig)",
                param_type="boolean",
                default=False,
                description="Simulate hardware without physical ESP32 boards connected.",
            ),
            Parameter(
                name="board",
                label="Board Track",
                param_type="select",
                default="idf",
                options=["idf", "zephyr", "all"],
                description="Target firmware stack to test.",
            ),
            Parameter(
                name="port",
                label="Serial Port",
                param_type="text",
                default="",
                description="Hardware serial COM port (e.g. COM14). Auto-detected if empty.",
            ),
        ],
    ),
    "test_hil_boot": ToolDefinition(
        id="test_hil_boot",
        name="HIL Boot & OTA Tests (T01–T03)",
        category="tests",
        description="Verify factory boot, WiFi update, and BLE update slot flips.",
        command_template=[sys.executable, "-m", "pytest", "tests_hil/test_t01_t03_boot_update.py", "-v"],
        parameters=[
            Parameter(
                name="mock_rig",
                label="Simulated Rig (--mock-rig)",
                param_type="boolean",
                default=False,
                description="Simulate hardware without physical ESP32 boards connected.",
            ),
            Parameter(
                name="board",
                label="Board Track",
                param_type="select",
                default="idf",
                options=["idf", "zephyr", "all"],
            ),
            Parameter(name="port", label="Serial Port", param_type="text", default=""),
        ],
    ),
    "test_hil_security": ToolDefinition(
        id="test_hil_security",
        name="HIL Security & Rollback Tests (T04–T09)",
        category="tests",
        description="Verify bad signature rejection, watchdog rollback, and auth gates.",
        command_template=[sys.executable, "-m", "pytest", "tests_hil/test_t04_t09_rollback_security.py", "-v"],
        parameters=[
            Parameter(
                name="mock_rig",
                label="Simulated Rig (--mock-rig)",
                param_type="boolean",
                default=False,
                description="Simulate hardware without physical ESP32 boards connected.",
            ),
            Parameter(
                name="board",
                label="Board Track",
                param_type="select",
                default="idf",
                options=["idf", "zephyr", "all"],
            ),
            Parameter(name="port", label="Serial Port", param_type="text", default=""),
        ],
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

        if p.name == "mock_rig":
            if val is True or str(val).lower() in ("true", "1"):
                cmd.append("--mock-rig")
        elif p.name == "board":
            if "--board" not in cmd:
                cmd.extend(["--board", str(val)])
        elif p.name == "port":
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
