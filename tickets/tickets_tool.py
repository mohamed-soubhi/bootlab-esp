#!/usr/bin/env python3
"""ticket tool — single source of truth is tickets.json.

Commands
  check                      validate ids, deps, cycles
  next                       list tickets whose deps are all done and status is todo
  set <ID> <status> [--pr URL]   update a ticket, then re-render TICKETS.md
  render                     regenerate TICKETS.md (progress, diagrams, details)
  csv                        write tickets.csv (Jira / spreadsheet import)
  gh [--apply]               create GitHub labels, milestones, issues (dry-run by default)
"""
import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
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
    w("> Plan reference: `PLAN.md`. Legend: ⬜ todo · 🔵 doing · 🟣 review · 🟥 blocked · ✅ done\n")
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


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("next")
    sub.add_parser("render")
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
        print(f"{a.id} -> {a.status}")
    elif a.cmd == "gh":
        gh(d, a.apply)


if __name__ == "__main__":
    main()
