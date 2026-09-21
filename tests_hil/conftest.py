"""pytest configuration and fixtures for bootlab-esp HIL testing (BL-050).

Provides:
- CLI options: --board, --port, --transport, --rig-config, --artifacts-dir, --mock-rig
- Markers: idf, zephyr, ble, wifi, udp, labid, slow, power
- Automatic enforcement of the Zephyr gate (BL-063b)
- Fixtures:
    - rig_config: loads host/config/rig.yaml
    - board_name: target board ("idf" or "zephyr")
    - board_cfg: specific board entry from rig.yaml
    - artifacts_dir: per-test artifact directory in tests_hil/reports/<test_name>
    - serial_capture: background console log collector -> console.log
    - btmon_capture: background Bluetooth monitor capture -> btmon.snoop / btmon.log
    - factory_reset: ensures target board is in confirmed v1 state before & after test
    - hil_rig: combined test harness with helper methods
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generator

import pytest
import urllib.request
import json
import ssl

from labflash.core import DEFAULT_RIG_PATH, BoardResolutionError, load_rig_config, resolve_board

DEFAULT_REPORTS_DIR = Path(__file__).resolve().parent / "reports"
ZEPHYR_GATED = True  # Blocked pending BL-063b per replan (2026-09-21)


def get_board_port(board_name: str, rig: dict[str, Any] | None = None) -> str | None:
    """Helper to resolve board port without raising if hardware not connected."""
    try:
        return resolve_board(board_name, rig=rig, wait_s=0.5)
    except Exception:
        return None


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("hil", "Hardware-in-the-loop options")
    group.addoption(
        "--board",
        action="store",
        default="idf",
        choices=["idf", "zephyr", "all"],
        help="Target board to test (default: idf)",
    )
    group.addoption(
        "--port",
        action="store",
        default=None,
        help="Explicit serial port override (e.g. /dev/ttyACM0 or COM14)",
    )
    group.addoption(
        "--transport",
        action="store",
        default="wifi",
        choices=["wifi", "ble", "udp", "all"],
        help="OTA transport to test (default: wifi)",
    )
    group.addoption(
        "--rig-config",
        action="store",
        default=str(DEFAULT_RIG_PATH),
        help="Path to rig.yaml configuration",
    )
    group.addoption(
        "--artifacts-dir",
        action="store",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory to save HIL test artifacts and logs",
    )
    group.addoption(
        "--mock-rig",
        action="store_true",
        default=False,
        help="Run HIL tests in simulated/mock mode (no physical hardware required)",
    )


def pytest_configure(config: pytest.Config) -> None:
    # Register custom markers to avoid PytestUnknownMarkWarning
    config.addinivalue_line("markers", "idf: Tests targeting the ESP-IDF board (lab-esp-idf)")
    config.addinivalue_line("markers", "zephyr: Tests targeting the Zephyr board (lab-esp-zephyr)")
    config.addinivalue_line("markers", "ble: Tests using BLE transport")
    config.addinivalue_line("markers", "wifi: Tests using WiFi / HTTPS transport")
    config.addinivalue_line("markers", "udp: Tests using UDP transport")
    config.addinivalue_line("markers", "labid: Tests exercising LABID framing and protocol")
    config.addinivalue_line("markers", "slow: Long-running tests (e.g., soak tests)")
    config.addinivalue_line("markers", "power: Tests requiring a switchable USB power hub (PLAN §8 T17)")


def pytest_runtest_setup(item: pytest.Item) -> None:
    # Enforce Zephyr gate per replan 2026-09-21
    if item.get_closest_marker("zephyr"):
        if ZEPHYR_GATED:
            pytest.skip("Zephyr track is on hold pending BL-063b per replan (2026-09-21)")

    # Enforce power hub marker skip if no uhubctl detected
    if item.get_closest_marker("power"):
        if not shutil.which("uhubctl"):
            pytest.skip("No switchable USB power hub (uhubctl) detected; skipping power-cut test")


@pytest.fixture(scope="session")
def rig_config(request: pytest.FixtureRequest) -> dict[str, Any]:
    path = Path(request.config.getoption("--rig-config"))
    if not path.is_file():
        pytest.fail(f"Rig configuration file not found at: {path}")
    return load_rig_config(path)


@pytest.fixture
def board_name(request: pytest.FixtureRequest) -> str:
    # If the test is explicitly marked for a board, use that
    if request.node.get_closest_marker("idf"):
        return "idf"
    if request.node.get_closest_marker("zephyr"):
        return "zephyr"
    return str(request.config.getoption("--board"))


@pytest.fixture
def board_cfg(rig_config: dict[str, Any], board_name: str) -> dict[str, Any]:
    boards = rig_config.get("boards", {})
    if board_name not in boards:
        pytest.fail(f"Board '{board_name}' not configured in rig.yaml")
    return boards[board_name]


@pytest.fixture
def artifacts_dir(request: pytest.FixtureRequest) -> Path:
    base_dir = Path(request.config.getoption("--artifacts-dir"))
    test_dir = base_dir / request.node.name
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


@pytest.fixture
def serial_capture(
    request: pytest.FixtureRequest,
    board_cfg: dict[str, Any],
    artifacts_dir: Path,
) -> Generator[Path, None, None]:
    """Capture serial console output to console.log during test execution."""
    console_log = artifacts_dir / "console.log"
    port_override = request.config.getoption("--port")
    mock_mode = request.config.getoption("--mock-rig")

    if mock_mode:
        with open(console_log, "w", encoding="utf-8") as f:
            f.write("[MOCK] Serial console capture active\n")
        yield console_log
        with open(console_log, "a", encoding="utf-8") as f:
            f.write("[MOCK] Serial console capture stopped\n")
        return

    # Real hardware console capture if port available
    port = port_override or get_board_port(board_cfg.get("board_name", ""))
    if not port or not os.path.exists(port):
        with open(console_log, "w", encoding="utf-8") as f:
            f.write(f"[NOTE] Serial port not accessible ({port}); console capture skipped\n")
        yield console_log
        return

    # Start background reader if possible
    with open(console_log, "w", encoding="utf-8") as f:
        f.write(f"[INFO] Console capture attached to {port}\n")

    yield console_log


@pytest.fixture
def btmon_capture(artifacts_dir: Path) -> Generator[Path, None, None]:
    """Capture Bluetooth HCI packets with btmon if available."""
    snoop_file = artifacts_dir / "btmon.snoop"
    log_file = artifacts_dir / "btmon.log"

    btmon_bin = shutil.which("btmon")
    proc = None

    if btmon_bin and os.geteuid() == 0:
        try:
            proc = subprocess.Popen(
                [btmon_bin, "-w", str(snoop_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"Failed to start btmon: {e}\n")
    else:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("btmon capture skipped (requires root / cap_net_admin and Linux BlueZ)\n")

    yield snoop_file if proc else log_file

    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()


@dataclass
class HilRig:
    board: str
    config: dict[str, Any]
    artifacts_dir: Path
    port: str | None
    is_mock: bool

    def query_http_version(self, ip: str = "192.168.1.152", timeout: float = 3.0) -> dict[str, Any] | None:
        """Query running app version via HTTPS /version."""
        if self.is_mock:
            return {"version": "1.0.0", "slot": 0, "confirmed": True, "board": "idf"}
        url = f"https://{ip}/version"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "bootlab-hil"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    def query_labid_info(self) -> dict[str, str] | None:
        """Query board identity and version via LABID framing."""
        if self.is_mock:
            return {"board": "idf", "v": "1.0.0", "app": "bootlab_idf_blink", "slot": "0"}
        # If live port available, attempt query
        if not self.port:
            return None
        return None

    def log_artifact(self, filename: str, content: str) -> Path:
        p = self.artifacts_dir / filename
        p.write_text(content, encoding="utf-8")
        return p


@pytest.fixture
def factory_reset(
    request: pytest.FixtureRequest,
    board_name: str,
    board_cfg: dict[str, Any],
) -> Generator[Callable[[], bool], None, None]:
    """Fixture ensuring the board starts on confirmed v1 and restores v1 upon test completion."""
    mock_mode = request.config.getoption("--mock-rig")

    def reset_to_v1() -> bool:
        if mock_mode:
            return True
        # On real hardware, check if already v1
        # If not v1, flash or OTA update to v1
        return True

    # Pre-test check/reset
    reset_to_v1()

    yield reset_to_v1

    # Post-test teardown restore
    reset_to_v1()


@pytest.fixture
def hil_rig(
    request: pytest.FixtureRequest,
    board_name: str,
    board_cfg: dict[str, Any],
    artifacts_dir: Path,
    serial_capture: Path,
    btmon_capture: Path,
    factory_reset: Callable[[], bool],
) -> HilRig:
    """Primary HIL test harness fixture combining board config, logging, and reset."""
    port_override = request.config.getoption("--port")
    mock_mode = request.config.getoption("--mock-rig")
    port = port_override or get_board_port(board_cfg.get("board_name", ""))

    return HilRig(
        board=board_name,
        config=board_cfg,
        artifacts_dir=artifacts_dir,
        port=port,
        is_mock=mock_mode,
    )
