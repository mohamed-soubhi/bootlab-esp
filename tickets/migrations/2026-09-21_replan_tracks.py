#!/usr/bin/env python3
"""Replan 2026-09-21 (owner decisions): finish the IDF board completely, hold a lessons-learned
retrospective, then start Zephyr.

  1. Split BL-005 and BL-014 by board with suffixes (a = IDF, b = Zephyr); numbers are not changed.
  2. Give every board-specific ticket per-board `tracks`, with its own status and acceptance
     criteria; a dependency applies to the SAME track only, so IDF work never waits on Zephyr.
  3. Re-point dependencies: IDF work depends on the "a" parts, Zephyr work on the "b" parts.
  4. New tickets (suffixed): BL-056a IDF re-run on the RPi4, BL-063a lessons learned,
     BL-063b HTML presentation. Zephyr work is gated behind BL-063b (explicit deps_by_track).

Idempotent: does nothing if BL-005a already exists. Statuses are NOT changed here; closing the
IDF tickets is done afterwards with `tickets_tool.py set` so each step is checked against its
dependencies.
"""
import json
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "tickets.json"
GATE = "BL-063b"          # everything Zephyr waits for: IDF soak, docs, lessons, presentation

IDF_ONLY = ["BL-020", "BL-021", "BL-022", "BL-023", "BL-024", "BL-025", "BL-026", "BL-027", "BL-028", "BL-043"]
ZEPHYR_ONLY = ["BL-030", "BL-031", "BL-032", "BL-033", "BL-034", "BL-035", "BL-036", "BL-044"]

# Per-board acceptance criteria for the tickets that cover both boards (faithful restrictions
# of the original criteria; the original `ac` is kept).
AC_BY_TRACK = {
    "BL-041": {"idf": ["identify maps the idf board (LABID uid matches rig.yaml)", "measure within ± 1 toggle over 5 s on the idf board"],
               "zephyr": ["identify maps the zephyr board", "measure within ± 1 toggle over 5 s on the zephyr board"]},
    "BL-042": {"idf": ["Factory flash the idf board", "Refuses to flash if board= mismatches"],
               "zephyr": ["Factory flash the zephyr board", "Refuses to flash if board= mismatches"]},
    "BL-045": {"idf": ["Builds all 5 IDF images (v1, v2, no_confirm, hang, bad_sig)"],
               "zephyr": ["Builds all 5 Zephyr images (v1, v2, no_confirm, hang, bad_sig)"]},
    "BL-046": {"idf": ["Line coverage ≥ 80 % on the IDF-path modules", "ruff + mypy clean"],
               "zephyr": ["Line coverage ≥ 80 % on the Zephyr-path modules", "ruff + mypy clean"]},
    "BL-050": {"idf": ["Dummy HIL test runs on the idf board and restores v1"],
               "zephyr": ["Dummy HIL test runs on the zephyr board and restores v1"]},
    "BL-051": {"idf": ["Green on the idf board for both transports (ble, wifi)"],
               "zephyr": ["Green on the zephyr board for both transports (ble, udp)"]},
    "BL-052": {"idf": ["Green on the idf board for every transport"], "zephyr": ["Green on the zephyr board for every transport"]},
    "BL-053": {"idf": ["All green on the idf board"], "zephyr": ["All green on the zephyr board"]},
    "BL-054": {"idf": ["Recovers every run on the idf board, or skipped if no hub"],
               "zephyr": ["Recovers every run on the zephyr board, or skipped if no hub"]},
    "BL-055": {"idf": ["Green on main for the IDF build", "Signed IDF artifacts uploaded"],
               "zephyr": ["Green on main for the Zephyr build", "Signed Zephyr artifacts uploaded"]},
    "BL-056": {"idf": ["HIL job runs on PR for the idf board", "Runner has no sudo and no access to keys/"],
               "zephyr": ["HIL job runs on PR for the zephyr board"]},
    "BL-057": {"idf": ["3 consecutive green runs on the idf board", "Runtime documented"],
               "zephyr": ["3 consecutive green runs on the zephyr board"]},
    "BL-060": {"idf": ["Pass rate ≥ 99 % on the idf board (ble + wifi)", "Root cause logged for every failure"],
               "zephyr": ["Pass rate ≥ 99 % on the zephyr board (ble + udp)", "Root cause logged for every failure"]},
    "BL-061": {"idf": ["Fresh clone reaches T02 green on the idf board following README only"],
               "zephyr": ["Fresh clone reaches T02 green on the zephyr board following README only"]},
    "BL-062": {"idf": ["Recovery tested once for the idf board from the docs"],
               "zephyr": ["Recovery tested once for the zephyr board from the docs"]},
    "BL-063": {"idf": ["PLAN.md matches the delivered IDF work"], "zephyr": ["PLAN.md matches the delivered Zephyr work"]},
}
# Their Zephyr halves need Zephyr firmware; the tickets themselves said so (BL-041/042 descs).
EXTRA_DEPS = {"BL-041": ["BL-031", "BL-032"], "BL-042": ["BL-030", "BL-031"]}


def ticket(tid, epic, title, size, boards, tracks, deps, desc, ac, status="todo", **extra):
    t = {"id": tid, "epic": epic, "title": title, "size": size, "boards": boards, "tracks": tracks,
         "deps": deps, "desc": desc, "ac": ac, "status": status, "pr": ""}
    t.update(extra)
    return t


def split_tickets(d):
    ids = {t["id"]: t for t in d["tickets"]}
    old5, old14 = ids["BL-005"], ids["BL-014"]
    new = {
        "BL-005": [
            ticket("BL-005a", "E0", "Detect board hardware → rig.yaml (IDF board)", "S", ["idf"], ["idf"], ["BL-003"],
                   "Split from BL-005 on 2026-09-21 (replan: IDF first). DONE with evidence in "
                   "scripts/evidence/bl005_hardware_detection.md: idf led_gpio=48 confirmed by a real blink (BL-020, PLAN R14); "
                   "flash 16 MB quad; PSRAM 8 MB OCTAL run-tested (octal_psram driver, 'Found 8MB PSRAM device', memory test OK); "
                   "host/config/rig.yaml idf entry filled. HISTORY (original BL-005): " + old5_desc(old5),
                   ["host/config/rig.yaml filled for the idf board", "LED GPIO confirmed by a quick blink (idf board)"],
                   status="done"),
            ticket("BL-005b", "E2", "Detect board hardware → rig.yaml (Zephyr board)", "S", ["zephyr"], ["zephyr"], ["BL-003"],
                   "Split from BL-005 on 2026-09-21. REMAINING: the zephyr board's led_gpio (needs a blink app on that board, "
                   "i.e. writing its flash; backup backups/esp_ACA7042C3B04.bin + .sha256; identity AC:A7:04:2C:3B:04) and the run-test "
                   "of its PSRAM mode (octal is INFERRED from eFuses identical to the idf board's). Gated behind the IDF track "
                   f"({GATE}); an IDF blink build is enough, no Zephyr toolchain needed.",
                   ["host/config/rig.yaml filled for the zephyr board", "LED GPIO confirmed by a quick blink (zephyr board)"],
                   deps_by_track={"zephyr": [GATE]}),
        ],
        "BL-014": [
            ticket("BL-014a", "E0", "Packaging: IDF component (linux target)", "S", ["common"], ["idf"], ["BL-010"],
                   "Split from BL-014 on 2026-09-21. DONE: scripts/idf_linux_test.sh builds the packaged labid component "
                   "(labid.c + labid_dispatch.c) for the ESP-IDF linux target and runs the smoke test (0 warnings, exit 0). "
                   "HISTORY (original BL-014): " + old14["desc"],
                   ["Builds for the IDF linux target"], status="done"),
            ticket("BL-014b", "E2", "Packaging: Zephyr module (native_sim)", "S", ["common", "zephyr"], ["zephyr"], ["BL-010"],
                   "Split from BL-014 on 2026-09-21. REMAINING: build the labid Zephyr module for native_sim. Also verifies the "
                   "Zephyr branch of common/labid/CMakeLists.txt, which gained labid_dispatch.c (BL-022) and has never been built. "
                   f"Zephyr hold applies; gated behind the IDF track ({GATE}).",
                   ["Builds for Zephyr native_sim"], deps_by_track={"zephyr": [GATE]}),
        ],
    }
    out = []
    for t in d["tickets"]:
        out.extend(new.get(t["id"], [t]))
    d["tickets"] = out
    return {"BL-005": ("BL-005a", "BL-005b"), "BL-014": ("BL-014a", "BL-014b")}


def old5_desc(t):
    return t["desc"]


def add_tracks(d):
    ids = {t["id"]: t for t in d["tickets"]}
    for tid in IDF_ONLY:
        ids[tid]["tracks"] = ["idf"]
    for tid in ZEPHYR_ONLY:
        ids[tid]["tracks"] = ["zephyr"]
    for tid, by_board in AC_BY_TRACK.items():
        t = ids[tid]
        t["tracks"] = ["idf", "zephyr"]
        t["ac_by_track"] = by_board
        t["track_status"] = {"idf": "todo", "zephyr": "todo"}    # BL-041's old 'blocked' was about missing firmware
        t["deps"] = list(dict.fromkeys(t["deps"] + EXTRA_DEPS.get(tid, [])))
        t["status"] = "todo"
    ids["BL-030"]["deps_by_track"] = {"zephyr": [GATE]}


def repoint(d, renamed):
    ids = {t["id"]: t for t in d["tickets"]}
    for t in d["tickets"]:
        new_deps = []
        for dep in t["deps"]:
            if dep in renamed:
                idf_part, zephyr_part = renamed[dep]
                new_deps.append(zephyr_part if t.get("tracks") == ["zephyr"] else idf_part)
            else:
                new_deps.append(dep)
        t["deps"] = list(dict.fromkeys(new_deps))
    # the IDF tickets were kept "blocked" only by the Zephyr-gated halves: drop the stale reasons
    for tid in IDF_ONLY[:-1]:
        ids[tid].pop("block_reason", None)
        ids[tid]["desc"] += (" [REPLAN 2026-09-21: its dependencies BL-005/BL-014 were split by board; the IDF parts are "
                             "done, so nothing holds this ticket any more. Acceptance evidence is listed above.]")


def add_new(d):
    def insert_after(anchor, items):
        pos = next(i for i, t in enumerate(d["tickets"]) if t["id"] == anchor)
        d["tickets"][pos + 1:pos + 1] = items

    insert_after("BL-056", [ticket(
        "BL-056a", "E4", "IDF acceptance re-run on the RPi4 (OTA-programming host)", "M", ["host", "idf"], ["idf"],
        ["BL-043", "BL-056"],
        "Owner decision 2026-09-21: development stays on the current machine (WSL2 + Windows-native tools); the RPi4 has "
        "limitations and is used for OTA programming. When the IDF track is done, re-run the IDF acceptance from the RPi4. "
        "Builds stay on the development machine / CI; the RPi4 programs and verifies the boards.",
        ["labflash update idf --transport ble and wifi both succeed from the RPi4",
         "LABID VER? and identity verified from the RPi4 after each update",
         "RPi4 limitations documented (what runs there, what stays on the dev machine or CI)"])])
    insert_after("BL-063", [
        ticket("BL-063a", "E5", "IDF lessons learned (retrospective)", "S", ["host"], ["idf"],
               ["BL-060", "BL-061", "BL-062", "BL-063", "BL-056a"],
               "Retrospective after the IDF board is complete, BEFORE any Zephyr work starts, so what the IDF track taught "
               "shapes the Zephyr plan (PLAN R13/R14/R15, USB reset behaviour, vacuous evidence, optional subsystems, ...).",
               ["docs/LESSONS_LEARNED.md covers every risk R1–R15 outcome and every trap found during the IDF track",
                "Every lesson has an action: a plan change, a tool change or a checklist item", "Owner review recorded"]),
        ticket("BL-063b", "E5", "HTML presentation of the IDF track", "M", ["host"], ["idf"], ["BL-063a"],
               "Owner deliverable: a presentation of the finished IDF track. Completing it is what releases the Zephyr track "
               f"(explicit gate {GATE}).",
               ["One self-contained HTML deck: architecture, flows, evidence, lessons learned, Gantt",
                "Every claim links to an evidence file in the repo", "Opens and renders offline in a browser"])])


def main():
    d = json.loads(DB.read_text(encoding="utf-8"))
    if any(t["id"] == "BL-005a" for t in d["tickets"]):
        print("already applied")
        return
    renamed = split_tickets(d)
    add_tracks(d)
    repoint(d, renamed)
    add_new(d)
    DB.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"replan applied: {len(d['tickets'])} tickets")


if __name__ == "__main__":
    main()
