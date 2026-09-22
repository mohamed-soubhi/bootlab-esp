"""Hardware-free tests for the BL-060 soak runner (fake backend)."""
from __future__ import annotations

import json

from labflash.update import Snapshot

from tests_hil.soak import next_variant, plan_cycle, plan_transport, run_soak


class FakeBackend:
    def __init__(self, fail_cycles=(), start="1.0.0"):
        self.app, self.slot, self.calls, self.fail = start, 0, [], set(fail_cycles)
        self.n = 0

    def snapshot(self):
        return Snapshot(app=self.app, slot=self.slot, confirmed=True, uid="E072A1AA2390", source="labid")

    def update(self, variant, transport, log_path, timeout_s=None):
        self.n += 1
        self.calls.append((variant, transport))
        if self.n in self.fail:
            return False
        self.app, self.slot = ("2.0.0" if variant == "v2" else "1.0.0"), 1 - self.slot
        return True

    def reset_to_v1(self, log_path, transport="wifi"):
        if not self.app.startswith("1."):
            self.app, self.slot = "1.0.0", 1 - self.slot
        return True


def run(tmp_path, backend, cycles=8, **kw):
    return run_soak(backend, cycles=cycles, out_dir=tmp_path, pause_s=0, sleep_fn=lambda _: None,
                    clock=iter(range(0, 10_000, 3)).__next__, **kw)


def test_plan_alternates_variant_and_mixes_transports():
    plans = [plan_cycle(i) for i in range(1, 9)]
    assert [p[0] for p in plans] == ["v2", "v1"] * 4
    assert {p[1] for p in plans} == {"wifi", "ble"}
    assert [plan_transport(i) for i in range(1, 9)] == [p[1] for p in plans]


def test_next_variant_toggles_away_from_current():
    assert next_variant("1.0.0") == "v2"
    assert next_variant("2.0.0") == "v1"
    assert next_variant("1.0.0-noconfirm") == "v2"


def test_a_failed_cycle_does_not_cause_the_next_cycle_to_resend_the_same_version(tmp_path):
    """Regression for the 2026-09-22 soak finding: cycle 1 (target v2) fails and recovery leaves the board on v1;
    cycle 2 must target v2 again (the board's real state), never resend v1 while already on v1."""
    b = FakeBackend(fail_cycles={1})
    rep = run(tmp_path, b, cycles=2)
    assert rep["total_cycles"] == 2
    assert b.calls[0] == ("v2", "wifi") and b.calls[1] == ("v2", "wifi")  # cycle 2 retried v2, not a v1 resend
    lines = [json.loads(line) for line in (tmp_path / "cycles.jsonl").read_text().splitlines()]
    assert [r["variant"] for r in lines] == ["v2", "v2"]


def test_all_pass_report_labelled_live_and_ends_on_v1(tmp_path):
    b = FakeBackend()
    rep = run(tmp_path, b)
    assert rep["mode"] == "live" and rep["total_cycles"] == 8 and rep["passes"] == 8 and rep["pass_rate_pct"] == 100.0
    assert rep["final_state_v1"] is True and b.app == "1.0.0"
    lines = (tmp_path / "cycles.jsonl").read_text().splitlines()
    assert len(lines) == 8 and json.loads(lines[0])["cycle"] == 1
    assert json.loads((tmp_path / "report.json").read_text())["passes"] == 8


def test_failure_recorded_with_cause_and_run_continues(tmp_path):
    rep = run(tmp_path, FakeBackend(fail_cycles={3}))
    assert rep["failures"] == 1 and rep["total_cycles"] == 8
    f = rep["failure_log"][0]
    assert f["cycle"] == 3 and "update" in f["cause"]


def test_aborts_after_consecutive_failures(tmp_path):
    rep = run(tmp_path, FakeBackend(fail_cycles=set(range(1, 100))), cycles=20, max_consecutive_failures=3)
    assert rep["aborted"] is True and rep["total_cycles"] == 3


def test_resume_ignores_a_malformed_line_instead_of_miscounting(tmp_path):
    run(tmp_path, FakeBackend(), cycles=4)
    with (tmp_path / "cycles.jsonl").open("a") as f:
        f.write(json.dumps({"cycle": 4, "note": "not a cycle record"}) + "\n")
    b2 = FakeBackend()
    rep = run(tmp_path, b2, cycles=8, resume=True)
    assert rep["resumed_from"] == 4 and rep["total_cycles"] == 8
    assert len(b2.calls) == 4 and b2.calls[0] == plan_cycle(5)  # cycle 5 actually attempted, not skipped to 6


def test_resume_skips_completed_cycles(tmp_path):
    run(tmp_path, FakeBackend(), cycles=4)
    b2 = FakeBackend()
    rep = run(tmp_path, b2, cycles=8, resume=True)
    assert len(b2.calls) == 4 and rep["total_cycles"] == 8 and rep["resumed_from"] == 4


def test_recovery_reset_failure_does_not_crash_the_run(tmp_path):
    b = FakeBackend(fail_cycles={1})
    precondition_done = []

    def flaky_reset(log_path, transport="wifi"):
        if not precondition_done:
            precondition_done.append(1)
            return True   # precondition OK; the recovery call (after cycle 1 fails) is the flaky one
        raise TimeoutError("board unreachable")
    b.reset_to_v1 = flaky_reset
    rep = run(tmp_path, b, cycles=3)
    assert rep["total_cycles"] == 3 and rep["failures"] == 1
    lines = (tmp_path / "cycles.jsonl").read_text().splitlines()
    assert all("ok" in json.loads(line) for line in lines), "a non-cycle record broke the uniform jsonl format"
    assert "recovery reset raised" in (tmp_path / "update.log").read_text()


def test_wrong_version_after_ok_update_is_a_failure(tmp_path):
    b = FakeBackend()
    orig = b.update

    def lying_update(variant, transport, log_path, timeout_s=None):
        orig(variant, transport, log_path)
        b.app = "9.9.9"   # CLI said OK but the board reports something else
        return True
    b.update = lying_update
    rep = run(tmp_path, b, cycles=1)
    assert rep["failures"] == 1 and "expected 2.0.0" in rep["failure_log"][0]["cause"]
