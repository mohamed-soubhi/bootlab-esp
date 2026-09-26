"""A cross-process advisory lock on a file, for serializing use of a shared resource (BL-072: one BLE adapter, two boards).

Windows uses msvcrt byte-range locking, POSIX uses flock; both are released automatically if the holder dies.
"""
from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path


class LockTimeout(RuntimeError):
    """The lock stayed held by another process for longer than the timeout."""


def _try_lock(fd: int) -> bool:
    if os.name == "nt":
        import msvcrt
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)      # type: ignore[attr-defined,unused-ignore]
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        with contextlib.suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)      # type: ignore[attr-defined,unused-ignore]
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(path: Path, timeout_s: float | None = 1800.0, poll_s: float = 1.0,
              sleep_fn: Callable[[float], None] = time.sleep,
              clock: Callable[[], float] = time.monotonic) -> Iterator[float]:
    """Hold an exclusive lock on `path` (created if missing); yields the seconds spent waiting for it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        if os.name == "nt" and os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")                          # msvcrt locks a byte range, so the file needs a byte
        start = clock()
        while not _try_lock(fd):
            if timeout_s is not None and clock() - start >= timeout_s:
                raise LockTimeout(f"{path} is still held by another process after {timeout_s:.0f} s")
            sleep_fn(poll_s)
        waited = clock() - start
        try:
            yield waited
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
