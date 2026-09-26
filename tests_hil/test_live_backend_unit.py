"""Hardware-free tests for the HIL live backend (injected fakes). Live behaviour is proven on the board, not here."""
from __future__ import annotations

from pathlib import Path

import pytest
from labflash.update import Snapshot

from tests_hil.live_backend import (
    VARIANT_DIRS,
    LiveBackend,
    LiveRigError,
    assert_native_host,
)


def snap(app="1.0.0", slot=0, confirmed=True):
    return Snapshot(app=app, slot=slot, confirmed=confirmed, uid="E072A1AA2390", source="labid")


def make(tmp_path, snapshots, rc=0, out="UPDATE OK\n"):
    calls = []
    it = iter(snapshots)

    def update_fn(args):
        calls.append(args)
        print(out, end="")
        return rc

    images = tmp_path / "images"
    for d in VARIANT_DIRS.values():
        (images / d).mkdir(parents=True)
        (images / d / "bootlab_idf_blink.bin").write_bytes(b"x")
    be = LiveBackend(board="idf", port="COM14", board_ip="1.2.3.4", images_dir=images, keys_dir=tmp_path,
                     env_file=None, rig_path=None, snapshot_fn=lambda: next(it), update_fn=update_fn,
                     measure_fn=lambda d, e, t: (10, 1.0, True))
    return be, calls


def test_update_passes_real_image_and_no_hardcoded_token(tmp_path):
    be, calls = make(tmp_path, [])
    assert be.update("v2", "wifi", tmp_path / "u.log") is True
    a = calls[0]
    assert Path(a.image).parts[-2:] == ("build_v2", "bootlab_idf_blink.bin") and a.transport == "wifi"
    assert a.token is None and a.board_ip == "1.2.3.4" and a.labid_port == "COM14"
    assert "UPDATE OK" in (tmp_path / "u.log").read_text()


def test_update_false_when_cli_fails(tmp_path):
    be, _ = make(tmp_path, [], rc=1, out="UPDATE FAILED\n")
    assert be.update("v1", "ble", tmp_path / "u.log") is False


def test_update_false_when_rc0_but_no_ok_marker(tmp_path):
    be, _ = make(tmp_path, [], rc=0, out="nothing\n")
    assert be.update("v1", "ble", tmp_path / "u.log") is False


def test_missing_image_is_an_error_not_a_silent_false(tmp_path):
    be, _ = make(tmp_path, [])
    (be.images_dir / VARIANT_DIRS["v2"] / "bootlab_idf_blink.bin").unlink()
    with pytest.raises(LiveRigError):
        be.update("v2", "wifi", tmp_path / "u.log")


def test_unknown_variant(tmp_path):
    be, _ = make(tmp_path, [])
    with pytest.raises(LiveRigError):
        be.update("v9", "wifi", tmp_path / "u.log")


def test_reset_noop_when_confirmed_v1(tmp_path):
    be, calls = make(tmp_path, [snap()])
    assert be.reset_to_v1(tmp_path / "u.log") is True and calls == []


def test_reset_updates_when_on_v2_and_verifies(tmp_path):
    be, calls = make(tmp_path, [snap("2.0.0", 1), snap()])
    assert be.reset_to_v1(tmp_path / "u.log") is True and len(calls) == 1


def test_reset_fails_if_still_not_v1(tmp_path):
    be, _ = make(tmp_path, [snap("2.0.0", 1), snap("2.0.0", 1)])
    assert be.reset_to_v1(tmp_path / "u.log") is False


def test_wsl_refused():
    with pytest.raises(LiveRigError):
        assert_native_host(proc_version="Linux ... microsoft-standard-WSL2")
    assert_native_host(proc_version="Linux 6.1 generic")


class FakeSerial:
    def __init__(self):
        self.log, self.dtr, self.rts, self.port = [], None, None, None

    def __setattr__(self, k, v):
        if k in ("dtr", "rts"):
            self.__dict__.setdefault("log", []).append((k, v))
        object.__setattr__(self, k, v)

    def open(self):
        self.log.append(("open", None))

    def close(self):
        self.log.append(("close", None))


def test_hard_reset_esptool_sequence_lines_inactive_before_open():
    from tests_hil.live_backend import hard_reset
    fs = FakeSerial()
    sleeps = []
    hard_reset("COM14", serial_factory=lambda: fs, sleep=sleeps.append)
    log = fs.log
    o = log.index(("open", None))
    assert ("dtr", False) in log[:o] and ("rts", False) in log[:o]
    after = [e for e in log[o + 1:] if e[0] in ("dtr", "rts")]
    assert after == [("dtr", True), ("rts", False), ("dtr", False), ("rts", True), ("dtr", False), ("rts", False)]
    assert log[-1] == ("close", None) and len(sleeps) == 3


def test_wait_snapshot_tolerates_reboot_and_times_out(tmp_path):
    be, _ = make(tmp_path, [])
    seq = iter([RuntimeError("gone"), snap("2.0.0"), snap()])

    def fn():
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v
    be.snapshot_fn = fn
    got = be.wait_snapshot(lambda s: s.app == "1.0.0", timeout_s=10, poll_s=1, sleep_fn=lambda _: None)
    assert got is not None and got.app == "1.0.0"
    be.snapshot_fn = lambda: snap("2.0.0")
    assert be.wait_snapshot(lambda s: s.app == "1.0.0", timeout_s=3, poll_s=1, sleep_fn=lambda _: None) is None


class FakeDevice:
    """Minimal LABID device: answers ID?/VER?/STATE? lines, counts uptime, ignores junk."""
    def __init__(self, drop_every=0):
        self.buf, self.out, self.n, self.drop = b"", b"", 0, drop_every

    def write(self, data):
        from labflash.labid import build_frame
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            self.n += 1
            if self.drop and self.n % self.drop == 0:
                continue
            reply = {b"$LAB,ID?": ("ID", {"uid": "E072A1AA2390", "hw": "x", "mcu": "y"}),
                     b"$LAB,VER?": ("VER", {"app": "1.0.0", "slot": "0", "confirmed": "1"}),
                     b"$LAB,STATE?": ("STATE", {"uptime_ms": str(1000 + self.n * 10)})}.get(line)
            if reply:
                self.out += build_frame(reply[0], reply[1]).encode()

    def read1(self):
        b, self.out = self.out[:1], self.out[1:]
        return b

    def close(self):
        pass


def _be_with(tmp_path, dev):
    be, _ = make(tmp_path, [])
    be.transport_factory = lambda: dev
    return be


def test_stress_counts_good_answers(tmp_path):
    ok, n = _be_with(tmp_path, FakeDevice()).stress(5)
    assert (ok, n) == (5, 5)


def test_abuse_framing_reports_no_reset_and_sane(tmp_path):
    r = _be_with(tmp_path, FakeDevice()).abuse_framing()
    assert "err_codes" in r and r["no_reset"] and r["version_ok"] and r["uid"] == "E072A1AA2390"


def test_failure_image_versions_are_not_v1():
    from tests_hil.live_backend import _is_v1
    assert _is_v1("1.0.0") and _is_v1("1.2.3")
    assert not any(_is_v1(v) for v in ("1.0.0-hang", "1.0.0-badsig", "1.0.0-noconfirm", "2.0.0", "gen-abc"))


def test_reset_to_v1_rolls_back_a_pending_image_with_a_reset_not_an_ota(tmp_path, monkeypatch):
    import tests_hil.live_backend as lb
    resets = []
    monkeypatch.setattr(lb, "hard_reset", lambda port: resets.append(port))
    be, calls = make(tmp_path, [snap("1.0.0-noconfirm", 1, False), snap("1.0.0", 0, True)])
    assert be.reset_to_v1(tmp_path / "u.log") is True
    assert resets == ["COM14"] and calls == []               # a pending image refuses OTA; the reset rolled it back


def test_reset_to_v1_still_updates_when_the_rollback_lands_on_another_version(tmp_path, monkeypatch):
    import tests_hil.live_backend as lb
    monkeypatch.setattr(lb, "hard_reset", lambda port: None)
    be, calls = make(tmp_path, [snap("1.0.0-noconfirm", 1, False), snap("2.0.0", 0, True), snap("1.0.0", 1, True)])
    assert be.reset_to_v1(tmp_path / "u.log") is True and len(calls) == 1


def test_reset_to_v1_retries_a_transfer_that_never_started(tmp_path, monkeypatch):
    import tests_hil.live_backend as lb
    sleeps = []
    monkeypatch.setattr(lb, "RESTORE_SLEEP", sleeps.append)
    be, calls = make(tmp_path, [snap("2.0.0", 1), snap("1.0.0", 0)])
    results = iter([1, 1, 0])                                   # update fails twice, then works
    be.update_fn = lambda args: _flaky(calls, results)
    assert be.reset_to_v1(tmp_path / "u.log") is True and len(calls) == 3 and sleeps == [15.0, 15.0]


def _flaky(calls, results):
    calls.append(1)
    rc = next(results)
    print("UPDATE OK" if rc == 0 else "UPDATE FAILED")
    return rc


def test_reset_to_v1_gives_up_after_the_attempts(tmp_path, monkeypatch):
    import tests_hil.live_backend as lb
    monkeypatch.setattr(lb, "RESTORE_SLEEP", lambda s: None)
    be, calls = make(tmp_path, [snap("2.0.0", 1)], rc=1, out="UPDATE FAILED\n")
    assert be.reset_to_v1(tmp_path / "u.log") is False and len(calls) == lb.RESTORE_ATTEMPTS


def test_reset_reuses_the_shared_console_port_instead_of_opening_a_second_handle(tmp_path, monkeypatch):
    import tests_hil.live_backend as lb
    opened, shared = [], []
    monkeypatch.setattr(lb, "hard_reset", lambda port: opened.append(port))

    class Shared:
        def hard_reset(self):
            shared.append(1)
    be, _ = make(tmp_path, [])
    be.console_port = Shared()
    be.reset()
    assert shared == [1] and opened == []
    be.console_port = None
    be.reset()
    assert opened == ["COM14"]


def test_wifi_updates_use_the_configured_http_port(tmp_path):
    be, calls = make(tmp_path, [])
    be.http_port = 8444
    be.update("v1", "wifi", tmp_path / "u.log")
    assert calls[0].http_port == 8444


def test_ble_updates_take_the_shared_lock_and_wifi_updates_do_not(tmp_path):
    be, _ = make(tmp_path, [])
    be.ble_lock = tmp_path / "ble.lock"
    held = []
    real = be._transport_turn

    def spy(transport):
        held.append(transport)
        return real(transport)
    be._transport_turn = spy
    be.update("v1", "ble", tmp_path / "u.log")
    be.update("v1", "wifi", tmp_path / "u.log")
    assert held == ["ble", "wifi"] and (tmp_path / "ble.lock").exists()
    be.ble_lock = None
    assert type(real("ble")).__name__ == "nullcontext"
