"""Per-board tracks (idf / zephyr) in tickets_tool.py: dependency rules, set --track,
status derivation, readiness, checks, and the per-track Gantt. Synthetic data only."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tickets_tool as tt  # noqa: E402


def _t(i, deps=(), status="todo", tracks=None, size="S", epic="E0", **extra):
    t = {"id": i, "epic": epic, "title": f"{i} title", "size": size, "boards": [], "deps": list(deps),
         "desc": "", "ac": ["x"], "status": status, "pr": ""}
    if tracks is not None:
        t["tracks"] = tracks
    t.update(extra)
    return t


def _db():
    """T1 shared+done; A idf-only; G idf-only gate; B zephyr-only gated on G; M both boards."""
    return {
        "project": "p", "statuses": ["todo", "doing", "review", "blocked", "done"],
        "sizes": {"S": "", "M": "", "L": ""},
        "epics": [{"id": "E0", "phase": "P0", "title": "Setup", "plan": ""}],
        "tickets": [
            _t("T1", status="done"),
            _t("A", ["T1"], tracks=["idf"]),
            _t("G", ["A"], tracks=["idf"]),
            _t("B", ["T1"], tracks=["zephyr"], deps_by_track={"zephyr": ["G"]}),
            _t("M", ["A", "B"], tracks=["idf", "zephyr"]),
        ],
    }


def test_tracks_of_and_shared_tickets():
    db = _db()
    by = tt.by_id(db)
    assert tt.tracks_of(by["A"]) == ["idf"]
    assert tt.tracks_of(by["M"]) == ["idf", "zephyr"]
    assert tt.tracks_of(by["T1"]) == []            # no tracks = shared prerequisite
    assert tt.has_tracks(db) is True


def test_a_dependency_applies_only_to_the_matching_track():
    db = _db()
    assert tt.node_deps(db, ("M", "idf")) == [("A", "idf")]          # B is zephyr-only: ignored
    assert tt.node_deps(db, ("M", "zephyr")) == [("B", "zephyr")]    # A is idf-only: ignored


def test_shared_dependency_applies_to_every_track():
    assert ("T1", "") in tt.node_deps(_db(), ("A", "idf"))


def test_explicit_cross_track_gate():
    deps = tt.node_deps(_db(), ("B", "zephyr"))
    assert ("G", "idf") in deps and ("T1", "") in deps


def test_derived_overall_status():
    t = _t("X", tracks=["idf", "zephyr"], track_status={"idf": "done", "zephyr": "done"})
    assert tt.derive_status(t) == "done"
    t["track_status"]["zephyr"] = "blocked"
    assert tt.derive_status(t) == "blocked"
    t["track_status"]["zephyr"] = "todo"
    assert tt.derive_status(t) == "doing"           # one board done, the other still to do
    t["track_status"]["idf"] = "todo"
    assert tt.derive_status(t) == "todo"


def test_set_on_a_two_track_ticket_needs_a_track():
    db = _db()
    with pytest.raises(ValueError, match="track"):
        tt.apply_set(db, "M", "blocked")


def test_set_updates_only_that_track_and_derives_the_ticket_status():
    db = _db()
    tt.apply_set(db, "A", "done")
    tt.apply_set(db, "M", "done", track="idf")
    m = tt.by_id(db)["M"]
    assert m["track_status"] == {"idf": "done", "zephyr": "todo"}
    assert m["status"] == "doing"


def test_set_done_refuses_when_that_tracks_dependencies_are_open():
    db = _db()
    with pytest.raises(ValueError, match="unfinished"):
        tt.apply_set(db, "M", "done", track="idf")     # (A, idf) is still todo


def test_idf_track_is_not_held_back_by_an_unfinished_zephyr_ticket():
    db = _db()
    tt.apply_set(db, "A", "done")
    tt.apply_set(db, "M", "done", track="idf")         # B (zephyr) is todo: irrelevant to the idf track


def test_zephyr_work_waits_for_the_gate():
    db = _db()
    with pytest.raises(ValueError, match="unfinished"):
        tt.apply_set(db, "B", "doing")
    tt.apply_set(db, "A", "done")
    tt.apply_set(db, "G", "done")
    tt.apply_set(db, "B", "doing")


def test_ready_nodes_are_per_track():
    db = _db()
    ready = {(t["id"], k) for t, k in tt.ready_nodes(db)}
    assert ready == {("A", "idf")}
    tt.apply_set(db, "A", "done")
    ready = {(t["id"], k) for t, k in tt.ready_nodes(db)}
    assert ready == {("G", "idf"), ("M", "idf")}       # B still waits for G; M(zephyr) waits for B


def test_check_rejects_unknown_tracks_and_a_dependency_that_can_never_apply():
    db = _db()
    assert tt.check(db) == []
    db["tickets"][1]["tracks"] = ["arm"]
    assert any("track" in e for e in tt.check(db))
    db = _db()
    db["tickets"].append(_t("X", ["B"], tracks=["idf"]))   # idf ticket depending on a zephyr-only one
    assert any("never" in e or "overlap" in e for e in tt.check(db))


def test_check_detects_a_cycle_created_by_an_explicit_gate():
    db = _db()
    tt.by_id(db)["A"]["deps_by_track"] = {"idf": ["B"]}    # A -> B -> G -> A
    assert any("cycle" in e for e in tt.check(db))


def test_track_progress_counts_shared_done_tickets_in_both_tracks():
    db = _db()
    tt.apply_set(db, "A", "done")
    assert tt.track_progress(db, "idf") == (2, 4)        # T1 + A done of T1, A, G, M
    assert tt.track_progress(db, "zephyr") == (1, 3)     # T1 done of T1, B, M


def test_per_track_gantt_orders_zephyr_after_the_idf_gate():
    sched = tt.gantt_schedule(_db(), date(2026, 9, 16), track="zephyr")
    idf = tt.gantt_schedule(_db(), date(2026, 9, 16), track="idf")
    assert sched["B"][0] >= idf["G"][1]
    assert set(sched) == {"T1", "B", "M"}
    assert set(idf) == {"T1", "A", "G", "M"}


def test_root_blockers_are_reported_per_track():
    db = _db()
    tt.by_id(db)["G"]["status"] = "blocked"
    tt.by_id(db)["A"]["status"] = "done"
    roots = tt.gantt_root_blockers(db, track="idf")
    assert [r["id"] for r in roots] == ["G"]
    assert tt.gantt_root_blockers(db, track="zephyr") == []    # G is idf-only, not part of that view


def test_gantt_text_has_one_diagram_per_track():
    text = tt.gantt_text(_db(), date(2026, 9, 16))
    assert text.count("```mermaid") == 2
    assert "IDF track" in text and "Zephyr track" in text
    assert "dateFormat YYYY-MM-DD" in text
