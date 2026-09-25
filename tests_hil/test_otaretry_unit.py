"""Hardware-free tests for the host-side retry wrapper (BL-069 AC5 / BL-067 runners). Owner: Claude."""
from __future__ import annotations

from pathlib import Path

import pytest
from labflash.update import Snapshot

from tests_hil import otaretry as ot

FULL_WIFI = "host served: {'update.bin': 1234} (image was 1234 bytes)\n"


class Board:
    """`script` is a list of behaviours, one per update call: 'ok', 'raise', 'nopull', 'partial', 'applied_then_raise'."""

    def __init__(self, script):
        self.script, self.calls = list(script), 0
        self.app, self.slot = "1.0.0", 0

    def snapshot(self):
        return Snapshot(self.app, self.slot, True, "U", "labid")

    def update_image_path(self, path, transport, log_path, timeout_s=None):
        step = self.script[self.calls] if self.calls < len(self.script) else "ok"
        self.calls += 1
        with log_path.open("a") as f:
            if step in ("ok", "applied_then_raise"):
                f.write(FULL_WIFI)
            elif step == "nopull":
                f.write("host served: {} (image was 1234 bytes)\n")
            elif step == "partial":
                f.write("host served: {'update.bin': 10} (image was 1234 bytes)\n")
        if step == "raise":
            raise PermissionError("[WinError 32] file in use")
        if step == "applied_then_raise":
            self.app, self.slot = "2.0.0", 1
            raise PermissionError("[WinError 32] file in use during cleanup")
        if step == "ok":
            self.app, self.slot = "2.0.0", 1
            return True
        return False


def _send(board, tmp_path, retries=3, sleeps=None):
    return ot.send_with_retry(board, Path("x.bin"), "wifi", tmp_path / "u.log", 60, retries=retries, backoff_s=7,
                              sleep_fn=(sleeps if sleeps is not None else []).append)


def test_a_clean_send_is_not_retried(tmp_path):
    b = Board(["ok"])
    assert _send(b, tmp_path) == (True, "", 0) and b.calls == 1


@pytest.mark.parametrize("bad", ["raise", "nopull"])
def test_host_side_trouble_is_retried_with_a_backoff_until_it_works(tmp_path, bad):
    b, sleeps = Board([bad, bad, "ok"]), []
    ok, cause, used = _send(b, tmp_path, sleeps=sleeps)
    assert ok and cause == "" and used == 2 and b.calls == 3 and sleeps == [7, 7]
    assert "retry 1/3" in (tmp_path / "u.log").read_text()


def test_retries_are_bounded(tmp_path):
    b = Board(["raise"] * 10)
    ok, cause, used = _send(b, tmp_path, retries=2)
    assert not ok and "PermissionError" in cause and used == 2 and b.calls == 3


def test_a_failure_that_did_transfer_the_whole_image_is_not_host_side(tmp_path):
    b = Board(["ok"])
    b.script = ["ok"]
    log = tmp_path / "u.log"

    def rejected_after_full_transfer(*a, **k):
        with log.open("a") as f:
            f.write(FULL_WIFI)
        return False
    b.update_image_path = rejected_after_full_transfer
    ok, cause, used = _send(b, tmp_path)
    assert (ok, cause, used) == (False, "", 0)


def test_a_partial_transfer_counts_as_never_delivered_and_is_retried(tmp_path):
    b = Board(["partial", "ok"])
    assert _send(b, tmp_path)[2] == 1


def test_never_retries_on_top_of_a_board_that_changed(tmp_path):
    b = Board(["applied_then_raise", "ok"])
    ok, cause, used = _send(b, tmp_path)
    assert not ok and "PermissionError" in cause and used == 0 and b.calls == 1        # the update took effect; do not repeat it


def test_transfer_evidence_parsing():
    assert ot.transfer_seen("host served: {'update.bin': 10} (image was 10 bytes)", "wifi")
    assert not ot.transfer_seen("host served: {'update.bin': 4} (image was 10 bytes)", "wifi")
    assert not ot.transfer_seen("host served: {} (image was 10 bytes)", "wifi")
    assert ot.transfer_seen("  BLE: sector 1/300\n  BLE: sector 300/300", "ble")
    assert not ot.transfer_seen("  BLE: sector 3/300", "ble")
    assert not ot.transfer_seen("BLE OTA failed: no device", "ble")
