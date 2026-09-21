"""labflash core — rig config loading and board resolution (BL-040).

Boards are identified by USB serial (== the ESP32-S3's own MAC), never by
port name / ttyACMx index, which the OS reassigns on every enumeration
(replug, port swap, or re-enumeration after a reset). Every resolution
re-scans live devices from scratch — nothing is cached across calls, so a
stale device path is never returned.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml
from serial.tools import list_ports

DEFAULT_RIG_PATH = Path(__file__).resolve().parents[1] / "config" / "rig.yaml"
DEFAULT_WAIT_S = 5.0
POLL_INTERVAL_S = 0.2


class BoardResolutionError(RuntimeError):
    """Raised when a configured board cannot be resolved to a live device."""


def load_rig_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path is not None else DEFAULT_RIG_PATH
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not cfg or "boards" not in cfg:
        raise BoardResolutionError(f"rig config at {path} has no 'boards' section")
    return cfg


def _live_serials() -> dict[str, str]:
    """Live USB serial -> device path, freshly enumerated every call."""
    out = {}
    for p in list_ports.comports():
        if p.serial_number:
            out[p.serial_number.upper()] = p.device
    return out


def resolve_board(board_key: str, rig: dict | None = None, wait_s: float = DEFAULT_WAIT_S) -> str:
    """Resolve one board's device path by its configured USB serial.

    Polls live enumeration for up to `wait_s` (default 5s, covering
    re-enumeration after a board reset) — never returns a memoized path,
    so it can't reuse a stale ttyACMx once the OS reassigns it. Raises
    BoardResolutionError with a clear, actionable message if the board's
    configured serial never appears within the window (covers both a
    genuinely missing board and a swapped board that isn't the one
    expected under this key — either way, an unrecognized/absent serial
    is reported plainly rather than silently returning the wrong port).
    """
    rig = rig if rig is not None else load_rig_config()
    boards = rig.get("boards", {})
    if board_key not in boards:
        raise BoardResolutionError(f"unknown board key {board_key!r} (not in rig.yaml)")
    expected_serial = str(boards[board_key]["usb_serial"]).upper()

    deadline = time.monotonic() + wait_s
    while True:
        live = _live_serials()
        if expected_serial in live:
            return live[expected_serial]
        if time.monotonic() >= deadline:
            present = ", ".join(sorted(live)) or "none"
            raise BoardResolutionError(
                f"board {board_key!r} (expected USB serial {expected_serial}) "
                f"not found after {wait_s:.1f}s. Devices present: {present}"
            )
        time.sleep(POLL_INTERVAL_S)


def resolve_all_boards(rig: dict | None = None, wait_s: float = DEFAULT_WAIT_S) -> dict[str, str]:
    """Resolve every board listed in rig.yaml.

    Raises BoardResolutionError (from resolve_board) on the first board
    that can't be resolved, naming which board and what was actually
    found on the bus.
    """
    rig = rig if rig is not None else load_rig_config()
    return {key: resolve_board(key, rig=rig, wait_s=wait_s) for key in rig.get("boards", {})}
