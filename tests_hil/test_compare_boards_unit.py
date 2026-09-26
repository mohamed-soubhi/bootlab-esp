"""BL-072: compare two soak runs (one per board) and flag board-to-board differences. Owner: Claude wrote the spec, the cheap
agent implements tests_hil/compare_boards.py."""
from __future__ import annotations

import json

from tests_hil import compare_boards as cb

PLAN = {"seed": 7, "cycles": 6, "ble_share": 0.5, "failure_cap": 2, "manifest_sha256": "abc", "model_version": 2}
PICKS = [("wifi", "fixed", "v1"), ("ble", "fixed", "v2"), ("wifi", "failure", "bad_sig"), ("ble", "generated", "gen-1"),
         ("wifi", "fixed", "v3"), ("ble", "failure", "hang")]
BASE = {("wifi", "fixed"): 32.0, ("ble", "fixed"): 108.0, ("wifi", "failure"): 150.0, ("ble", "generated"): 220.0, ("ble", "failure"): 180.0}


def _make_run(tmp_path, name, scale=1.0, bad_cycles=(), plan=PLAN, retries=None):
    d = tmp_path / name
    d.mkdir()
    lines = [json.dumps({"header": plan})]
    for n, (transport, kind, image) in enumerate(PICKS, 1):
        rec = {"cycle": n, "image": image, "kind": kind, "transport": transport, "ok": n not in bad_cycles,
               "cause": "" if n not in bad_cycles else "board did not roll back",
               "duration_s": round(BASE[(transport, kind)] * scale, 1)}
        if retries and n in retries:
            rec["infra_retries"] = retries[n]
        lines.append(json.dumps(rec))
    lines.append(json.dumps({"cycle": 3, "image": "bad_sig", "kind": "failure", "transport": "wifi", "ok": True, "cause": "",
                             "duration_s": round(150.0 * scale, 1), "rerun": True}))   # a re-run supersedes the earlier record
    (d / "cycles.jsonl").write_text("\n".join(lines) + "\n")
    passes = 6 - len(bad_cycles)
    (d / "report.json").write_text(json.dumps({"seed": plan["seed"], "plan": plan, "total_cycles": 6, "passes": passes,
                                               "failures": 6 - passes, "pass_rate_pct": round(passes / 6 * 100, 2),
                                               "aborted": False, "final_state_confirmed": True}))
    return d


def test_load_run_keeps_the_latest_record_per_cycle(tmp_path):
    run = cb.load_run(_make_run(tmp_path, "a"))
    assert sorted(run["cycles"]) == [1, 2, 3, 4, 5, 6]
    assert run["cycles"][3].get("rerun") is True and run["report"]["seed"] == 7


def test_summarize_reports_rates_medians_and_retries(tmp_path):
    s = cb.summarize(cb.load_run(_make_run(tmp_path, "a", bad_cycles=(6,), retries={2: 1, 5: 2})))
    assert s["cycles"] == 6 and s["passes"] == 5 and s["pass_rate_pct"] == 83.33
    assert s["infra_retries"] == 3
    assert s["median_s"][("wifi", "fixed")] == 32.0 and s["median_s"][("ble", "failure")] == 180.0
    assert [f["cycle"] for f in s["failures"]] == [6]


def test_identical_runs_have_no_flags(tmp_path):
    c = cb.compare(cb.load_run(_make_run(tmp_path, "a")), cb.load_run(_make_run(tmp_path, "b")))
    assert c["plan_identical"] is True and c["flags"] == []
    assert c["cycle_agreement"] == {"same_outcome": 6, "differ": []}
    assert all(not d["flagged"] for d in c["duration_diffs"])


def test_a_slower_board_is_flagged_by_ratio(tmp_path):
    c = cb.compare(cb.load_run(_make_run(tmp_path, "a")), cb.load_run(_make_run(tmp_path, "b", scale=1.5)), tolerance=0.25)
    flagged = [d for d in c["duration_diffs"] if d["flagged"]]
    assert len(flagged) == 5 and all(abs(d["ratio"] - 1.5) < 0.01 for d in flagged)
    assert any("slower" in f for f in c["flags"])


def test_small_differences_are_not_flagged(tmp_path):
    c = cb.compare(cb.load_run(_make_run(tmp_path, "a")), cb.load_run(_make_run(tmp_path, "b", scale=1.1)), tolerance=0.25)
    assert not any(d["flagged"] for d in c["duration_diffs"])


def test_outcome_differences_are_listed_by_cycle(tmp_path):
    c = cb.compare(cb.load_run(_make_run(tmp_path, "a")), cb.load_run(_make_run(tmp_path, "b", bad_cycles=(2, 6))))
    assert c["cycle_agreement"]["differ"] == [2, 6] and c["cycle_agreement"]["same_outcome"] == 4
    assert any("outcome" in f for f in c["flags"])


def test_a_different_plan_is_flagged_and_cycles_are_not_compared(tmp_path):
    other = dict(PLAN, seed=8)
    c = cb.compare(cb.load_run(_make_run(tmp_path, "a")), cb.load_run(_make_run(tmp_path, "b", plan=other)))
    assert c["plan_identical"] is False and any("plan" in f for f in c["flags"])
    assert c["cycle_agreement"] is None


def test_markdown_has_a_table_and_names_the_flagged_rows(tmp_path):
    c = cb.compare(cb.load_run(_make_run(tmp_path, "a")), cb.load_run(_make_run(tmp_path, "b", scale=2.0, bad_cycles=(4,))))
    md = cb.render_markdown(c, names=("board 1", "board 2"))
    assert "board 1" in md and "board 2" in md and "|" in md and "ble" in md
    assert "pass rate" in md.lower() and md.count("FLAG") >= 1
