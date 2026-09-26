"""Hardware-free tests for the cross-process file lock (BL-072). Owner: Claude."""
from __future__ import annotations

import multiprocessing
import time

import pytest

from tests_hil.filelock import LockTimeout, file_lock


def _hold(path, ready, release):
    with file_lock(path):
        ready.set()
        release.wait(20)


def test_a_free_lock_is_taken_immediately(tmp_path):
    with file_lock(tmp_path / "ble.lock") as waited:
        assert waited < 0.5


def test_the_lock_is_reusable_after_release(tmp_path):
    for _ in range(3):
        with file_lock(tmp_path / "ble.lock"):
            pass


def test_a_second_process_waits_and_then_times_out(tmp_path):
    path = tmp_path / "ble.lock"
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold, args=(path, ready, release))
    holder.start()
    try:
        assert ready.wait(20)
        slept = []
        clock = iter(range(1000)).__next__
        with pytest.raises(LockTimeout), file_lock(path, timeout_s=3, poll_s=1, sleep_fn=slept.append, clock=lambda: float(clock())):
            pass
        assert slept                                       # it polled instead of failing at once
    finally:
        release.set()
        holder.join(20)


def test_the_waiter_gets_the_lock_when_the_holder_lets_go(tmp_path):
    path = tmp_path / "ble.lock"
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold, args=(path, ready, release))
    holder.start()
    try:
        assert ready.wait(20)
        release.set()
        start = time.monotonic()
        with file_lock(path, timeout_s=20, poll_s=0.1) as waited:
            assert waited < 20
        assert time.monotonic() - start < 20
    finally:
        release.set()
        holder.join(20)
