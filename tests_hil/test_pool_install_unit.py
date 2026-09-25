"""BL-069 AC5: hardware-free tests for the pool install runner (fake board). Owner: Claude."""
from __future__ import annotations

import json

import pytest
from labflash import imagefmt as fmt
from labflash import imagegen as gen
from labflash import poolmanifest as pm
from labflash.update import Snapshot

from tests_hil import pool_install as pi
from tests_hil import pool_schedule as ps


def _make_pool(tmp_path):
    entries = []
    for i, v in enumerate(gen.gen_pool("inst")):
        sl = {"near_limit": fmt.SLOT_SIZE - 4096 * 3, "too_big": fmt.SLOT_SIZE + 4096 * 5}.get(
            v.role, 1_249_280 + fmt.align_up(v.pad_bytes))
        data = bytes([i + 1]) * 64 + b"\0" * (sl + v.trailer_len - 64)
        (tmp_path / f"g{i:02d}.bin").write_bytes(data)
        entries.append(pm.make_entry(i, v, f"g{i:02d}.bin", data, sl))
    m = pm.make_manifest("inst", entries)
    pm.write_manifest(tmp_path / "manifest.json", m)
    return m


class FakeBoard:
    """A board that follows the manifest's expectations; `break_keys` makes chosen installs misbehave."""

    def __init__(self, manifest, start_slot=0, break_keys=(), reject_hangs=False):
        self.by_file = {e["file"]: e for e in manifest["images"]}
        self.app, self.slot, self.confirmed = "1.0.0", start_slot, True
        self.calls, self.broken, self.n = [], set(break_keys), 0
        self.silently_moves_on_reject = reject_hangs

    def snapshot(self):
        return Snapshot(self.app, self.slot, self.confirmed, "UID", "labid")

    def update_image_path(self, image_path, transport, log_path, timeout_s=None):
        e = self.by_file.get(image_path.name)
        self.calls.append((e["index"] if e else image_path.name, transport, timeout_s))
        self.n += 1
        if self.n in self.broken:
            return False
        if e and e["expected"][transport]["accept"]:
            self.app, self.slot, self.confirmed = e["version"], self.slot ^ 1, True
            return True
        if e and self.silently_moves_on_reject:
            self.slot ^= 1
        return False

    def reset_to_v1(self, log_path, transport=None):
        self.app, self.confirmed = "1.0.0", True
        return True


def _run(tmp_path, board, m, **kw):
    kw.setdefault("sweeps", 2)
    out = tmp_path / kw.pop("out_name", "out")
    return pi.run_pool_install(board, m, tmp_path, out, pause_s=0, sleep_fn=lambda s: None, **kw)


def _records(out):
    lines = [json.loads(x) for x in (out / "results.jsonl").read_text().splitlines() if x.strip()]
    return [r for r in lines if "key" in r]


def test_verify_pool_accepts_an_intact_pool_and_names_the_bad_file(tmp_path):
    m = _make_pool(tmp_path)
    pi.verify_pool(m, tmp_path)
    (tmp_path / "g03.bin").write_bytes((tmp_path / "g03.bin").read_bytes()[:-1] + b"\x99")
    with pytest.raises(pi.PoolError, match="g03.bin"):
        pi.verify_pool(m, tmp_path)
    (tmp_path / "g04.bin").unlink()
    with pytest.raises(pi.PoolError, match="g04.bin|g03.bin"):
        pi.verify_pool(m, tmp_path)


@pytest.mark.parametrize("start_slot", [0, 1])
def test_clean_run_passes_and_covers_both_slots(tmp_path, start_slot):
    m = _make_pool(tmp_path)
    rep = _run(tmp_path, FakeBoard(m, start_slot), m)
    assert rep["counts"]["fail"] == 0 and rep["coverage_gaps"] == [] and not rep["aborted"]
    assert rep["counts"]["expected_reject"] == 2 and rep["counts"]["skipped"] == 4      # too_big x2 transports, ble skips 2 x 2 sweeps
    assert rep["final_state_v1"] is True and rep["mode"] == "live"
    assert (tmp_path / "out" / "results.jsonl").is_file()
    cov = json.loads((tmp_path / "out" / "slot_coverage.json").read_text())
    assert all(set(v["wifi"]) == {0, 1} for v in cov.values())


def test_skipped_steps_never_touch_the_board(tmp_path):
    m = _make_pool(tmp_path)
    b = FakeBoard(m)
    _run(tmp_path, b, m)
    ble_calls = {c[0] for c in b.calls if c[1] == "ble"}
    unaligned = {e["index"] for e in m["images"] if e["role"] == "unaligned_trailer"}
    assert not (ble_calls & unaligned)


def test_expected_reject_uses_a_short_timeout_and_checks_the_board_is_unchanged(tmp_path):
    m = _make_pool(tmp_path)
    b = FakeBoard(m)
    rep = _run(tmp_path, b, m, reject_timeout_s=77)
    assert {c[2] for c in b.calls if c[0] == 12} == {77}
    assert rep["counts"]["expected_reject"] == 2
    b2 = FakeBoard(m, reject_hangs=True)             # board moves slot although it should have rejected
    rep2 = _run(tmp_path, b2, m, out_name="out2")
    assert rep2["counts"]["fail"] >= 1


def test_a_failed_install_is_recorded_recovered_and_does_not_cascade(tmp_path):
    m = _make_pool(tmp_path)
    rep = _run(tmp_path, FakeBoard(m, break_keys={3}), m)
    assert rep["counts"]["fail"] == 1 and not rep["aborted"]
    assert rep["coverage_gaps"] == [] and rep["topup_installs"] >= 1      # the top-up pass closed what the failure opened


def test_three_consecutive_failures_abort_and_restore_v1(tmp_path):
    m = _make_pool(tmp_path)
    rep = _run(tmp_path, FakeBoard(m, break_keys={1, 2, 3}), m, max_consecutive_unexpected=3)
    assert rep["aborted"] is True and rep["final_state_v1"] is True
    assert rep["counts"]["fail"] == 3


def test_resume_skips_completed_steps(tmp_path):
    m = _make_pool(tmp_path)
    b1 = FakeBoard(m)
    _run(tmp_path, b1, m, stop_after=10)
    assert len(_records(tmp_path / "out")) == 10
    b2 = FakeBoard(m, start_slot=b1.slot)
    b2.app = b1.app
    rep = _run(tmp_path, b2, m, resume=True)
    total = len(ps.plan_sweeps(m))
    assert rep["counts"]["fail"] == 0 and rep["resumed_from"] == 10
    assert len(_records(tmp_path / "out")) == total


def test_existing_results_without_resume_refuse_to_overwrite(tmp_path):
    m = _make_pool(tmp_path)
    _run(tmp_path, FakeBoard(m), m, stop_after=2)
    with pytest.raises(FileExistsError):
        _run(tmp_path, FakeBoard(m), m)


def test_dry_run_prints_the_plan_and_needs_no_board(tmp_path, capsys):
    _make_pool(tmp_path)
    assert pi.main(["--pool", str(tmp_path), "--out", str(tmp_path / "o"), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "wifi:1:0" in out and "ble:2:" in out and "skip" in out


class ExplodingBoard(FakeBoard):
    """Raises on chosen calls to update_image_path / snapshot to prove errors become recorded failures."""

    def __init__(self, manifest, boom_update=(), boom_snapshot=(), **kw):
        super().__init__(manifest, **kw)
        self.boom_update, self.boom_snapshot, self.snaps = set(boom_update), set(boom_snapshot), 0

    def update_image_path(self, image_path, transport, log_path, timeout_s=None):
        if self.n + 1 in self.boom_update:
            self.n += 1
            raise OSError("link down")
        return super().update_image_path(image_path, transport, log_path, timeout_s)

    def snapshot(self):
        self.snaps += 1
        if self.snaps in self.boom_snapshot:
            raise OSError("labid read failed")
        return super().snapshot()


def test_a_reject_over_an_unproven_transport_is_a_failure_not_an_expected_reject(tmp_path):
    m = _make_pool(tmp_path)
    accepting = sum(1 for e in m["images"] if e["expected"]["wifi"]["accept"])
    rep = _run(tmp_path, FakeBoard(m, break_keys=set(range(1, accepting + 1))), m, sweeps=1,
               max_consecutive_unexpected=99, transports=("wifi",))
    unverified = [f for f in rep["failure_log"] if "unverified" in f["cause"]]
    assert unverified and rep["counts"]["expected_reject"] == 0


def test_an_exception_during_a_reject_is_a_failure_not_an_expected_reject(tmp_path):
    m = _make_pool(tmp_path)
    accepting = sum(1 for e in m["images"] if e["expected"]["wifi"]["accept"])
    rep = _run(tmp_path, ExplodingBoard(m, boom_update={accepting + 1}), m, sweeps=1, transports=("wifi",))
    assert rep["counts"]["expected_reject"] == 0 and any("link down" in f["cause"] for f in rep["failure_log"])


def test_an_unreadable_board_before_an_update_is_recorded_not_fatal(tmp_path):
    m = _make_pool(tmp_path)
    rep = _run(tmp_path, ExplodingBoard(m, boom_snapshot={3}), m)
    assert rep["counts"]["fail"] >= 1 and any("unreadable" in f["cause"] for f in rep["failure_log"])
    assert (tmp_path / "out" / "report.json").is_file()


def test_resume_retries_failed_steps_but_not_passed_ones(tmp_path):
    m = _make_pool(tmp_path)
    b1 = FakeBoard(m, break_keys={2})
    _run(tmp_path, b1, m, stop_after=6)
    first = _records(tmp_path / "out")
    assert sum(r["verdict"] == "fail" for r in first) == 1
    b2 = FakeBoard(m, start_slot=b1.slot)
    b2.app = b1.app
    rep = _run(tmp_path, b2, m, resume=True)
    assert rep["counts"]["fail"] == 0 and rep["coverage_gaps"] == []
    keys = [r["key"] for r in _records(tmp_path / "out")]
    assert keys.count(next(r["key"] for r in first if r["verdict"] == "fail")) == 2     # tried, failed, retried


def test_resume_refuses_results_from_a_different_pool(tmp_path):
    m = _make_pool(tmp_path)
    _run(tmp_path, FakeBoard(m), m, stop_after=3)
    other = dict(m, seed_base="another")
    with pytest.raises(pi.PoolError, match="different pool"):
        _run(tmp_path, FakeBoard(m), other, resume=True)


def test_failed_recovery_is_counted_and_logged(tmp_path):
    m = _make_pool(tmp_path)

    class NoRecover(FakeBoard):
        def reset_to_v1(self, log_path, transport=None):
            return self.n == 0                     # the start-of-run reset works, recovery afterwards does not
    rep = _run(tmp_path, NoRecover(m, break_keys={3}), m)
    assert rep["recovery_failures"] >= 1
    assert "did not restore confirmed v1" in (tmp_path / "out" / "update.log").read_text()


def test_topup_closes_coverage_gaps_left_by_a_failure(tmp_path):
    m = _make_pool(tmp_path)
    rep = _run(tmp_path, FakeBoard(m, break_keys={2}), m)
    assert rep["counts"]["fail"] == 1 and rep["coverage_gaps"] == [] and rep["topup_installs"] >= 1
    assert any(r.get("topup") for r in _records(tmp_path / "out"))


def test_topup_is_bounded_when_a_transport_is_dead(tmp_path):
    m = _make_pool(tmp_path)
    ble_first = sum(1 for e in m["images"] if e["expected"]["wifi"]["accept"]) * 2 + 1
    rep = _run(tmp_path, FakeBoard(m, break_keys=set(range(ble_first, ble_first + 400))), m,
               max_consecutive_unexpected=1000)
    assert rep["topup_installs"] <= pi.TOPUP_LIMIT and rep["coverage_gaps"]


def test_clean_run_needs_no_topup(tmp_path):
    m = _make_pool(tmp_path)
    assert _run(tmp_path, FakeBoard(m), m)["topup_installs"] == 0
