"""Live (real-board) backend for the HIL rig. No mocks, no PowerShell, no hard-coded token.

Runs natively (Windows workstation, later the RPi4): under usbipd/WSL2 the serial port resets the board and
there is no Bluetooth (PLAN R14), so `assert_native_host` refuses instead of silently degrading.
Every operation calls the labflash Python APIs directly and verifies through LABID.
"""
from __future__ import annotations

import contextlib
import io
import time
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from labflash.update import Snapshot, read_app_version

REPO = Path(__file__).resolve().parent.parent
IMAGE_NAME = "bootlab_idf_blink.bin"
VARIANT_DIRS = {
    "v1": "build",
    "v2": "build_v2",
    "v3": "build_v3",
    "v4": "build_v4",
    "no_confirm": "build_no_confirm",
    "hang": "build_hang",
    "bad_sig": "build_bad_sig",
}
OK_MARKER = "UPDATE OK"


def _is_v1(app: str) -> bool:
    """A v1 release ("1.x.y"); the failure images ("1.0.0-hang", "-badsig", "-noconfirm") are NOT v1."""
    return app.startswith("1.") and "-" not in app


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


def _default_snapshot_fn(port: str, transport_factory: Callable[[], object] | None = None) -> Callable[[], Snapshot]:
    from labflash.update_cli import labid_snapshot_fn
    return labid_snapshot_fn(port, transport_factory)


def _default_measure_fn(
    port: str, transport_factory: Callable[[], object] | None = None
) -> Callable[[float, float | None, int], tuple[int, float, bool]]:
    def measure(duration_s: float, expect_hz: float | None, tol: int) -> tuple[int, float, bool]:
        from labflash.identify import SerialLineTransport
        from labflash.identify import measure as _measure
        tr = transport_factory() if transport_factory else SerialLineTransport(port)
        try:
            return _measure(tr, duration_s, expect_hz, tol)
        finally:
            tr.close()
    return measure


def hard_reset(port: str, serial_factory=None, sleep=None, hold_s: float = 0.1) -> None:
    """Restart the chip into the APPLICATION via the USB-Serial/JTAG DTR/RTS transitions (esptool-style):
    (DTR=1,RTS=0) -> (DTR=0,RTS=1) resets with IO0 released -> (0,0). A plain RTS pulse does NOT reset this port
    (proved on hardware: uptime kept counting). The port drops ~600 ms; the caller re-polls the board."""
    import time as _time
    sleep = sleep or _time.sleep
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    ser = serial_factory()
    ser.port = port
    ser.dtr = False   # inactive before open so opening does not toggle the lines (R14)
    ser.rts = False
    ser.open()
    try:
        ser.dtr, ser.rts = True, False
        sleep(hold_s)
        ser.dtr, ser.rts = False, True
        sleep(hold_s)
        ser.dtr, ser.rts = False, False
        sleep(hold_s / 2)
    finally:
        ser.close()


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
    transport_factory: Callable[[], object] | None = None
    console_port: object | None = None   # SharedConsolePort, when console_log was passed to create()

    @classmethod
    def create(cls, port: str, board_ip: str, images_dir: Path | None = None, keys_dir: Path | None = None,
               env_file: str | None = None, rig_path: str | None = None, board: str = "idf",
               console_log: Path | None = None) -> LiveBackend:
        """`console_log`, when given, opens ONE persistent SharedConsolePort for the whole backend's
        life (BL-060 follow-up): every LABID query and the board's raw ESP_LOG console output share
        it, so console.log captures continuously instead of only during brief per-query opens. Call
        `shutdown()` when done with the backend to release the port."""
        assert_native_host()
        from labflash.update_cli import run_update
        console_port = None
        transport_factory = None
        if console_log is not None:
            from labflash.serial_console import SharedConsolePort
            console_port = SharedConsolePort(port, console_log=console_log)
            def transport_factory() -> object:
                return console_port
        if images_dir is None:
            images_dir = REPO / "esp_zephyr" / "app" if board == "zephyr" else REPO / "esp_idf"
        return cls(board=board, port=port, board_ip=board_ip, images_dir=images_dir,
                   keys_dir=keys_dir, env_file=env_file, rig_path=rig_path,
                   snapshot_fn=_default_snapshot_fn(port, transport_factory), update_fn=run_update,
                   measure_fn=_default_measure_fn(port, transport_factory),
                   transport_factory=transport_factory, console_port=console_port)

    def shutdown(self) -> None:
        """Release the shared console port, if `console_log` was passed to `create()`. Call once, at
        the very end of a run -- not after each query (existing call sites already call `.close()`
        per query, which is a no-op on the shared port; see SharedConsolePort)."""
        if self.console_port is not None:
            self.console_port.shutdown()

    def image_for(self, variant: str) -> Path:
        d = VARIANT_DIRS.get(variant)
        if d is None:
            raise LiveRigError(f"unknown variant {variant!r}")
        if self.board == "zephyr":
            # Zephyr's real convention is build_<variant> uniformly (build_v1, build_v2, build_hang, ...);
            # VARIANT_DIRS["v1"] = "build" is IDF's convention leaking in via the shared dict and points at
            # a stale pre-BLE/WiFi build (BL-064). Prefer build_<variant> first.
            variant_d = f"build_{variant}"
            candidates = [
                self.images_dir / variant_d / "app" / "zephyr" / "zephyr.signed.bin",
                self.images_dir / d / "app" / "zephyr" / "zephyr.signed.bin",
                self.images_dir / d / "zephyr.signed.bin",
                REPO / "esp_zephyr" / "app" / variant_d / "app" / "zephyr" / "zephyr.signed.bin",
                REPO / "esp_zephyr" / "app" / d / "app" / "zephyr" / "zephyr.signed.bin",
            ]
            for p in candidates:
                if p.is_file():
                    return p
            raise LiveRigError(f"zephyr image for {variant} not found in candidates: {candidates}")
        p = self.images_dir / d / IMAGE_NAME
        if not p.is_file():
            raise LiveRigError(f"image for {variant} not found: {p}")
        return p

    def reset(self) -> None:
        hard_reset(self.port)

    def wait_snapshot(self, wanted: Callable[[Snapshot], bool], timeout_s: float = 60.0, poll_s: float = 2.0,
                      sleep_fn: Callable[[float], None] | None = None) -> Snapshot | None:
        """Poll LABID until `wanted`; a rebooting board (port gone, no answer) is not an error."""
        import time as _time
        sleep_fn = sleep_fn or _time.sleep
        last = None
        for _ in range(max(1, int(timeout_s / poll_s) + 1)):
            try:
                last = self.snapshot_fn()
            except Exception:  # noqa: S110, BLE001 - mid-reboot
                pass
            else:
                if wanted(last):
                    return last
            sleep_fn(poll_s)
        return None

    def _transport(self):
        if self.transport_factory is not None:
            return self.transport_factory()
        from labflash.identify import SerialLineTransport
        return SerialLineTransport(self.port)

    def identify_fields(self) -> dict:
        from labflash.identify import identify
        tr = self._transport()
        try:
            return identify(tr)
        finally:
            tr.close()

    def stress(self, n: int) -> tuple[int, int]:
        """n consecutive VER? on ONE connection; returns (well-formed answers, n)."""
        from labflash.identify import get_version
        tr = self._transport()
        ok = 0
        try:
            for _ in range(n):
                try:
                    if get_version(tr).get("app"):
                        ok += 1
                except Exception:  # noqa: S110, BLE001 - counted as a failure
                    pass
        finally:
            tr.close()
        return ok, n

    def abuse_framing(self) -> dict:
        """Send bad-CRC, oversize and garbage lines to the real device; report whether it stayed up and sane."""
        from labflash.identify import _read_frame, get_state, get_version, identify
        tr = self._transport()
        try:
            up0 = int(get_state(tr)["uptime_ms"])
            tr.write(b"$LAB,ID?*0000\n")
            tr.write(b"$LAB,ID?," + b"a" * 300 + b"\n")
            tr.write(b"\xff\x00garbage!!\n")
            errs: list[str] = []
            deadline = time.monotonic() + 1.5   # the device answers junk with ERR frames; collect, do not misread them
            while time.monotonic() < deadline:
                frame = _read_frame(tr, deadline)
                if frame and frame[0] == "ERR":
                    errs.append(frame[1].get("code", "?"))
            up1 = int(get_state(tr)["uptime_ms"])
            return {"uptime_before": up0, "uptime_after": up1, "no_reset": up1 > up0, "err_codes": errs,
                    "version_ok": bool(get_version(tr).get("app")), "uid": identify(tr).get("uid")}
        finally:
            tr.close()

    def snapshot(self) -> Snapshot:
        return self.snapshot_fn()

    def labid_info(self) -> dict[str, str]:
        s = self.snapshot()
        return {"board": self.board, "v": s.app, "slot": str(s.slot), "confirmed": "1" if s.confirmed else "0",
                "uid": s.uid or ""}

    def measure(self, duration_s: float, expect_hz: float | None, tolerance: int) -> tuple[float, bool]:
        _, hz, passed = self.measure_fn(duration_s, expect_hz, tolerance)
        return hz, passed

    def update(self, variant: str, transport: str, log_path: Path, timeout_s: float | None = None) -> bool:
        return self.update_image_path(self.image_for(variant), transport, log_path, timeout_s, label=variant)

    def update_image_path(self, image: Path, transport: str, log_path: Path, timeout_s: float | None = None,
                          label: str | None = None) -> bool:
        """Install the image at `image` (any signed file, e.g. a BL-069 pool image) via `transport`."""
        variant = label or image.name
        args = Namespace(
            board=self.board, image=str(image), transport=transport, labid_port=self.port, no_labid=False,
            board_mac=None, address=None, scan_timeout=10.0, board_ip=self.board_ip, host_ip=None, http_port=8443,
            udp_port=1337, confirm_timeout=30.0,
            keys=str(self.keys_dir) if self.keys_dir else None, ca_cert=None, server_cert=None, server_key=None,
            token=None, env_file=self.env_file or "credentials.env", rig=self.rig_path, timeout=timeout_s or self.timeout_s)
        args.transport_factory = self.transport_factory   # shares the SharedConsolePort, if one is open (BL-060)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.update_fn(args)
        out = buf.getvalue()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"--- update {variant} via {transport} rc={rc}\n{out}\n")
        return rc == 0 and OK_MARKER in out

    def interrupted_transfer(self, variant: str, fraction: float = 0.5, settle_s: float = 20.0) -> dict:
        """WiFi OTA whose image server cuts the connection after `fraction` of the bytes (T08 driver).
        Returns what really happened; the caller asserts the board discarded the partial image."""
        import shutil
        import tempfile

        from labflash.idf_wifi_ota import OtaServer, WifiBoard
        from labflash.update_cli import DEFAULT_KEYS, guess_host_ip, read_token
        image = self.image_for(variant)
        size = image.stat().st_size
        keys = self.keys_dir or DEFAULT_KEYS
        board = WifiBoard(self.board_ip, read_token(self.env_file, None), keys / "ca.pem")
        with tempfile.TemporaryDirectory(prefix="labflash-t08-") as d:
            shutil.copy(image, Path(d) / "update.bin")
            server = OtaServer(d, 8443, keys / "server_cert.pem", keys / "server_key.pem",
                               abort_after_bytes=int(size * fraction)).start()
            try:
                status = board.trigger(f"https://{guess_host_ip(self.board_ip)}:{server.port}/update.bin",
                                       read_app_version(image.read_bytes()))
                deadline = time.monotonic() + settle_s
                while time.monotonic() < deadline and server.aborted == 0:
                    time.sleep(0.5)
                time.sleep(settle_s)   # let the board notice the short body and abandon the download
                return {"trigger_status": status, "image_bytes": size, "served": dict(server.served),
                        "aborted": server.aborted}
            finally:
                server.stop()

    def reset_to_v1(self, log_path: Path, transport: str | None = None) -> bool:
        if transport is None:
            transport = "udp" if self.board == "zephyr" else "wifi"
        s = self.snapshot()
        if _is_v1(s.app) and s.confirmed:
            return True
        if not self.update("v1", transport, log_path):
            return False
        s = self.snapshot()
        return _is_v1(s.app) and s.confirmed
