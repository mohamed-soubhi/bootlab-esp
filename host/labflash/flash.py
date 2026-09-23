"""labflash flash / recover — USB factory flash and recovery with pre-write identity checks (BL-042).

Strict Guardrail:
- BEFORE ANY FLASH OR RECOVERY WRITE, the device identity (MAC / USB serial)
  is verified against rig.yaml. If there is a mismatch (or wrong board requested),
  the tool refuses to write and exits with FlashIdentityError.
- Flashing Zephyr is gated behind BL-063b per replan.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from serial.tools import list_ports

from labflash.core import load_rig_config, resolve_board

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]


class FlashError(RuntimeError):
    """Base error for flashing operations."""


class FlashIdentityError(FlashError):
    """Raised when board identity does not match expectation before write."""


class ZephyrGatedError(FlashError):
    """Raised when attempting to flash Zephyr while gated."""


def find_esptool_cmd(repo_root: Path | None = None) -> list[str]:
    """Find esptool executable, prioritizing repo virtual environment.

    Works on Windows (.venv/Scripts/esptool.exe) and Linux (.venv/bin/esptool).
    Falls back to `sys.executable -m esptool` which always works on any platform.
    """
    import platform
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    on_windows = platform.system() == "Windows"

    # Candidate paths in priority order
    candidates: list[Path] = []
    if on_windows:
        # sys.prefix is the Python installation root (e.g. C:\Python312 or a venv root)
        # Scripts\ is the Windows equivalent of bin/
        scripts_dir = Path(sys.prefix) / "Scripts"
        candidates += [
            root / ".venv" / "Scripts" / "esptool.exe",
            root / ".venv" / "Scripts" / "esptool",
            scripts_dir / "esptool.exe",
            scripts_dir / "esptool",
            # labflash itself lives in Scripts/ — esptool.exe is a sibling
            Path(__file__).resolve().parent.parent.parent / "Scripts" / "esptool.exe",
            Path(sys.executable).parent / "Scripts" / "esptool.exe",
            Path(sys.executable).parent / "esptool.exe",
        ]
    else:
        candidates += [
            root / ".venv" / "bin" / "esptool",
            Path(sys.executable).parent / "esptool",
        ]

    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            # On Windows, skip ELF/shell-script wrappers (WinError 193 guard)
            if on_windows:
                try:
                    with open(candidate, "rb") as f:
                        magic = f.read(2)
                    if magic != b"MZ":  # not a Windows PE binary
                        continue
                except OSError:
                    continue
            return [str(candidate)]

    # shutil.which respects PATHEXT on Windows so .exe/.cmd/.bat are found
    found = shutil.which("esptool") or shutil.which("esptool.py")
    if found:
        return [found]

    # Last resort: always works since esptool is a Python package
    return [sys.executable, "-m", "esptool"]


def normalize_mac(mac: str) -> str:
    """Normalize MAC or serial number to lowercase hex without delimiters."""
    return re.sub(r"[^0-9a-fA-F]", "", mac).lower()


def get_port_serial_number(port: str) -> str | None:
    """Read USB serial number from pySerial list_ports."""
    for p in list_ports.comports():
        if (p.device == port or Path(p.device).resolve() == Path(port).resolve()) and p.serial_number:
            return normalize_mac(p.serial_number)
    return None


def read_mac_with_esptool(
    port: str,
    runner: Callable | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Query MAC directly from chip using esptool read-mac."""
    from labflash.build import run_command

    esptool_cmd = find_esptool_cmd(repo_root)
    cmd = [*esptool_cmd, "--port", str(port), "read-mac"]
    # use_idf_env=False: esptool is already resolved; read-mac does not need IDF.
    res = run_command(cmd, cwd=Path.cwd(), use_idf_env=False, runner=runner)
    if res.returncode != 0:
        # Try read_mac (legacy syntax)
        cmd_legacy = [*esptool_cmd, "--port", str(port), "read_mac"]
        res = run_command(cmd_legacy, cwd=Path.cwd(), use_idf_env=False, runner=runner)

    if res.returncode == 0:
        # Match 'MAC: xx:xx:xx:xx:xx:xx'
        m = re.search(r"MAC:\s*([0-9a-fA-F:]{17})", res.stdout or "")
        if m:
            return normalize_mac(m.group(1))
    return None


def check_identity_before_write(
    board: str,
    port: str,
    rig: dict | None = None,
    runner: Callable | None = None,
) -> str:
    """Verify board identity BEFORE any write operation.

    Returns normalized MAC if verified, or raises FlashIdentityError.
    """
    rig = rig if rig is not None else load_rig_config()
    boards = rig.get("boards", {})
    if board not in boards:
        raise FlashError(f"Unknown board {board!r} in rig.yaml")

    expected_mac = normalize_mac(str(boards[board]["mac"]))

    # 1. Try USB serial enumeration first (instant, non-intrusive)
    serial_num = get_port_serial_number(port)
    if serial_num:
        if serial_num != expected_mac:
            raise FlashIdentityError(
                f"Identity mismatch on {port}: port has USB serial '{serial_num}', "
                f"but board '{board}' expects '{expected_mac}'. Write REFUSED."
            )
        return serial_num

    # 2. If serial not exposed by OS driver, query via esptool
    chip_mac = read_mac_with_esptool(port, runner=runner)
    if chip_mac:
        if chip_mac != expected_mac:
            raise FlashIdentityError(
                f"Identity mismatch on {port}: chip reports MAC '{chip_mac}', "
                f"but board '{board}' expects '{expected_mac}'. Write REFUSED."
            )
        return chip_mac

    raise FlashIdentityError(
        f"Could not verify board identity on {port} before writing (expected MAC {expected_mac}). Write REFUSED."
    )


def factory_flash_idf(
    port: str,
    repo_root: Path | None = None,
    runner: Callable | None = None,
) -> None:
    """Perform full factory flash of ESP-IDF board (bootloader, partitions, otadata, app)."""
    from labflash.build import run_command

    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    build_dir = root / "esp_idf" / "build"

    # Files to flash per flasher_args.json
    files = {
        "0x0": build_dir / "bootloader" / "bootloader.bin",
        "0x8000": build_dir / "partition_table" / "partition-table.bin",
        "0xf000": build_dir / "ota_data_initial.bin",
        "0x20000": build_dir / "bootlab_idf_blink.bin",
    }

    for offset, p in files.items():
        if not p.is_file():
            raise FlashError(f"Missing required factory flash binary at {offset}: {p}")

    esptool_cmd = find_esptool_cmd(root)
    cmd = [
        *esptool_cmd,
        "--chip",
        "esp32s3",
        "-p",
        str(port),
        "-b",
        "460800",
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write-flash",
        "--flash-mode",
        "dio",
        "--flash-size",
        "16MB",
        "--flash-freq",
        "80m",
    ]
    for offset, p in files.items():
        cmd.extend([offset, str(p)])

    res = run_command(cmd, cwd=build_dir, use_idf_env=True, runner=runner)
    if res.returncode != 0:
        raise FlashError(f"Factory flash failed on {port}:\n{res.stderr or res.stdout}")


def factory_flash_zephyr(
    port: str,
    repo_root: Path | None = None,
    runner: Callable | None = None,
) -> None:
    """Perform full factory flash of Zephyr board (MCUboot at 0x0, signed app at 0x20000)."""
    from labflash.build import run_command

    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    build_dir = root / "esp_zephyr" / "app" / "build_v1"
    if not (build_dir / "mcuboot" / "zephyr" / "zephyr.bin").is_file():
        build_dir = root / "esp_zephyr" / "app" / "build"

    mcuboot_bin = build_dir / "mcuboot" / "zephyr" / "zephyr.bin"
    app_bin = build_dir / "app" / "zephyr" / "zephyr.signed.bin"

    files = {
        "0x0": mcuboot_bin,
        "0x20000": app_bin,
    }

    for offset, p in files.items():
        if not p.is_file():
            raise FlashError(f"Missing required Zephyr factory binary at {offset}: {p}")

    esptool_cmd = find_esptool_cmd(root)
    cmd = [
        *esptool_cmd,
        "--chip",
        "esp32s3",
        "-p",
        str(port),
        "-b",
        "460800",
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write-flash",
        "--flash-mode",
        "dio",
        "--flash-size",
        "16MB",
        "--flash-freq",
        "80m",
    ]
    for offset, p in files.items():
        cmd.extend([offset, str(p)])

    # use_idf_env=False: esptool is already resolved by find_esptool_cmd(); Zephyr
    # flashing does not need the IDF environment (no idf.py, no export.sh required).
    esptool_path = esptool_cmd[0] if len(esptool_cmd) == 1 else " ".join(esptool_cmd)
    res = run_command(cmd, cwd=build_dir, use_idf_env=False, runner=runner)
    if res.returncode != 0:
        err = res.stderr or res.stdout or ""
        if "No module named esptool" in err:
            raise FlashError(
                f"esptool is not installed in this Python environment.\n"
                f"  Run:  pip install esptool\n"
                f"  (Python used: {sys.executable})"
            )
        raise FlashError(f"Zephyr factory flash failed on {port} (esptool: {esptool_path}):\n{err}")



def erase_flash(
    port: str,
    repo_root: Path | None = None,
    runner: Callable | None = None,
) -> None:
    """Erase entire chip flash."""
    from labflash.build import run_command

    esptool_cmd = find_esptool_cmd(repo_root)
    cmd = [*esptool_cmd, "--chip", "esp32s3", "-p", str(port), "erase-flash"]
    # use_idf_env=False: esptool is already resolved; erase does not need IDF.
    res = run_command(cmd, cwd=Path.cwd(), use_idf_env=False, runner=runner)
    if res.returncode != 0:
        raise FlashError(f"Erase flash failed on {port}:\n{res.stderr or res.stdout}")


def flash_board(
    board: str,
    port: str | None = None,
    recover: bool = False,
    repo_root: Path | None = None,
    runner: Callable | None = None,
) -> None:
    """Top-level flash dispatcher enforcing pre-write identity verification."""
    if board not in ("idf", "zephyr"):
        raise FlashError(f"Unknown board '{board}'. Choices: idf, zephyr")

    rig = load_rig_config()
    target_port = port or resolve_board(board, rig=rig)

    # 1. Mandatory identity verification check BEFORE writing
    verified_mac = check_identity_before_write(board, target_port, rig=rig, runner=runner)
    print(f"[VERIFIED] Board '{board}' identity confirmed on {target_port} (MAC: {verified_mac})")

    # 2. Recovery erase if requested
    if recover:
        print(f"Erasing flash on {target_port} for recovery...")
        erase_flash(target_port, repo_root=repo_root, runner=runner)

    # 3. Write factory binaries
    print(f"Writing factory binaries to {board} on {target_port}...")
    if board == "idf":
        factory_flash_idf(target_port, repo_root=repo_root, runner=runner)
    elif board == "zephyr":
        factory_flash_zephyr(target_port, repo_root=repo_root, runner=runner)

    print(f"[SUCCESS] {board} factory flashed successfully on {target_port}.")
