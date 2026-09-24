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

ICON = {"todo": "⬜", "doing": "🔵", "review": "🟣", "blocked": "🟥", "done": "✅", "canceled": "🚫"}
CANCELED = "canceled"


def load():
    return json.loads(DB.read_text(encoding="utf-8"))


def save(d):
    DB.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def by_id(d):
    return {t["id"]: t for t in d["tickets"]}


def active(d):
    """View of the database without canceled tickets. A canceled ticket is out of scope: it is not counted in any
    progress figure, not scheduled, and does not gate its dependents (edges to it are dropped). The database itself
    is never modified; canceled tickets are still listed in TICKETS.md (own section) and kept in tickets.csv."""
    gone = {t["id"] for t in d["tickets"] if t["status"] == CANCELED}
    if not gone:
        return d
    kept = []
    for t in d["tickets"]:
        if t["id"] in gone:
            continue
        c = dict(t, deps=[x for x in t["deps"] if x not in gone])
        if t.get("deps_by_track"):
            c["deps_by_track"] = {k: [g for g in v if g not in gone] for k, v in t["deps_by_track"].items()}
        kept.append(c)
    return {**d, "tickets": kept}


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
    if has_tracks(d):
        _check_tracks(d, ids, errors)
    return errors


def ready(d):
    ids = by_id(d)
    return [t for t in d["tickets"]
            if t["status"] == "todo" and all(ids[x]["status"] == "done" for x in t["deps"])]


# ---------------------------------------------------------------- per-board tracks
# A ticket may be scoped per board ("tracks": ["idf", "zephyr"]) with its own status per board
# ("track_status"), its own acceptance criteria ("ac_by_track") and explicit cross-track gates
# ("deps_by_track"). A plain dependency applies to the SAME track only, so an IDF step never waits
# on a Zephyr one; a ticket without tracks is a shared prerequisite that applies to every track.
TRACKS = ("idf", "zephyr")
TRACK_NAMES = {"idf": "IDF", "zephyr": "Zephyr"}


def tracks_of(t):
    return list(t.get("tracks", []))


def has_tracks(d):
    return any(t.get("tracks") for t in d["tickets"])


def track_status(t, track):
    if len(t.get("tracks", [])) > 1 and track:
        return t.get("track_status", {}).get(track, t["status"])
    return t["status"]


def derive_status(t):
    """Overall status of a ticket from its per-board statuses."""
    sts = [track_status(t, k) for k in tracks_of(t)] or [t["status"]]
    if all(s == "done" for s in sts):
        return "done"
    if any(s == "blocked" for s in sts):
        return "blocked"
    if any(s in ("doing", "review", "done") for s in sts):
        return "doing"
    return "todo"


def node_list(t):
    """The (ticket, track) nodes a ticket is made of; a shared ticket is one node with track ''."""
    return [(t["id"], k) for k in tracks_of(t)] or [(t["id"], "")]


def node_deps(d, node):
    tid, track = node
    ids = by_id(d)
    t = ids[tid]
    out = []
    for dep in t["deps"]:
        dt = tracks_of(ids[dep])
        if not dt:
            out.append((dep, ""))
        elif not track:
            out.extend((dep, k) for k in dt)
        elif track in dt:
            out.append((dep, track))
    for dep in t.get("deps_by_track", {}).get(track, []):
        out.extend(node_list(ids[dep]))
    return list(dict.fromkeys(out))


def node_status(d, node):
    return track_status(by_id(d)[node[0]], node[1])


def ready_nodes(d):
    """(ticket, track) pairs that are todo with every dependency of that track done."""
    return [(t, node[1]) for t in d["tickets"] for node in node_list(t)
            if node_status(d, node) == "todo"
            and all(node_status(d, x) == "done" for x in node_deps(d, node))]


def _fmt_node(node):
    return f"{node[0]}[{node[1]}]" if node[1] else node[0]


def apply_set(d, tid, status, track=None, pr=None):
    """Set one ticket's status (for one board on a per-board ticket). Raises ValueError."""
    ids = by_id(d)
    if tid not in ids:
        raise ValueError(f"unknown ticket {tid}")
    if status not in d["statuses"]:
        raise ValueError(f"status must be one of {d['statuses']}")
    t = ids[tid]
    tr = tracks_of(t)
    if len(tr) > 1 and track is None:
        raise ValueError(f"{tid} has tracks {', '.join(tr)}: pass --track <{'|'.join(tr)}>")
    if track and tr and track not in tr:
        raise ValueError(f"{tid} has no track {track} (tracks: {', '.join(tr)})")
    track = track if len(tr) > 1 else (tr[0] if tr else "")
    node = (tid, track)
    if status in ("doing", "review", "done"):
        open_deps = [x for x in node_deps(d, node) if node_status(d, x) not in ("done", CANCELED)]
        if open_deps:
            raise ValueError(f"{_fmt_node(node)} depends on unfinished {[_fmt_node(x) for x in open_deps]}")
    if len(tr) > 1:
        t.setdefault("track_status", {k: t["status"] for k in tr})[track] = status
        t["status"] = derive_status(t)
    else:
        t["status"] = status
    if pr is not None:
        t["pr"] = pr


def track_progress(d, track):
    """(done, total) nodes for one board: its own nodes plus the shared prerequisites."""
    nodes = [node for t in d["tickets"] for node in node_list(t) if node[1] in ("", track)]
    return sum(node_status(d, n) == "done" for n in nodes), len(nodes)


def _check_tracks(d, ids, errors):
    for t in d["tickets"]:
        tr = tracks_of(t)
        for k in tr:
            if k not in TRACKS:
                errors.append(f"{t['id']}: unknown track {k}")
        for k, st in t.get("track_status", {}).items():
            if k not in tr:
                errors.append(f"{t['id']}: track_status for {k}, which is not one of its tracks")
            if st not in d["statuses"]:
                errors.append(f"{t['id']}: bad track status {st}")
        for k, gates in t.get("deps_by_track", {}).items():
            if k not in tr:
                errors.append(f"{t['id']}: deps_by_track for {k}, which is not one of its tracks")
            errors.extend(f"{t['id']}: unknown gate {g}" for g in gates if g not in ids)
        for dep in t["deps"]:
            dt = tracks_of(ids[dep]) if dep in ids else []
            if tr and dt and not set(tr) & set(dt):
                errors.append(f"{t['id']} depends on {dep} but their tracks never overlap "
                              "(use deps_by_track for a deliberate cross-track gate)")
    if any("unknown" in e for e in errors):
        return   # the graph walk below would fail on a missing ticket; those errors are already listed
    state = {}

    def visit(node, stack):
        if state.get(node) == 1:
            errors.append("cycle: " + " -> ".join(_fmt_node(x) for x in stack + [node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for nxt in node_deps(d, node):
            visit(nxt, stack + [node])
        state[node] = 2

    for t in d["tickets"]:
        for node in node_list(t):
            visit(node, [])


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
    canceled = [t for t in d["tickets"] if t["status"] == CANCELED]
    d = active(d)      # canceled tickets are out of scope: not counted, not scheduled (listed in their own section)
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
    w("> Plan reference: `PLAN.md`. Legend: ⬜ todo · 🔵 doing · 🟣 review · 🟥 blocked · ✅ done · 🚫 canceled (out of scope, not counted)")
    w("> **Schedule, progress and what blocks what: see [GANTT.md](GANTT.md).**\n")
    w("## Overall\n")
    w(f"`{bar(done, total, 30)}` **{done}/{total} done ({100*done//total}%)**\n")
    if has_tracks(d):
        for k in TRACKS:
            n_done, n_total = track_progress(d, k)
            w(f"- **{TRACK_NAMES[k]} track:** `{bar(n_done, n_total, 20)}` {n_done}/{n_total}")
        w("")
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

    if canceled:
        w("## Canceled (out of scope: not counted, not scheduled, do not gate anything)\n")
        w("| | ID | Title | Why | Replaced by |")
        w("|---|---|---|---|---|")
        for t in canceled:
            why = (t.get("cancel_reason") or "—").replace("|", "/")
            repl = ", ".join(t.get("superseded_by", [])) or "—"
            w(f"| {ICON[CANCELED]} | {t['id']} | {t['title']} | {why} | {repl} |")
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
            if tracks_of(t):
                w("- **Tracks:** " + " · ".join(f"{TRACK_NAMES[k]} {ICON[track_status(t, k)]} {track_status(t, k)}"
                                                for k in tracks_of(t)) + "  ")
            w(f"- **Depends on:** {', '.join(t['deps']) or '—'}  ")
            for k, gates in t.get("deps_by_track", {}).items():
                w(f"- **Cross-track gate ({TRACK_NAMES[k]}):** waits for {', '.join(gates)}  ")
            w(f"- **Plan:** {e['plan']}\n")
            w(f"{t['desc']}\n")
            w("**Acceptance criteria**")
            if t.get("ac_by_track"):
                for k in tracks_of(t):
                    tick = "x" if track_status(t, k) == "done" else " "
                    w(f"*{TRACK_NAMES[k]} scope*")
                    for a in t["ac_by_track"].get(k, []):
                        w(f"- [{tick}] {a}")
            else:
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
        wr.writerow(["ID", "Summary", "Epic", "Phase", "Size", "Boards", "Tracks", "Depends on", "Status",
                     "Track status", "Description", "Acceptance criteria"])
        for t in d["tickets"]:
            e = epics[t["epic"]]
            wr.writerow([t["id"], t["title"], f"{e['id']} {e['title']}", e["phase"], t["size"],
                         ";".join(t["boards"]), ";".join(tracks_of(t)), ";".join(t["deps"]), t["status"],
                         ";".join(f"{k}={track_status(t, k)}" for k in tracks_of(t)), t["desc"],
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


def gantt_schedule(d, start=GANTT_START, track=None):
    """Planned (start, end) per ticket: size -> days, starting after the latest dependency.
    With per-board tracks, `track` selects one board's view (its tickets plus shared ones)."""
    if has_tracks(d):
        return _tracked_schedule(d, start, track)
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


def gantt_root_blockers(d, track=None):
    """Blocked tickets with nothing unfinished beneath them: what actually gates the rest."""
    if has_tracks(d):
        return _tracked_root_blockers(d, track)
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
    if has_tracks(d):
        return _gantt_text_tracks(d, start)
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


# --- per-board view (used when tickets carry `tracks`) ---
def _view_nodes(d, track):
    return [node for t in d["tickets"] for node in node_list(t) if node[1] in ("", track)]


def _node_schedule(d, start):
    ids = by_id(d)
    memo = {}

    def plan(node):
        if node not in memo:
            begin = max((plan(x)[1] for x in node_deps(d, node)), default=start)
            memo[node] = (begin, begin + timedelta(days=GANTT_DAYS[ids[node[0]]["size"]]))
        return memo[node]

    for t in d["tickets"]:
        for node in node_list(t):
            plan(node)
    return memo


def _tracked_schedule(d, start, track):
    memo = _node_schedule(d, start)
    if track is None:
        out = {}
        for (tid, _), (b, e) in memo.items():
            ob, oe = out.get(tid, (b, e))
            out[tid] = (min(b, ob), max(e, oe))
        return out
    return {node[0]: memo[node] for node in _view_nodes(d, track)}


def _blocked_why(t):
    reason = (t.get("block_reason") or "").strip()
    if reason:
        return reason
    note = re.search(r"\[BLOCKED[:\s][^\]]*\]", t.get("desc") or "")
    return note.group(0).strip("[]") if note else ""


def _node_tag(d, node):
    t, st = by_id(d)[node[0]], node_status(d, node)
    if st == "done":
        return "done"
    if st in ("doing", "review") or (st == "blocked" and "PASS" in (t.get("block_reason") or "")):
        return "active"
    return "crit" if st == "blocked" else ""


def _tracked_root_blockers(d, track):
    ids = by_id(d)
    view = _view_nodes(d, track)
    in_view = set(view)
    direct = defaultdict(set)
    for t in d["tickets"]:
        for node in node_list(t):
            for dep in node_deps(d, node):
                direct[dep].add(node)

    def unfinished_dependents(node):
        seen, stack = set(), list(direct[node])
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(direct[cur])
        return {x for x in seen if x in in_view and node_status(d, x) != "done"}

    rows = [{"id": n[0], "title": ids[n[0]]["title"], "unblocks": len(unfinished_dependents(n)),
             "why": _blocked_why(ids[n[0]]), "track": n[1]}
            for n in view
            if node_status(d, n) == "blocked" and all(node_status(d, x) == "done" for x in node_deps(d, n))]
    return sorted(rows, key=lambda r: (-r["unblocks"], r["id"]))


def _gantt_text_tracks(d, start):
    ids = by_id(d)
    memo = _node_schedule(d, start)
    gates = [(t["id"], k, g) for t in d["tickets"] for k, g in t.get("deps_by_track", {}).items()]
    lines = [
        "# Gantt — schedule, progress and dependencies (per board)",
        "",
        "> Generated from `tickets.json` by `python3 tickets/tickets_tool.py gantt` (also refreshed by `set`).",
        "> **Do not edit.** Bar **colours are the actual status**; bar **positions are a plan** computed from ticket",
        f"> size (S=1 d, M=2 d, L=4 d) and dependencies, starting {start.isoformat()} — not a record of when work ran.",
        "> A dependency applies to the **same board only**, so an IDF step never waits on a Zephyr one.",
    ]
    for tid, k, g in gates:
        lines.append(f"> Cross-track gate: **{tid}** [{k}] waits for {', '.join(g)}.")
    lines += ["", "## Progress", ""]
    for k in TRACKS:
        n_done, n_total = track_progress(d, k)
        lines.append(f"- **{TRACK_NAMES[k]} track:** `{bar(n_done, n_total, 30)}` **{n_done}/{n_total} done**")
    lines += ["", "| Epic | Phase | " + " | ".join(TRACK_NAMES[k] for k in TRACKS) + " |",
              "|---|---|" + "---|" * len(TRACKS)]
    for e in d["epics"]:
        cells = []
        for k in TRACKS:
            nodes = [n for n in _view_nodes(d, k) if ids[n[0]]["epic"] == e["id"]]
            n_done = sum(node_status(d, n) == "done" for n in nodes)
            cells.append(f"`{bar(n_done, len(nodes), 10)}` {n_done}/{len(nodes)}" if nodes else "—")
        lines.append(f"| {e['id']} {e['title']} | {e['phase']} | " + " | ".join(cells) + " |")

    for k in TRACKS:
        name, view = TRACK_NAMES[k], _view_nodes(d, k)
        lines += ["", f"## Gantt — {name} track", "", "```mermaid", "gantt",
                  f"    title bootlab-esp — {name} track (colour = actual status, position = planned schedule)",
                  "    dateFormat YYYY-MM-DD", "    axisFormat %d %b",
                  "    todayMarker stroke-width:3px,stroke:#f80,opacity:0.7"]
        for e in d["epics"]:
            nodes = sorted((n for n in view if ids[n[0]]["epic"] == e["id"]), key=lambda n: n[0])
            if not nodes:
                continue
            lines.append("    section " + " ".join(f"{e['phase']} {e['title']}".translate(_MERMAID_BAD).split()))
            for node in nodes:
                begin, end = memo[node]
                tag = _node_tag(d, node)
                prefix = f"{tag}, " if tag else ""
                lines.append(f"    {gantt_label(ids[node[0]])} :{prefix}{gantt_id(node[0])}, "
                             f"{begin.isoformat()}, {(end - begin).days}d")
        lines += ["```", "",
                  "**Legend:** green = ✅ done · blue = 🔵 acceptance criteria pass, held only by a dependency · "
                  "red = 🟥 blocked · plain = ⬜ todo · orange line = today.",
                  "", f"### Root blockers — {name} track", ""]
        roots = _tracked_root_blockers(d, k)
        if roots:
            lines += ["| Ticket | Blocks | Why it is blocked |", "|---|---|---|"]
            lines += [f"| **{r['id']}** {gantt_label({'id': '', 'title': r['title']})} | "
                      f"{r['unblocks']} tickets | {_short(r['why']) or '—'} |" for r in roots]
        else:
            lines.append("None: nothing on this board is blocked.")
        lines += ["", f"### Ready to start — {name} track (todo, every dependency of this board done)", ""]
        ready_here = [(t, kk) for t, kk in ready_nodes(d) if kk in ("", k)]
        lines += [f"- **{t['id']}** [{t['size']}] {t['title']}" for t, _ in ready_here] or ["- none"]
        lines += ["", f"### Waiting-on — {name} track", "",
                  "| Ticket | Status | Waiting on (unfinished dependencies) |", "|---|---|---|"]
        for node in view:
            if node_status(d, node) == "done":
                continue
            st = node_status(d, node)
            waiting = [f"{_fmt_node(x)} {ICON[node_status(d, x)]}" for x in node_deps(d, node)
                       if node_status(d, x) != "done"]
            lines.append(f"| {gantt_label({'id': node[0], 'title': ids[node[0]]['title']})} | "
                         f"{ICON[st]} {st} | {', '.join(waiting) or '—'} |")
    return "\n".join(lines) + "\n"


def write_gantt(d):
    GANTT_MD.write_text(gantt_text(active(d)), encoding="utf-8")


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
    s.add_argument("--track", choices=TRACKS, default=None,
                   help="board to update on a per-board ticket (required when the ticket has two tracks)")
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
        live = active(d)
        if has_tracks(live):
            for t, k in ready_nodes(live):
                print(f"{t['id']}  [{t['size']}]  {('[' + k + '] ') if k else ''}{t['title']}")
        else:
            for t in ready(live):
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
        try:
            apply_set(d, a.id, a.status, track=a.track, pr=a.pr)
        except ValueError as err:
            sys.exit(str(err))
        save(d)
        render(d)
        write_gantt(d)
        print(f"{a.id}{('[' + a.track + ']') if a.track else ''} -> {a.status}")
    elif a.cmd == "gh":
        gh(d, a.apply)


if __name__ == "__main__":
    main()
