"""Tests for the Gantt generator in tickets_tool.py (pure functions, synthetic data)."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tickets_tool as tt  # noqa: E402


def _db():
    def t(i, deps, status, size="S", block=None, epic="E0"):
        return {"id": i, "epic": epic, "title": f"{i} title: with, odd; chars", "size": size,
                "boards": [], "deps": deps, "desc": "", "ac": ["x"], "status": status, "pr": "",
                **({"block_reason": block} if block else {})}
    return {
        "project": "p", "statuses": ["todo", "doing", "review", "blocked", "done"],
        "sizes": {"S": "", "M": "", "L": ""},
        "epics": [{"id": "E0", "phase": "P0", "title": "Setup", "plan": ""},
                  {"id": "E1", "phase": "P1", "title": "IDF", "plan": ""}],
        "tickets": [
            t("BL-001", [], "done"),
            t("BL-002", ["BL-001"], "done", "M"),
            t("BL-003", ["BL-002"], "blocked", "L", block="All 2 ACs PASS; waiting on dep", epic="E1"),
            t("BL-004", ["BL-003"], "todo", epic="E1"),
            t("BL-005", ["BL-001"], "blocked", block="needs hardware", epic="E1"),
            t("BL-006", ["BL-004", "BL-005"], "todo", epic="E1"),
        ],
    }


def test_ids_are_mermaid_safe():
    assert tt.gantt_id("BL-020") == "bl020"


def test_labels_drop_characters_that_break_mermaid():
    label = tt.gantt_label({"id": "BL-1", "title": "a: b, c; d # e"})
    assert not any(ch in label for ch in ":;,#")
    assert label.startswith("BL-1")


def test_schedule_starts_after_the_latest_dependency():
    sched = tt.gantt_schedule(_db(), date(2026, 9, 16))
    assert sched["BL-001"] == (date(2026, 9, 16), date(2026, 9, 17))      # S = 1 day
    assert sched["BL-002"][0] == sched["BL-001"][1]                       # after BL-001
    assert sched["BL-002"][1] == date(2026, 9, 19)                        # M = 2 days
    assert sched["BL-003"][0] == sched["BL-002"][1]
    assert sched["BL-006"][0] == max(sched["BL-004"][1], sched["BL-005"][1])


def test_every_ticket_is_scheduled_and_never_before_its_deps():
    db = _db()
    sched = tt.gantt_schedule(db, date(2026, 9, 16))
    assert set(sched) == {x["id"] for x in db["tickets"]}
    for x in db["tickets"]:
        for dep in x["deps"]:
            assert sched[x["id"]][0] >= sched[dep][1]


def test_status_tags():
    db = _db()
    by = {x["id"]: x for x in db["tickets"]}
    assert tt.gantt_tag(by["BL-001"]) == "done"
    assert tt.gantt_tag(by["BL-003"]) == "active"     # ACs pass, waiting on a dependency
    assert tt.gantt_tag(by["BL-005"]) == "crit"       # genuinely blocked
    assert tt.gantt_tag(by["BL-004"]) == ""           # todo


def test_root_blockers_are_unfinished_tickets_with_nothing_unfinished_below_them():
    roots = [r["id"] for r in tt.gantt_root_blockers(_db())]
    # BL-003 waits on done BL-002 only; BL-005 waits on done BL-001 only
    assert roots == ["BL-003", "BL-005"]


def test_root_blockers_count_what_they_unblock_transitively():
    counts = {r["id"]: r["unblocks"] for r in tt.gantt_root_blockers(_db())}
    assert counts["BL-003"] == 2      # BL-004 and BL-006 (through BL-004)
    assert counts["BL-005"] == 1      # BL-006


def test_root_blocker_reason_falls_back_to_the_blocked_note_in_desc():
    db = _db()
    for t in db["tickets"]:
        if t["id"] == "BL-005":
            t.pop("block_reason")
            t["desc"] = "Do the thing. [BLOCKED: needs the Zephyr board + throttle check] more text"
    why = {r["id"]: r["why"] for r in tt.gantt_root_blockers(db)}["BL-005"]
    assert "needs the Zephyr board" in why


def test_gantt_text_is_a_mermaid_gantt_with_every_ticket_and_a_legend():
    text = tt.gantt_text(_db(), date(2026, 9, 16))
    assert "```mermaid" in text and "\ngantt\n" in text
    assert "dateFormat YYYY-MM-DD" in text
    for i in ("bl001", "bl002", "bl003", "bl004", "bl005", "bl006"):
        assert f"{i}, 2026-" in text          # tagged ("done, bl001, 2026-..") and untagged (":bl004, 2026-..")
    assert "section P0" in text and "section P1" in text
    assert "Root blockers" in text
