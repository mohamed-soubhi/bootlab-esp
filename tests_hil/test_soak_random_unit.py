"""BL-067: hardware-free tests for the randomized soak runner (fake board that models all image kinds). Owner: Claude."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from labflash import imagefmt as fmt
from labflash import imagegen as gen
from labflash import poolmanifest as pm
from labflash.update import Snapshot

from tests_hil import soak_model as sm
from tests_hil import soak_random as sr
from tests_hil.otaretry import transfer_seen


def _pool(tmp_path):
    entries = []
    for i, v in enumerate(gen.gen_pool("rand")):
        sl = {"near_limit": fmt.SLOT_SIZE - 4096 * 3, "too_big": fmt.SLOT_SIZE + 4096 * 5}.get(
            v.role, 1_249_280 + fmt.align_up(v.pad_bytes))
        data = bytes([i + 1]) * 64 + b"\0" * (sl + v.trailer_len - 64)
        (tmp_path / f"g{i:02d}.bin").write_bytes(data)
        entries.append(pm.make_entry(i, v, f"g{i:02d}.bin", data, sl))
    m = pm.make_manifest("rand", entries)
    pm.write_manifest(tmp_path / "manifest.json", m)
    return m


class FakeBoard:
    """A board that behaves like the real one for every image kind; `misbehave` maps update call number -> mode."""

    def __init__(self, catalog, misbehave=None, console=None):
        self.console = console
        self.by_path = {}
        for img in (*catalog.fixed, *catalog.failures, *catalog.generated):
            self.by_path[img.file if img.kind == "generated" else f"/img/{img.file}.bin"] = img
        self.app, self.slot, self.confirmed = "1.0.0", 0, True
        self.prior, self.n, self.resets = None, 0, 0
        self.misbehave = misbehave or {}
        self.log = []

    def image_for(self, variant):
        return Path(f"/img/{variant}.bin")

    def snapshot(self):
        return Snapshot(self.app, self.slot, self.confirmed, "UID", "labid")

    def reset(self):
        self.resets += 1
        if self.prior:                                   # unconfirmed image rolls back on reset
            self.app, self.slot = self.prior
            self.prior, self.confirmed = None, True

    def wait_snapshot(self, wanted, timeout_s=60.0, poll_s=2.0, sleep_fn=None):
        s = self.snapshot()
        return s if wanted(s) else None

    def reset_to_v1(self, log_path, transport=None):
        self.app, self.confirmed, self.prior = "1.0.0", True, None
        return True

    def update_image_path(self, image_path, transport, log_path, timeout_s=None):
        key = image_path.name if image_path.name.startswith("g") and image_path.name[1:3].isdigit() else f"/img/{image_path.name}"
        img = self.by_path[key.replace("\\", "/")] if key in self.by_path else self.by_path[f"/img/{image_path.name}"]
        self.n += 1
        self.log.append((img.name, transport))
        m = self.misbehave.get(self.n)
        with log_path.open("a", encoding="utf-8") as f:                    # what the real update CLI prints
            if m == "no_transfer":
                f.write("host served: {} (image was 1234 bytes)\n" if transport == "wifi" else "no sectors\n")
            elif m == "partial_transfer":
                f.write("host served: {'update.bin': 100} (image was 1234 bytes)\n" if transport == "wifi"
                        else "  BLE: sector 1/2\n")
            else:
                f.write("host served: {'update.bin': 1234} (image was 1234 bytes)\n" if transport == "wifi"
                        else "  BLE: sector 1/2\n  BLE: sector 2/2\n")
        if img.failure == "hang" and m != "hang_never_boots" and self.console is not None:
            with self.console.open("a", encoding="utf-8") as f:
                f.write("E (5012) task_wdt: Task watchdog got triggered. The following tasks did not reset the watchdog in time:\n")
        mode = self.misbehave.get(self.n)
        if mode in ("no_transfer", "partial_transfer") or (mode == "hang_never_boots" and img.failure != "hang"):
            return False
        if mode == "raise":
            raise OSError("link down")
        if mode == "dead":
            return False
        if img.kind in ("fixed", "generated"):
            if not img.accepts[transport]:
                return False
            self.app, self.slot, self.confirmed = img.version, self.slot ^ 1, True
            return True
        if img.failure == "bad_sig":
            if mode == "accepts_bad":
                self.app, self.slot = img.version, self.slot ^ 1
                return True
            return False
        if img.failure == "no_confirm":
            if mode != "never_boots":
                self.prior = (self.app, self.slot)
                self.app, self.slot, self.confirmed = img.version, self.slot ^ 1, False
            return False
        return False                                    # hang: boots, watchdog resets, rolls back before update() returns


def _setup(tmp_path, cycles=60, seed=7, **kw):
    m = _pool(tmp_path)
    cat = sm.build_catalog(m)
    picks = sm.plan(seed, cycles, cat)
    plan_id = sr._plan_id(seed, cycles, 0.5, 2, m)
    return cat, picks, plan_id


def _run(tmp_path, board, cat, picks, plan_id, **kw):
    kw.setdefault("infra_retries", 0)               # the fakes below model board behaviour, not host trouble
    if board.console is None:
        board.console = tmp_path / "console.txt"
    return sr.run_soak(board, cat, picks, plan_id, tmp_path, tmp_path / kw.pop("out_name", "out"), pause_s=0,
                       sleep_fn=lambda s: None, console_log=board.console, **kw)


def _records(out):
    return [json.loads(x) for x in (out / "cycles.jsonl").read_text().splitlines() if x.strip() and "header" not in x]


def test_a_clean_run_passes_every_cycle_and_ends_confirmed(tmp_path):
    cat, picks, pid = _setup(tmp_path, 120)
    rep = _run(tmp_path, FakeBoard(cat), cat, picks, pid)
    assert rep["total_cycles"] == 120 and rep["failures"] == 0 and rep["pass_rate_pct"] == 100.0
    assert not rep["aborted"] and rep["final_state_confirmed"] and rep["mode"] == "live" and rep["seed"] == 7
    kinds = {r["kind"] for r in _records(tmp_path / "out")}
    assert {"warmup", "fixed", "generated", "failure"} <= kinds


def test_warmup_proves_both_transports_before_cycle_one(tmp_path):
    cat, picks, pid = _setup(tmp_path, 5)
    board = FakeBoard(cat)
    _run(tmp_path, board, cat, picks, pid)
    assert board.log[:2] == [("v2", "wifi"), ("v1", "ble")]
    assert [r["cycle"] for r in _records(tmp_path / "out")[:2]] == [0, 0]


def test_same_seed_replays_the_same_sequence(tmp_path):
    cat, picks, pid = _setup(tmp_path, 40)
    a, b = FakeBoard(cat), FakeBoard(cat)
    _run(tmp_path, a, cat, picks, pid, out_name="a")
    _run(tmp_path, b, cat, sm.plan(7, 40, cat), pid, out_name="b")
    assert a.log == b.log


def test_failure_images_leave_the_board_on_the_last_confirmed_image(tmp_path):
    cat, picks, pid = _setup(tmp_path, 200, seed=3)
    board = FakeBoard(cat)
    rep = _run(tmp_path, board, cat, picks, pid)
    assert rep["failures"] == 0
    assert board.resets >= 1                              # no_confirm cycles reset the board to trigger the rollback
    assert board.snapshot().confirmed


def test_a_generated_image_reports_the_slots_it_landed_in(tmp_path):
    cat, picks, pid = _setup(tmp_path, 300, seed=5)
    rep = _run(tmp_path, FakeBoard(cat), cat, picks, pid)
    assert rep["generated_slots"] and all(s in ([0], [1], [0, 1]) for v in rep["generated_slots"].values() for s in v.values())


def test_a_bad_sig_image_that_the_board_accepts_is_a_failure(tmp_path):
    cat, picks, pid = _setup(tmp_path, 200, seed=3)
    first_bad = next(i for i, p in enumerate(picks) if p.image.failure == "bad_sig")
    board = FakeBoard(cat)
    # update call numbers: 2 warm-up installs, then one call per cycle
    board.misbehave = {2 + first_bad + 1: "accepts_bad"}
    rep = _run(tmp_path, board, cat, picks, pid)
    assert rep["failures"] == 1 and "rejected image changed" in rep["failure_log"][0]["cause"]
    assert not rep["aborted"] and rep["final_state_confirmed"]


def test_a_no_confirm_image_that_never_boots_is_a_failure(tmp_path):
    cat, picks, pid = _setup(tmp_path, 200, seed=3)
    idx = next(i for i, p in enumerate(picks) if p.image.failure == "no_confirm")
    board = FakeBoard(cat, {2 + idx + 1: "never_boots"})
    rep = _run(tmp_path, board, cat, picks, pid)
    assert rep["failures"] == 1 and "did not boot unconfirmed" in rep["failure_log"][0]["cause"]


def test_an_exception_is_a_recorded_failure_and_the_model_resyncs(tmp_path):
    cat, picks, pid = _setup(tmp_path, 60)
    rep = _run(tmp_path, FakeBoard(cat, {10: "raise"}), cat, picks, pid)
    assert rep["failures"] == 1 and "link down" in rep["failure_log"][0]["cause"] and rep["pass_rate_pct"] > 95


def test_three_consecutive_unexpected_outcomes_abort_and_restore(tmp_path):
    cat, picks, pid = _setup(tmp_path, 60)
    rep = _run(tmp_path, FakeBoard(cat, {n: "dead" for n in range(5, 40)}), cat, picks, pid)
    assert rep["aborted"] and rep["final_state_confirmed"] and rep["failures"] == 3


def test_a_failed_warmup_stops_the_run_before_any_cycle(tmp_path):
    cat, picks, pid = _setup(tmp_path, 10)
    with pytest.raises(sr.SoakError, match="warm-up"):
        _run(tmp_path, FakeBoard(cat, {1: "dead"}), cat, picks, pid)


def test_resume_continues_the_same_plan_and_refuses_another(tmp_path):
    cat, picks, pid = _setup(tmp_path, 50)
    b1 = FakeBoard(cat)
    _run(tmp_path, b1, cat, picks, pid, stop_after=20)
    assert len([r for r in _records(tmp_path / "out") if r["cycle"] >= 1]) == 20
    b2 = FakeBoard(cat)
    b2.app, b2.slot = b1.app, b1.slot
    rep = _run(tmp_path, b2, cat, picks, pid, resume=True)
    assert rep["total_cycles"] == 50 and rep["failures"] == 0 and rep["resumed_from"] == 20
    with pytest.raises(sr.SoakError, match="different plan"):
        _run(tmp_path, FakeBoard(cat), cat, picks, dict(pid, seed=99), resume=True)


def test_existing_output_without_resume_refuses_to_overwrite(tmp_path):
    cat, picks, pid = _setup(tmp_path, 10)
    _run(tmp_path, FakeBoard(cat), cat, picks, pid, stop_after=3)
    with pytest.raises(FileExistsError):
        _run(tmp_path, FakeBoard(cat), cat, picks, pid)


def test_dry_run_prints_the_seeded_plan_without_a_board(tmp_path, capsys):
    _pool(tmp_path)
    assert sr.main(["--pool", str(tmp_path), "--out", str(tmp_path / "o"), "--cycles", "50", "--seed", "11", "--dry-run"]) == 0
    first = capsys.readouterr().out
    sr.main(["--pool", str(tmp_path), "--out", str(tmp_path / "o"), "--cycles", "50", "--seed", "11", "--dry-run"])
    assert first == capsys.readouterr().out and first.startswith("seed 11:")
    assert not (tmp_path / "o").exists()


def test_a_failure_image_without_transfer_evidence_is_a_failure_not_a_pass(tmp_path):
    cat, picks, pid = _setup(tmp_path, 200, seed=3)
    idx = next(i for i, p in enumerate(picks) if p.image.kind == "failure")
    rep = _run(tmp_path, FakeBoard(cat, {2 + idx + 1: "no_transfer"}), cat, picks, pid)
    assert rep["failures"] == 1 and "no complete transfer" in rep["failure_log"][0]["cause"]


def test_transfer_evidence_parsing():
    assert transfer_seen("host served: {'update.bin': 10} (image was 10 bytes)", "wifi")
    assert not transfer_seen("host served: {'update.bin': 4} (image was 10 bytes)", "wifi")      # partial
    assert not transfer_seen("host served: {} (image was 10 bytes)", "wifi")
    assert transfer_seen("  BLE: sector 1/300\n  BLE: sector 300/300", "ble")
    assert not transfer_seen("  BLE: sector 3/300", "ble")                                       # partial
    assert not transfer_seen("BLE OTA failed: no device", "ble")


def test_a_partial_transfer_of_a_failure_image_is_not_evidence(tmp_path):
    cat, picks, pid = _setup(tmp_path, 200, seed=3)
    idx = next(i for i, p in enumerate(picks) if p.image.kind == "failure")
    rep = _run(tmp_path, FakeBoard(cat, {2 + idx + 1: "partial_transfer"}), cat, picks, pid)
    assert rep["failures"] == 1 and "no complete transfer" in rep["failure_log"][0]["cause"]


def test_a_hang_image_that_never_ran_is_not_a_pass(tmp_path):
    cat, picks, pid = _setup(tmp_path, 300, seed=3)
    idx = next(i for i, p in enumerate(picks) if p.image.failure == "hang")
    rep = _run(tmp_path, FakeBoard(cat, {2 + idx + 1: "hang_never_boots"}), cat, picks, pid)
    assert rep["failures"] == 1 and "no evidence that the hang image ran" in rep["failure_log"][0]["cause"]


def test_the_board_is_restored_and_a_report_written_even_when_the_run_dies(tmp_path):
    cat, picks, pid = _setup(tmp_path, 60)

    class Dies(FakeBoard):
        died = False

        def snapshot(self):
            if self.n >= 8 and not self.died:
                self.died = True
                raise KeyboardInterrupt
            return super().snapshot()

        def reset_to_v1(self, log_path, transport=None):
            self.restored = True
            return super().reset_to_v1(log_path, transport)
    board = Dies(cat)
    board.restored = False
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, board, cat, picks, pid)
    assert board.restored and (tmp_path / "out" / "report.json").is_file()


def test_a_soak_error_still_writes_the_report_and_restores(tmp_path):
    cat, picks, pid = _setup(tmp_path, 10)
    board = FakeBoard(cat, {1: "dead"})
    with pytest.raises(sr.SoakError, match="warm-up"):
        _run(tmp_path, board, cat, picks, pid)
    rep = json.loads((tmp_path / "out" / "report.json").read_text())
    assert rep["error"] and "warm-up" in rep["error"] and rep["final_state_confirmed"]


def test_a_torn_last_line_does_not_break_resume(tmp_path):
    cat, picks, pid = _setup(tmp_path, 30)
    b1 = FakeBoard(cat)
    _run(tmp_path, b1, cat, picks, pid, stop_after=10)
    with (tmp_path / "out" / "cycles.jsonl").open("a") as f:
        f.write('{"cycle": 11, "image": "v')                    # killed mid-write
    b2 = FakeBoard(cat)
    b2.app, b2.slot = b1.app, b1.slot
    rep = _run(tmp_path, b2, cat, picks, pid, resume=True)
    assert rep["total_cycles"] == 30 and rep["failures"] == 0


def test_resume_refuses_non_contiguous_cycles(tmp_path):
    cat, picks, pid = _setup(tmp_path, 30)
    _run(tmp_path, FakeBoard(cat), cat, picks, pid, stop_after=6)
    lines = (tmp_path / "out" / "cycles.jsonl").read_text().splitlines()
    dropped = [x for x in lines if '"cycle": 3,' not in x]
    (tmp_path / "out" / "cycles.jsonl").write_text("\n".join(dropped) + "\n")
    with pytest.raises(sr.SoakError, match="contiguous"):
        _run(tmp_path, FakeBoard(cat), cat, picks, pid, resume=True)


def test_a_board_that_drifted_from_the_model_is_resynced_and_flagged(tmp_path):
    cat, picks, _pid = _setup(tmp_path, 10)
    board = FakeBoard(cat)                                     # real board: 1.0.0, slot 0, confirmed
    stale = sm.State("2.0.0", 1, True)                         # what the model wrongly believes
    rec, exp = sr._cycle(board, cat, tmp_path, picks[0], stale, tmp_path / "u.log", None, None, 0)
    assert rec["ok"] and rec["resynced_from_board"] is True
    assert exp is not None and exp.slot in (0, 1)


def test_an_unconfirmed_board_before_a_cycle_is_a_soak_error(tmp_path):
    cat, picks, _ = _setup(tmp_path, 10)
    board = FakeBoard(cat)
    board.confirmed = False
    with pytest.raises(sr.SoakError, match="unconfirmed"):
        sr._cycle(board, cat, tmp_path, picks[0], sm.State("1.0.0", 0, True), tmp_path / "u.log", None, None, 0)


def test_plan_id_carries_the_model_version(tmp_path):
    _, _, pid = _setup(tmp_path, 5)
    assert pid["model_version"] == sm.MODEL_VERSION
