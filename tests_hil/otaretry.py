"""Send an image with bounded retries for HOST-side trouble (BL-069 AC5 / BL-067 runners).

A live run found that after a long WiFi session on Windows an update could fail within seconds with a PermissionError on
its temp file, or the board could accept the trigger and never pull the image. Neither says anything about the board, so
retrying is right, but only while the board's state is unchanged: a retry after a half-applied update would double-install.
"""
from __future__ import annotations

import re
import time
import traceback
from collections.abc import Callable
from pathlib import Path

INFRA_RETRIES = 3
BACKOFF_S = 20.0


def log_since(log_path: Path | None, offset: int) -> str:
    return log_path.read_bytes()[offset:].decode("utf-8", errors="replace") if log_path is not None and log_path.is_file() else ""


def log_size(log_path: Path | None) -> int:
    return log_path.stat().st_size if log_path is not None and log_path.is_file() else 0


def transfer_seen(log_text: str, transport: str) -> bool:
    """Was the WHOLE image delivered? WiFi: the host served every byte; BLE: the last sector sent is the last one."""
    if transport == "wifi":
        served = re.search(r"host served: \{[^}]*:\s*(\d+)\}\s*\(image was (\d+) bytes\)", log_text)
        return bool(served) and int(served.group(1)) == int(served.group(2)) > 0
    sectors = re.findall(r"BLE: sector (\d+)/(\d+)", log_text)
    return bool(sectors) and sectors[-1][0] == sectors[-1][1]


def send_with_retry(backend, path: Path, transport: str, log_path: Path, timeout_s: float | None,
                    retries: int = INFRA_RETRIES, backoff_s: float = BACKOFF_S,
                    sleep_fn: Callable[[float], None] = time.sleep) -> tuple[bool, str, int]:
    """(ok, cause, retries_used). Retries only when the failure was host-side and the board did not change."""
    try:
        pre = backend.snapshot()
    except Exception:  # noqa: BLE001 - no baseline to protect: send once, the caller records the outcome
        pre = None
    used = 0
    while True:
        offset = log_size(log_path)
        try:
            ok, cause = bool(backend.update_image_path(path, transport, log_path, timeout_s)), ""
        except Exception as err:  # noqa: BLE001 - a failing send must be recorded, not crash the run
            ok, cause = False, f"update raised {type(err).__name__}: {err}"
            with log_path.open("a", encoding="utf-8") as f:                 # keep the stack: it names the locked file operation
                f.write("--- host-side exception\n" + "".join(traceback.format_exception(err)))
        host_side = bool(cause) or (not ok and not transfer_seen(log_since(log_path, offset), transport))
        if not host_side or used >= retries or pre is None:
            return ok, cause, used
        try:
            now = backend.snapshot()
        except Exception:  # noqa: BLE001
            return ok, cause, used
        if (now.app, now.slot, now.confirmed) != (pre.app, pre.slot, pre.confirmed):
            return ok, cause, used                       # the update did something: never retry on top of it
        used += 1
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"--- retry {used}/{retries} after host-side trouble ({cause or 'image never reached the board'}); "
                    f"waiting {backoff_s:.0f} s\n")
        sleep_fn(backoff_s)


SNAPSHOT_ATTEMPTS = 6
SNAPSHOT_WAIT_S = 5.0


def snapshot_with_retry(backend, attempts: int = SNAPSHOT_ATTEMPTS, wait_s: float = SNAPSHOT_WAIT_S,
                        sleep_fn: Callable[[float], None] = time.sleep):
    """backend.snapshot(), riding out a re-enumerating USB port (Windows briefly refuses to reopen COM after a reboot)."""
    for attempt in range(attempts):
        try:
            return backend.snapshot()
        except Exception:
            if attempt == attempts - 1:
                raise
            sleep_fn(wait_s)
    raise AssertionError("unreachable")
