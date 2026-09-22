"""Persistent, shared serial console for the board's UART/USB-Serial-JTAG port (BL-060 follow-up).

LABID and the board's ESP_LOG boot/OTA console output share ONE physical serial port. Windows
opens a COM port exclusively, so a LABID query (`SerialLineTransport`) and a separate console
watcher (`scripts/serial_watch.py`) cannot both hold it at once -- the second open fails with
"Access is denied". Every LABID transport used so far also opened and closed the port per query,
so nothing was listening -- and console bytes were dropped -- during the gaps between queries,
including exactly the moments (esp_ota_end, bootloader slot switch) BL-060 needs to see.

`SharedConsolePort` opens the port ONCE and keeps it open for the life of a test/soak run. A
background thread continuously drains bytes into (a) a timestamped console.log and (b) an
in-memory queue that a Transport-compatible `read1()`/`write()` adapter drains, so existing LABID
query code (labflash.identify) keeps working unmodified against the SAME open handle instead of
racing a second one.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path


class SharedConsolePort:
    """Transport-compatible (read1/write/close) wrapper around one persistently-open serial port.

    `close()` is intentionally a no-op: existing LABID call sites (labflash.identify, LiveBackend)
    call `tr.close()` after every query and must not tear down the shared connection early. Call
    `shutdown()` once, when the whole test/soak run is done, to actually stop the reader thread and
    release the port.
    """

    def __init__(self, port: str, baudrate: int = 115200, console_log: Path | None = None):
        import serial

        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = 0.05
        ser.write_timeout = 1.0
        ser.dtr = False   # inactive before open so opening does not toggle the reset/boot lines (R14)
        ser.rts = False
        ser.open()
        self._ser = ser
        self._byte_q: queue.Queue[bytes] = queue.Queue()
        self._write_lock = threading.Lock()
        self._line_buf = bytearray()
        self._console_fh = console_log.open("a", encoding="utf-8") if console_log else None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader_loop, name=f"console-tap-{port}", daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(self._ser.in_waiting or 1)
            except Exception:  # noqa: BLE001 - port went away (reset/replug/shutdown); stop quietly
                break
            if not chunk:
                continue
            for b in chunk:
                self._byte_q.put(bytes([b]))
            self._tee(chunk)

    def _tee(self, chunk: bytes) -> None:
        if self._console_fh is None:
            return
        self._line_buf.extend(chunk)
        while b"\n" in self._line_buf:
            line, _, rest = self._line_buf.partition(b"\n")
            self._line_buf = bytearray(rest)
            now = time.time()
            ts = time.strftime("%H:%M:%S", time.localtime(now))
            self._console_fh.write(f"[{ts}.{int(now * 1000) % 1000:03d}] {line.decode('utf-8', errors='replace')}\n")
        self._console_fh.flush()

    # --- Transport protocol (labflash.identify.Transport): read1()/write()/close() ---

    def read1(self) -> bytes:
        try:
            return self._byte_q.get_nowait()
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> None:
        with self._write_lock:
            self._ser.write(data)
            self._ser.flush()

    def close(self) -> None:
        """No-op: see class docstring. Use `shutdown()` to actually release the port."""

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        try:
            self._ser.close()
        finally:
            if self._console_fh is not None:
                self._console_fh.close()
