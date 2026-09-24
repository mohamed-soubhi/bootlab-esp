"""`canceled` status in tickets_tool.py: a canceled ticket is out of scope. It is not counted in any progress figure,
not scheduled, does not gate its dependents, and is listed in its own section with its reason and replacement."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tickets_tool as tt  # noqa: E402


def _db():
    def t(i, deps, status, **extra):
        return {"id": i, "epic": "E0", "title": f"{i} title", "size": "S", "boards": ["idf"], "deps": deps,
                "desc": "", "ac": ["x"], "status": status, "pr": "", **extra}
    return {
        "project": "p", "statuses": ["todo", "doing", "review", "blocked", "done", "canceled"],
        "sizes": {"S": "", "M": "", "L": ""},
        "epics": [{"id": "E0", "phase": "P0", "title": "Setup", "plan": ""}],
        "tickets": [
            t("BL-001", [], "done"),
            t("BL-002", ["BL-001"], "canceled", cancel_reason="host cannot be depended on", superseded_by=["BL-004"]),
            t("BL-003", ["BL-002"], "todo"),
            t("BL-004", ["BL-001"], "todo"),
        ],
    }


def test_check_accepts_canceled_status():
    assert tt.check(_db()) == []


def test_active_view_drops_canceled_tickets_and_their_dependency_edges():
    view = tt.active(_db())
    ids = [x["id"] for x in view["tickets"]]
    assert ids == ["BL-001", "BL-003", "BL-004"]
    assert next(x for x in view["tickets"] if x["id"] == "BL-003")["deps"] == []


def test_active_does_not_mutate_the_database():
    d = _db()
    tt.active(d)
    assert [x["id"] for x in d["tickets"]] == ["BL-001", "BL-002", "BL-003", "BL-004"]
    assert d["tickets"][2]["deps"] == ["BL-002"]


def test_dependent_of_a_canceled_ticket_is_not_held_up():
    ready = [x["id"] for x in tt.ready(tt.active(_db()))]
    assert "BL-003" in ready and "BL-002" not in ready


def test_apply_set_can_cancel_and_a_canceled_dep_does_not_block_doing():
    d = _db()
    d["tickets"][1]["status"] = "todo"                     # start from a live ticket
    tt.apply_set(d, "BL-002", "canceled")
    assert d["tickets"][1]["status"] == "canceled"
    tt.apply_set(d, "BL-003", "doing")                     # its only dep is canceled: must not raise
    assert d["tickets"][2]["status"] == "doing"


def test_apply_set_still_refuses_doing_when_a_live_dep_is_open():
    d = _db()
    d["tickets"].append({"id": "BL-005", "epic": "E0", "title": "t", "size": "S", "boards": ["idf"],
                         "deps": ["BL-004"], "desc": "", "ac": ["x"], "status": "todo", "pr": ""})
    with pytest.raises(ValueError):
        tt.apply_set(d, "BL-005", "doing")


def test_render_excludes_canceled_from_progress_and_lists_it_with_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(tt, "MD", tmp_path / "TICKETS.md")
    tt.render(_db())
    text = (tmp_path / "TICKETS.md").read_text(encoding="utf-8")
    assert "**1/3 done (33%)**" in text                    # 3 active tickets, not 4
    assert "🚫" in text and "## Canceled" in text
    assert "host cannot be depended on" in text
    assert "BL-004" in text.split("## Canceled")[1].split("## ")[0]      # replacement is named


def test_gantt_ignores_canceled():
    text = tt.gantt_text(tt.active(_db()))
    assert "BL-002" not in text


def test_csv_keeps_the_canceled_ticket_with_its_status(tmp_path, monkeypatch):
    monkeypatch.setattr(tt, "CSV", tmp_path / "t.csv")
    tt.to_csv(_db())
    rows = list(csv.DictReader((tmp_path / "t.csv").open(encoding="utf-8")))
    assert {r["ID"]: r["Status"] for r in rows}["BL-002"] == "canceled"
