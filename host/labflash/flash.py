"""labflash flash / recover — USB factory flash and recovery with pre-write identity checks (BL-042).

Strict Guardrail:
- BEFORE ANY FLASH OR RECOVERY WRITE, the device identity (MAC / USB serial)
  is verified against rig.yaml. If there is a mismatch (or wrong board requested),
  the tool refuses to write and exits with FlashIdentityError.
- Flashing Zephyr is gated behind BL-063b per replan.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import serial.tools.list_ports as list_ports

from labflash.core import BoardResolutionError, load_rig_config, resolve_board

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]


class FlashError(RuntimeError):
    """Base error for flashing operations."""


class FlashIdentityError(FlashError):
    """Raised when board identity does not match expectation before write."""


class ZephyrGatedError(FlashError):
    """Raised when attempting to flash Zephyr while gated."""


def normalize_mac(mac: str) -> str:
    """Normalize MAC or serial number to lowercase hex without delimiters."""
    return re.sub(r"[^0-9a-fA-F]", "", mac).lower()


def get_port_serial_number(port: str) -> str | None:
    """Read USB serial number from pySerial list_ports."""
    for p in list_ports.comports():
        if p.device == port or Path(p.device).resolve() == Path(port).resolve():
            if p.serial_number:
                return normalize_mac(p.serial_number)
    return None


def read_mac_with_esptool(
    port: str,
    runner: Callable | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Query MAC directly from chip using esptool read-mac."""
    from labflash.build import find_idf_export_script, run_command

    cmd = ["esptool", "--port", str(port), "read-mac"]
    res = run_command(cmd, cwd=Path.cwd(), use_idf_env=True, runner=runner)
    if res.returncode != 0:
        # Try read_mac (legacy syntax)
        cmd_legacy = ["esptool.py", "--port", str(port), "read_mac"]
        res = run_command(cmd_legacy, cwd=Path.cwd(), use_idf_env=True, runner=runner)

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

    cmd = [
        "esptool",
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


def erase_flash(
    port: str,
    runner: Callable | None = None,
) -> None:
    """Erase entire chip flash."""
    from labflash.build import run_command

    cmd = ["esptool", "--chip", "esp32s3", "-p", str(port), "erase-flash"]
    res = run_command(cmd, cwd=Path.cwd(), use_idf_env=True, runner=runner)
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
    if board == "zephyr":
        raise ZephyrGatedError(
            "Zephyr track is on hold pending BL-063b per replan (2026-09-21)."
        )

    if board != "idf":
        raise FlashError(f"Unknown board '{board}'. Choices: idf")

    rig = load_rig_config()
    target_port = port or resolve_board(board, rig=rig)

    # 1. Mandatory identity verification check BEFORE writing
    verified_mac = check_identity_before_write(board, target_port, rig=rig, runner=runner)
    print(f"[VERIFIED] Board '{board}' identity confirmed on {target_port} (MAC: {verified_mac})")

    # 2. Recovery erase if requested
    if recover:
        print(f"Erasing flash on {target_port} for recovery...")
        erase_flash(target_port, runner=runner)

    # 3. Write factory binaries
    print(f"Writing factory binaries to {board} on {target_port}...")
    factory_flash_idf(target_port, repo_root=repo_root, runner=runner)
    print(f"[SUCCESS] {board} factory flashed successfully on {target_port}.")
