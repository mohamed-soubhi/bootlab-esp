#!/usr/bin/env python3
"""ticket tool — single source of truth is tickets.json.

Commands
  check                      validate ids, deps, cycles
  next                       list tickets whose deps are all done and status is todo
  set <ID> <status> [--pr URL]   update a ticket, then re-render TICKETS.md
  render                     regenerate TICKETS.md (progress, diagrams, details)
  gantt                      regenerate GANTT.md (Gantt, progress, root blockers, waiting-on table)
  csv                        write tickets.csv (Jira / spreadsheet import)
  gh [--apply]               create GitHub labels, milestones, issues (dry-run by default)
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "tickets.json"
MD = HERE / "TICKETS.md"
CSV = HERE / "tickets.csv"

ICON = {"todo": "⬜", "doing": "🔵", "review": "🟣", "blocked": "🟥", "done": "✅"}


def load():
    return json.loads(DB.read_text(encoding="utf-8"))


def save(d):
    DB.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def by_id(d):
    return {t["id"]: t for t in d["tickets"]}


def check(d):
    ids = by_id(d)
    errors = []
    epics = {e["id"] for e in d["epics"]}
    for t in d["tickets"]:
        if t["epic"] not in epics:
            errors.append(f"{t['id']}: unknown epic {t['epic']}")
        if t["status"] not in d["statuses"]:
            errors.append(f"{t['id']}: bad status {t['status']}")
        for dep in t["deps"]:
            if dep not in ids:
                errors.append(f"{t['id']}: unknown dep {dep}")
    # cycle detection
    state = {}

    def visit(n, stack):
        if state.get(n) == 1:
            errors.append("cycle: " + " -> ".join(stack + [n]))
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for dep in ids[n]["deps"]:
            if dep in ids:
                visit(dep, stack + [n])
        state[n] = 2

    for n in ids:
        visit(n, [])
    return errors


def ready(d):
    ids = by_id(d)
    return [t for t in d["tickets"]
            if t["status"] == "todo" and all(ids[x]["status"] == "done" for x in t["deps"])]


def bar(done, total, width=20):
    filled = round(width * done / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def epic_status(ts):
    s = [t["status"] for t in ts]
    if all(x == "done" for x in s):
        return "done"
    if any(x == "blocked" for x in s):
        return "blocked"
    if any(x in ("doing", "review", "done") for x in s):
        return "doing"
    return "todo"


def render(d):
    ids = by_id(d)
    per_epic = defaultdict(list)
    for t in d["tickets"]:
        per_epic[t["epic"]].append(t)
    total = len(d["tickets"])
    done = sum(t["status"] == "done" for t in d["tickets"])
    counts = defaultdict(int)
    for t in d["tickets"]:
        counts[t["status"]] += 1

    out = []
    w = out.append
    w(f"# {d['project']} — Tickets & Progress\n")
    w("> Generated from `tickets.json` by `tickets_tool.py render`. **Do not edit by hand.**")
    w("> Plan reference: `PLAN.md`. Legend: ⬜ todo · 🔵 doing · 🟣 review · 🟥 blocked · ✅ done")
    w("> **Schedule, progress and what blocks what: see [GANTT.md](GANTT.md).**\n")
    w("## Overall\n")
    w(f"`{bar(done, total, 30)}` **{done}/{total} done ({100*done//total}%)**\n")
    w("```mermaid")
    w("pie showData title Ticket status")
    for s in d["statuses"]:
        if counts[s]:
            w(f'    "{s}" : {counts[s]}')
    w("```\n")

    w("## Epics\n")
    w("| Epic | Phase | Title | Progress | Done | Status | Plan |")
    w("|---|---|---|---|---|---|---|")
    for e in d["epics"]:
        ts = per_epic[e["id"]]
        dn = sum(t["status"] == "done" for t in ts)
        st = epic_status(ts)
        w(f"| {e['id']} | {e['phase']} | {e['title']} | `{bar(dn, len(ts), 12)}` | {dn}/{len(ts)} | {ICON[st]} {st} | {e['plan']} |")
    w("")

    # epic dependency graph
    edges = set()
    for t in d["tickets"]:
        for dep in t["deps"]:
            a, b = ids[dep]["epic"], t["epic"]
            if a != b:
                edges.add((a, b))
    w("## Epic dependency graph\n")
    w("```mermaid")
    w("flowchart LR")
    for e in d["epics"]:
        ts = per_epic[e["id"]]
        dn = sum(t["status"] == "done" for t in ts)
        w(f'    {e["id"]}["{e["phase"]} {e["title"]}<br/>{dn}/{len(ts)}"]:::{epic_status(ts)}')
    # keep graph readable: drop edges implied transitively
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)

    def reach(a, b, skip):
        stack, seen = [a], set()
        while stack:
            n = stack.pop()
            for m in adj[n]:
                if (n, m) == skip or m in seen:
                    continue
                if m == b:
                    return True
                seen.add(m)
                stack.append(m)
        return False

    for a, b in sorted(edges):
        if not reach(a, b, (a, b)):
            w(f"    {a} --> {b}")
    w("    classDef todo fill:#eeeeee,stroke:#999,color:#333")
    w("    classDef doing fill:#cfe3ff,stroke:#2f6fdb,color:#123")
    w("    classDef blocked fill:#ffd6d6,stroke:#c62828,color:#400")
    w("    classDef done fill:#d4f5d4,stroke:#2e7d32,color:#132")
    w("```\n")

    w("## Ready to start now\n")
    r = ready(d)
    if r:
        for t in r:
            w(f"- **{t['id']}** {t['title']} ({t['size']}) — {t['epic']}")
    else:
        w("- Nothing ready (check blocked tickets).")
    blocked = [t for t in d["tickets"] if t["status"] == "blocked"]
    if blocked:
        w("\n## Blocked\n")
        for t in blocked:
            w(f"- 🟥 **{t['id']}** {t['title']} {('— ' + t['pr']) if t['pr'] else ''}")
    w("")

    w("## Tickets by epic\n")
    for e in d["epics"]:
        ts = per_epic[e["id"]]
        w(f"### {e['id']} · {e['phase']} — {e['title']}\n")
        w("| | ID | Title | Size | Boards | Depends on | PR |")
        w("|---|---|---|---|---|---|---|")
        for t in ts:
            deps = ", ".join(t["deps"]) or "—"
            pr = f"[link]({t['pr']})" if t["pr"] else ""
            w(f"| {ICON[t['status']]} | {t['id']} | {t['title']} | {t['size']} | {', '.join(t['boards'])} | {deps} | {pr} |")
        w("")
        for t in ts:
            chk = "x" if t["status"] == "done" else " "
            w(f"<details><summary>{ICON[t['status']]} <b>{t['id']}</b> — {t['title']}</summary>\n")
            w(f"- **Size:** {t['size']} ({d['sizes'][t['size']]})  ")
            w(f"- **Boards:** {', '.join(t['boards'])}  ")
            w(f"- **Depends on:** {', '.join(t['deps']) or '—'}  ")
            w(f"- **Plan:** {e['plan']}\n")
            w(f"{t['desc']}\n")
            w("**Acceptance criteria**")
            for a in t["ac"]:
                w(f"- [{chk}] {a}")
            w("\n</details>\n")

    w("## Full ticket dependency graph\n")
    w("<details><summary>Show graph</summary>\n")
    w("```mermaid")
    w("flowchart TB")
    for e in d["epics"]:
        w(f'    subgraph {e["id"]}_g["{e["phase"]} {e["title"]}"]')
        for t in per_epic[e["id"]]:
            nid = t["id"].replace("-", "")
            w(f'        {nid}["{t["id"]}"]:::{t["status"] if t["status"] != "review" else "doing"}')
        w("    end")
    for t in d["tickets"]:
        for dep in t["deps"]:
            w(f'    {dep.replace("-", "")} --> {t["id"].replace("-", "")}')
    w("    classDef todo fill:#eeeeee,stroke:#999,color:#333")
    w("    classDef doing fill:#cfe3ff,stroke:#2f6fdb,color:#123")
    w("    classDef blocked fill:#ffd6d6,stroke:#c62828,color:#400")
    w("    classDef done fill:#d4f5d4,stroke:#2e7d32,color:#132")
    w("```\n")
    w("</details>\n")

    w("## Workflow rules for the agent\n")
    w("1. Pick only tickets from **Ready to start now**.")
    w("2. `python3 tickets_tool.py set BL-xxx doing` when starting.")
    w("3. One branch + one PR per ticket: `bl-xxx-short-title`. PR body copies the acceptance criteria with evidence.")
    w("4. `set BL-xxx review --pr <url>` when the PR is open; `set BL-xxx done` after merge.")
    w("5. `set BL-xxx blocked --pr <issue-or-note-url>` when an ESCALATE condition triggers; stop and ask the owner.")
    w("6. Commit `tickets.json` and `TICKETS.md` together with each status change.")
    MD.write_text("\n".join(out) + "\n", encoding="utf-8")


def to_csv(d):
    epics = {e["id"]: e for e in d["epics"]}
    with CSV.open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["ID", "Summary", "Epic", "Phase", "Size", "Boards", "Depends on", "Status", "Description", "Acceptance criteria"])
        for t in d["tickets"]:
            e = epics[t["epic"]]
            wr.writerow([t["id"], t["title"], f"{e['id']} {e['title']}", e["phase"], t["size"],
                         ";".join(t["boards"]), ";".join(t["deps"]), t["status"], t["desc"],
                         " | ".join(t["ac"])])


def gh(d, apply):
    epics = {e["id"]: e for e in d["epics"]}

    def run(cmd):
        print("$ " + " ".join(cmd))
        if apply:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 and "already exists" not in res.stderr:
                print(res.stderr.strip(), file=sys.stderr)
            return res.stdout
        return ""

    labels = {f"size:{s}" for s in d["sizes"]}
    labels |= {f"board:{b}" for t in d["tickets"] for b in t["boards"]}
    labels |= {f"epic:{e['id']}" for e in d["epics"]}
    for lb in sorted(labels):
        run(["gh", "label", "create", lb, "--force"])
    for e in d["epics"]:
        run(["gh", "api", "repos/{owner}/{repo}/milestones", "-f", f"title={e['phase']} {e['title']}"])
    existing = ""
    if apply:
        existing = subprocess.run(["gh", "issue", "list", "--state", "all", "--limit", "500",
                                   "--json", "title", "-q", ".[].title"],
                                  capture_output=True, text=True).stdout
    for t in d["tickets"]:
        title = f"[{t['id']}] {t['title']}"
        if title in existing:
            print(f"skip existing {t['id']}")
            continue
        e = epics[t["epic"]]
        body = (f"**Epic:** {e['id']} {e['title']} ({e['phase']})  \n**Plan:** {e['plan']}  \n"
                f"**Size:** {t['size']}  \n**Depends on:** {', '.join(t['deps']) or '—'}\n\n"
                f"{t['desc']}\n\n### Acceptance criteria\n" + "\n".join(f"- [ ] {a}" for a in t["ac"]))
        cmd = ["gh", "issue", "create", "--title", title, "--body", body,
               "--milestone", f"{e['phase']} {e['title']}",
               "--label", ",".join([f"epic:{e['id']}", f"size:{t['size']}"] + [f"board:{b}" for b in t["boards"]])]
        run(cmd)
    if not apply:
        print("\nDry run only. Re-run with --apply inside the repo to create them.")


# ---------------------------------------------------------------- Gantt (GANTT.md)
GANTT_MD = HERE / "GANTT.md"
GANTT_START = date(2026, 9, 16)            # first commit of the project
GANTT_DAYS = {"S": 1, "M": 2, "L": 4}      # tickets.json sizes: <=0.5 d, 1-2 d, 3-5 d
GANTT_LABEL_MAX = 52
_MERMAID_BAD = str.maketrans({":": " ", ";": " ", ",": " ", "#": " "})


def gantt_id(tid):
    return tid.lower().replace("-", "")


def gantt_label(t):
    text = " ".join(f"{t['id']} {t['title']}".translate(_MERMAID_BAD).split())
    return text[:GANTT_LABEL_MAX].rstrip()


def _acs_pass(t):
    """A blocked ticket whose own acceptance criteria are already met (only a dependency holds it)."""
    return t["status"] == "blocked" and "PASS" in (t.get("block_reason") or "")


def gantt_tag(t):
    if t["status"] == "done":
        return "done"
    if _acs_pass(t) or t["status"] in ("doing", "review"):
        return "active"
    if t["status"] == "blocked":
        return "crit"
    return ""


def gantt_schedule(d, start=GANTT_START):
    """Planned (start, end) per ticket: size -> days, starting after the latest dependency."""
    ids = by_id(d)
    memo = {}

    def plan(tid):
        if tid not in memo:
            t = ids[tid]
            begin = max((plan(x)[1] for x in t["deps"]), default=start)
            memo[tid] = (begin, begin + timedelta(days=GANTT_DAYS[t["size"]]))
        return memo[tid]

    for tid in ids:
        plan(tid)
    return memo


def _unfinished_dependents(d):
    """id -> set of unfinished tickets that depend on it, directly or transitively."""
    direct = defaultdict(set)
    for t in d["tickets"]:
        for dep in t["deps"]:
            direct[dep].add(t["id"])
    ids = by_id(d)
    out = {}
    for tid in ids:
        seen, stack = set(), list(direct[tid])
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(direct[cur])
        out[tid] = {x for x in seen if ids[x]["status"] != "done"}
    return out


def gantt_root_blockers(d):
    """Blocked tickets with nothing unfinished beneath them: what actually gates the rest."""
    ids = by_id(d)
    downstream = _unfinished_dependents(d)
    roots = [t for t in d["tickets"] if t["status"] == "blocked"
             and all(ids[x]["status"] == "done" for x in t["deps"])]
    def why(t):
        reason = (t.get("block_reason") or "").strip()
        if reason:
            return reason
        note = re.search(r"\[BLOCKED[:\s][^\]]*\]", t.get("desc") or "")   # older tickets keep it in desc
        return note.group(0).strip("[]") if note else ""

    rows = [{"id": t["id"], "title": t["title"], "unblocks": len(downstream[t["id"]]),
             "why": why(t)} for t in roots]
    return sorted(rows, key=lambda r: (-r["unblocks"], r["id"]))


def _short(text, n=150):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def gantt_text(d, start=GANTT_START):
    ids = by_id(d)
    sched = gantt_schedule(d, start)
    total = len(d["tickets"])
    done = [t for t in d["tickets"] if t["status"] == "done"]
    waiting = [t for t in d["tickets"] if _acs_pass(t)]
    blocked = [t for t in d["tickets"] if t["status"] == "blocked" and not _acs_pass(t)]
    todo = [t for t in d["tickets"] if t["status"] == "todo"]
    lines = [
        "# Gantt — schedule, progress and dependencies",
        "",
        "> Generated from `tickets.json` by `python3 tickets/tickets_tool.py gantt` (also refreshed by `set`).",
        "> **Do not edit.** Bar **colours are the actual status**; bar **positions are a plan** computed from ticket",
        f"> size (S=1 d, M=2 d, L=4 d) and dependencies, starting {start.isoformat()} — not a record of when work ran.",
        "",
        "## Progress",
        "",
        f"`{bar(len(done), total, 30)}` **{len(done)}/{total} done**",
        "",
        f"- ✅ done: **{len(done)}**",
        f"- 🔵 acceptance criteria PASS, waiting only on a dependency: **{len(waiting)}**",
        f"- 🟥 blocked, work outstanding: **{len(blocked)}**",
        f"- ⬜ todo: **{len(todo)}**",
        "",
        "| Epic | Phase | Progress | Done | State |",
        "|---|---|---|---|---|",
    ]
    for e in d["epics"]:
        ts = [t for t in d["tickets"] if t["epic"] == e["id"]]
        n_done = sum(t["status"] == "done" for t in ts)
        lines.append(f"| {e['id']} {e['title']} | {e['phase']} | `{bar(n_done, len(ts), 12)}` | "
                     f"{n_done}/{len(ts)} | {ICON[epic_status(ts)]} {epic_status(ts)} |")
    lines += [
        "",
        "## Gantt",
        "",
        "```mermaid",
        "gantt",
        "    title bootlab-esp — tickets (colour = actual status, position = planned schedule)",
        "    dateFormat YYYY-MM-DD",
        "    axisFormat %d %b",
        "    todayMarker stroke-width:3px,stroke:#f80,opacity:0.7",
    ]
    for e in d["epics"]:
        title = " ".join(f"{e['phase']} {e['title']}".translate(_MERMAID_BAD).split())
        lines.append(f"    section {title}")
        for t in sorted((x for x in d["tickets"] if x["epic"] == e["id"]), key=lambda x: x["id"]):
            begin, end = sched[t["id"]]
            tag = gantt_tag(t)
            prefix = f"{tag}, " if tag else ""
            lines.append(f"    {gantt_label(t)} :{prefix}{gantt_id(t['id'])}, {begin.isoformat()}, {(end - begin).days}d")
    lines += [
        "```",
        "",
        "**Legend:** grey/green = ✅ done · blue = 🔵 acceptance criteria pass, held only by a dependency · "
        "red = 🟥 blocked · plain = ⬜ todo · orange line = today.",
        "",
        "## Root blockers — what actually gates the rest",
        "",
        "Blocked tickets with **nothing unfinished beneath them**. Finishing (or explicitly re-scoping) these is what "
        "moves the blue tickets to done.",
        "",
        "| Ticket | Blocks | Why it is blocked |",
        "|---|---|---|",
    ]
    for r in gantt_root_blockers(d):
        lines.append(f"| **{r['id']}** {gantt_label({'id': '', 'title': r['title']})} | "
                     f"{r['unblocks']} tickets | {_short(r['why']) or '—'} |")
    lines += ["", "## Ready to start (todo, every dependency done)", ""]
    ready_now = ready(d)
    lines += [f"- **{t['id']}** [{t['size']}] {t['title']}" for t in ready_now] or ["- none"]
    lines += ["", "## Waiting-on table", "",
              "| Ticket | Status | Waiting on (unfinished dependencies) |", "|---|---|---|"]
    for t in d["tickets"]:
        if t["status"] == "done":
            continue
        open_deps = [f"{x} {ICON[ids[x]['status']]}" for x in t["deps"] if ids[x]["status"] != "done"]
        lines.append(f"| {t['id']} {gantt_label({'id': '', 'title': t['title']})} | "
                     f"{ICON[t['status']]} {t['status']} | {', '.join(open_deps) or '—'} |")
    return "\n".join(lines) + "\n"


def write_gantt(d):
    GANTT_MD.write_text(gantt_text(d), encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("next")
    sub.add_parser("render")
    sub.add_parser("gantt")
    sub.add_parser("csv")
    s = sub.add_parser("set")
    s.add_argument("id")
    s.add_argument("status")
    s.add_argument("--pr", default=None)
    g = sub.add_parser("gh")
    g.add_argument("--apply", action="store_true")
    a = p.parse_args()

    d = load()
    errs = check(d)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        sys.exit(1)

    if a.cmd == "check":
        print(f"OK: {len(d['tickets'])} tickets, {len(d['epics'])} epics, no dependency errors")
    elif a.cmd == "next":
        for t in ready(d):
            print(f"{t['id']}  [{t['size']}]  {t['title']}")
    elif a.cmd == "render":
        render(d)
        print(f"wrote {MD.name}")
    elif a.cmd == "gantt":
        write_gantt(d)
        print(f"wrote {GANTT_MD.name}")
    elif a.cmd == "csv":
        to_csv(d)
        print(f"wrote {CSV.name}")
    elif a.cmd == "set":
        ids = by_id(d)
        if a.id not in ids:
            sys.exit(f"unknown ticket {a.id}")
        if a.status not in d["statuses"]:
            sys.exit(f"status must be one of {d['statuses']}")
        t = ids[a.id]
        if a.status in ("doing", "review", "done"):
            open_deps = [x for x in t["deps"] if ids[x]["status"] != "done"]
            if open_deps:
                sys.exit(f"{a.id} depends on unfinished {open_deps}")
        t["status"] = a.status
        if a.pr is not None:
            t["pr"] = a.pr
        save(d)
        render(d)
        write_gantt(d)
        print(f"{a.id} -> {a.status}")
    elif a.cmd == "gh":
        gh(d, a.apply)


if __name__ == "__main__":
    main()
