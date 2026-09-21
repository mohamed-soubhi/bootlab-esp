"""Live (real-board) backend for the HIL rig. No mocks, no PowerShell, no hard-coded token.

Runs natively (Windows workstation, later the RPi4): under usbipd/WSL2 the serial port resets the board and
there is no Bluetooth (PLAN R14), so `assert_native_host` refuses instead of silently degrading.
Every operation calls the labflash Python APIs directly and verifies through LABID.
"""
from __future__ import annotations

import contextlib
import io
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from labflash.update import Snapshot

REPO = Path(__file__).resolve().parent.parent
IMAGE_NAME = "bootlab_idf_blink.bin"
VARIANT_DIRS = {
    "v1": "build",
    "v2": "build_v2",
    "no_confirm": "build_no_confirm",
    "hang": "build_hang",
    "bad_sig": "build_bad_sig",
}
OK_MARKER = "UPDATE OK"


class LiveRigError(RuntimeError):
    """The live rig cannot run honestly (wrong host, missing image...). Never converted into a pass."""


def assert_native_host(proc_version: str | None = None) -> None:
    if proc_version is None:
        try:
            proc_version = Path("/proc/version").read_text()
        except OSError:
            return
    if "microsoft" in proc_version.lower():
        raise LiveRigError("live HIL must run natively (Windows python or the RPi4), not under WSL2 (R14: "
                           "serial open resets the board, no Bluetooth). Use --mock-rig only for simulation.")


def _default_snapshot_fn(port: str) -> Callable[[], Snapshot]:
    from labflash.update_cli import labid_snapshot_fn
    return labid_snapshot_fn(port)


def _default_measure_fn(port: str) -> Callable[[float, float | None, int], tuple[int, float, bool]]:
    def measure(duration_s: float, expect_hz: float | None, tol: int) -> tuple[int, float, bool]:
        from labflash.identify import SerialLineTransport, measure as _measure
        tr = SerialLineTransport(port)
        try:
            return _measure(tr, duration_s, expect_hz, tol)
        finally:
            tr.close()
    return measure


@dataclass
class LiveBackend:
    board: str
    port: str
    board_ip: str
    images_dir: Path
    keys_dir: Path | None
    env_file: str | None
    rig_path: str | None
    snapshot_fn: Callable[[], Snapshot]
    update_fn: Callable[[Namespace], int]
    measure_fn: Callable[[float, float | None, int], tuple[int, float, bool]]
    timeout_s: float = 240.0

    @classmethod
    def create(cls, port: str, board_ip: str, images_dir: Path | None = None, keys_dir: Path | None = None,
               env_file: str | None = None, rig_path: str | None = None, board: str = "idf") -> "LiveBackend":
        assert_native_host()
        from labflash.update_cli import run_update
        return cls(board=board, port=port, board_ip=board_ip, images_dir=images_dir or REPO / "esp_idf",
                   keys_dir=keys_dir, env_file=env_file, rig_path=rig_path,
                   snapshot_fn=_default_snapshot_fn(port), update_fn=run_update, measure_fn=_default_measure_fn(port))

    def image_for(self, variant: str) -> Path:
        d = VARIANT_DIRS.get(variant)
        if d is None:
            raise LiveRigError(f"unknown variant {variant!r}")
        p = self.images_dir / d / IMAGE_NAME
        if not p.is_file():
            raise LiveRigError(f"image for {variant} not found: {p}")
        return p

    def snapshot(self) -> Snapshot:
        return self.snapshot_fn()

    def labid_info(self) -> dict[str, str]:
        s = self.snapshot()
        return {"board": self.board, "v": s.app, "slot": str(s.slot), "confirmed": "1" if s.confirmed else "0",
                "uid": s.uid or ""}

    def measure(self, duration_s: float, expect_hz: float | None, tolerance: int) -> tuple[float, bool]:
        _, hz, passed = self.measure_fn(duration_s, expect_hz, tolerance)
        return hz, passed

    def update(self, variant: str, transport: str, log_path: Path) -> bool:
        image = self.image_for(variant)
        args = Namespace(
            board=self.board, image=str(image), transport=transport, labid_port=self.port, no_labid=False,
            board_mac=None, address=None, scan_timeout=10.0, board_ip=self.board_ip, host_ip=None, http_port=8443,
            keys=str(self.keys_dir) if self.keys_dir else None, ca_cert=None, server_cert=None, server_key=None,
            token=None, env_file=self.env_file or "credentials.env", rig=self.rig_path, timeout=self.timeout_s)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.update_fn(args)
        out = buf.getvalue()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"--- update {variant} via {transport} rc={rc}\n{out}\n")
        return rc == 0 and OK_MARKER in out

    def reset_to_v1(self, log_path: Path, transport: str = "wifi") -> bool:
        s = self.snapshot()
        if s.app.startswith("1.") and s.confirmed:
            return True
        if not self.update("v1", transport, log_path):
            return False
        s = self.snapshot()
        return s.app.startswith("1.") and s.confirmed
