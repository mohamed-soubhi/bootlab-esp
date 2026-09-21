"""Hardware-free tests for the HIL live backend (injected fakes). Live behaviour is proven on the board, not here."""
from __future__ import annotations

from pathlib import Path

import pytest

from labflash.update import Snapshot
from tests_hil.live_backend import LiveBackend, LiveRigError, assert_native_host, VARIANT_DIRS


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
    assert a.image.endswith("build_v2/bootlab_idf_blink.bin") and a.transport == "wifi"
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
