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

from tests_hil.live_backend import LiveBackend, LiveRigError
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
    group.addoption("--soak-cycles", action="store", type=int, default=100, help="T16 soak cycles (default 100)")
    group.addoption("--board-ip", action="store", default="192.168.1.152", help="Board IP for HTTPS (live mode)")
    group.addoption("--images-dir", action="store", default=None, help="Dir holding build*/bootlab_idf_blink.bin")
    group.addoption("--keys-dir", action="store", default=None, help="Dir with ca.pem/server_cert.pem/server_key.pem")
    group.addoption("--env-file", action="store", default=None, help="credentials.env with OTA_TOKEN (live mode)")
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

    # Live: the port is used exclusively by LABID queries (a second reader would corrupt frames and, under
    # usbipd, reset the board). LABID verification output goes to update.log instead.
    with open(console_log, "w", encoding="utf-8") as f:
        f.write("[LIVE] raw console not captured; LABID queries and update output are in update.log\n")
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
    mock_version: str = "1.0.0"
    mock_slot: int = 0
    backend: "LiveBackend | None" = None
    board_ip: str = "192.168.1.152"

    @property
    def mode(self) -> str:
        return "mock" if self.is_mock else "live"

    def query_http_version(self, ip: str | None = None, timeout: float = 3.0) -> dict[str, Any] | None:
        """Query running app version via HTTPS /version."""
        if self.is_mock:
            return {
                "version": self.mock_version,
                "app": self.mock_version,
                "slot": self.mock_slot,
                "confirmed": True,
                "board": "idf",
            }
        url = f"https://{ip or self.board_ip}/version"
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

    def trigger_http_ota(
        self,
        url: str = "https://192.168.1.134:8443/update.bin",
        token: str = "wrong-token",
        ip: str | None = None,
        timeout: float = 5.0,
    ) -> int:
        """Trigger POST /ota on the target board and return the HTTP status code."""
        if self.is_mock:
            if token != "lab-bearer-token-secret-12345":
                return 401
            return 202
        endpoint = f"https://{ip or self.board_ip}/ota"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        payload = json.dumps({"url": url}).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "bootlab-hil",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return -1

    def query_labid_info(self) -> dict[str, str] | None:
        """Query board identity and version via LABID framing."""
        if self.is_mock:
            return {"board": "idf", "v": "1.0.0", "app": "bootlab_idf_blink", "slot": "0"}
        assert self.backend is not None
        return self.backend.labid_info()

    def log_artifact(self, filename: str, content: str) -> Path:
        p = self.artifacts_dir / filename
        header = "" if filename.endswith(".json") else f"mode: {self.mode}\n"  # JSON carries its own "mode" key
        p.write_text(header + content, encoding="utf-8")
        return p

    def measure_blink_rate(
        self,
        expect_hz: float = 1.0,
        duration_s: float = 5.0,
        tolerance: int = 2,
    ) -> tuple[float, bool]:
        """Measure LED toggle frequency over duration_s."""
        if self.is_mock:
            hz = 4.0 if self.mock_version == "2.0.0" else 1.0
            return hz, (abs(hz - expect_hz) < 0.1)
        assert self.backend is not None
        return self.backend.measure(duration_s, expect_hz, tolerance)

    def ensure_variant(self, variant: str, transport: str = "wifi") -> bool:
        """Precondition helper: make sure the board runs `variant` (v1/v2), updating over `transport` if not."""
        want = "2.0.0" if variant == "v2" else "1.0.0"
        current = self.mock_version if self.is_mock else (self.query_labid_info() or {}).get("v")
        return current == want or self.update_ota(variant, transport)

    def update_ota(self, variant: str, transport: str = "wifi") -> bool:
        """Perform an OTA update to a specified variant (e.g. 'v1' or 'v2')."""
        if self.is_mock:
            if variant == "v2":
                self.mock_version = "2.0.0"
                self.mock_slot = 1
            else:
                self.mock_version = "1.0.0"
                self.mock_slot = 0
            return True
        assert self.backend is not None
        return self.backend.update(variant, transport, self.artifacts_dir / "update.log")


@pytest.fixture
def live_backend(request: pytest.FixtureRequest, board_cfg: dict[str, Any], artifacts_dir: Path) -> LiveBackend | None:
    """Real-board backend, or None with --mock-rig. Refuses (fails) rather than falling back to a mock."""
    if request.config.getoption("--mock-rig"):
        return None
    port = request.config.getoption("--port") or get_board_port(board_cfg.get("board_name", ""))
    if not port:
        pytest.fail("live HIL: board serial port not found (pass --port COMx, or use --mock-rig for a simulation)")
    opt = request.config.getoption
    try:
        return LiveBackend.create(
            port=port, board_ip=opt("--board-ip"),
            images_dir=Path(opt("--images-dir")) if opt("--images-dir") else None,
            keys_dir=Path(opt("--keys-dir")) if opt("--keys-dir") else None,
            env_file=opt("--env-file"), rig_path=opt("--rig-config"))
    except LiveRigError as err:
        pytest.fail(f"live HIL unavailable: {err}")


@pytest.fixture
def factory_reset(live_backend: LiveBackend | None, artifacts_dir: Path) -> Generator[Callable[[], bool], None, None]:
    """Board starts on confirmed v1 and is restored to v1 afterwards. Live: verified through LABID."""

    def reset_to_v1() -> bool:
        if live_backend is None:
            return True
        return live_backend.reset_to_v1(artifacts_dir / "update.log")

    if not reset_to_v1():
        pytest.fail("live HIL: could not bring the board to confirmed v1 before the test")
    yield reset_to_v1
    if not reset_to_v1():
        pytest.fail("live HIL: could not restore the board to confirmed v1 after the test")


@pytest.fixture
def hil_rig(
    request: pytest.FixtureRequest,
    board_name: str,
    board_cfg: dict[str, Any],
    artifacts_dir: Path,
    serial_capture: Path,
    btmon_capture: Path,
    live_backend: LiveBackend | None,
    factory_reset: Callable[[], bool],
) -> HilRig:
    """Primary HIL test harness fixture combining board config, logging, and reset."""
    return HilRig(
        board=board_name,
        config=board_cfg,
        artifacts_dir=artifacts_dir,
        port=live_backend.port if live_backend else request.config.getoption("--port"),
        is_mock=live_backend is None,
        backend=live_backend,
        board_ip=request.config.getoption("--board-ip"),
    )
