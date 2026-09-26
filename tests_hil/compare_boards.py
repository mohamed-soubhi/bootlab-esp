"""BL-072: compare two soak runs (one per board) and flag board-to-board differences.

Pure data: both runs are read from disk (`report.json` + `cycles.jsonl`), summarized, and compared per (transport, kind),
so a board that is slower or that disagrees on outcomes can be named without a board in the loop.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, TypedDict

_RATIO_UNCOMPARABLE = float("inf")


class Run(TypedDict):
    """One run directory: its report, the latest record per cycle, and the warm-up records."""

    report: dict[str, Any]
    cycles: dict[int, dict[str, Any]]
    warmup: list[dict[str, Any]]


class DurationDiff(TypedDict):
    """Median duration of one (transport, kind) pair on both boards, and whether it is outside tolerance."""

    transport: str
    kind: str
    a_median: float
    b_median: float
    ratio: float
    flagged: bool


def load_run(path: Path) -> Run:
    """Read a run directory; a re-run of a cycle supersedes the earlier record for that cycle."""
    report = json.loads((path / "report.json").read_text(encoding="utf-8"))
    cycles: dict[int, dict[str, Any]] = {}
    warmup: list[dict[str, Any]] = []
    for line in (path / "cycles.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "cycle" not in rec:
            continue
        if rec["cycle"] == 0:
            warmup.append(rec)
        else:
            cycles[rec["cycle"]] = rec
    return {"report": report, "cycles": cycles, "warmup": warmup}


def summarize(run: Run) -> dict[str, Any]:
    """Cycle count, pass rate, infra retries, the failures, and the median duration per (transport, kind)."""
    records = [run["cycles"][n] for n in sorted(run["cycles"])]
    passes = sum(1 for r in records if r["ok"])
    durations: dict[tuple[str, str], list[float]] = {}
    for r in records:
        durations.setdefault((r["transport"], r["kind"]), []).append(r["duration_s"])
    return {
        "cycles": len(records),
        "passes": passes,
        "pass_rate_pct": round(passes / len(records) * 100.0, 2) if records else 0.0,
        "infra_retries": sum(r.get("infra_retries", 0) for r in records),
        "failures": [
            {"cycle": r["cycle"], "image": r["image"], "transport": r["transport"], "cause": r["cause"]}
            for r in records
            if not r["ok"]
        ],
        "median_s": {key: statistics.median(values) for key, values in durations.items()},
    }


def compare(a: Run, b: Run, tolerance: float = 0.25) -> dict[str, Any]:
    """Compare two runs: the plan, the per-cycle outcomes, the durations, and the flags a human should read."""
    summary_a, summary_b = summarize(a), summarize(b)
    comparison: dict[str, Any] = {
        "plan_identical": a["report"].get("plan") == b["report"].get("plan"),
        "cycle_agreement": None,
        "duration_diffs": _duration_diffs(summary_a, summary_b, tolerance),
        "summary": {"a": summary_a, "b": summary_b},
    }
    if comparison["plan_identical"]:
        comparison["cycle_agreement"] = _agreement(a, b)
    comparison["flags"] = _flags(comparison)
    return comparison


def render_markdown(comparison: dict[str, Any], names: tuple[str, str] = ("board 1", "board 2")) -> str:
    """A markdown report: the two names, the summary and duration tables, then the flags as a bullet list."""
    summary_a, summary_b = comparison["summary"]["a"], comparison["summary"]["b"]
    lines = [
        "# Soak comparison",
        "",
        f"{names[0]} vs {names[1]}",
        "",
        "## Summary",
        "",
        f"| metric | {names[0]} | {names[1]} |",
        "| --- | --- | --- |",
        f"| Pass rate (%) | {summary_a['pass_rate_pct']} | {summary_b['pass_rate_pct']} |",
        f"| Cycles | {summary_a['cycles']} | {summary_b['cycles']} |",
        f"| Infra retries | {summary_a['infra_retries']} | {summary_b['infra_retries']} |",
        "",
        "## Durations",
        "",
        f"| transport | kind | {names[0]} median (s) | {names[1]} median (s) | ratio | flag |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {d['transport']} | {d['kind']} | {d['a_median']} | {d['b_median']} | {d['ratio']:.2f} | "
        f"{'FLAG' if d['flagged'] else ''} |"
        for d in comparison["duration_diffs"]
    )
    lines.extend(["", "## Flags", ""])
    if comparison["flags"]:
        lines.extend(f"- {flag}" for flag in comparison["flags"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _agreement(a: Run, b: Run) -> dict[str, Any]:
    shared = sorted(set(a["cycles"]) & set(b["cycles"]))
    differ = [n for n in shared if a["cycles"][n]["ok"] != b["cycles"][n]["ok"]]
    return {"same_outcome": len(shared) - len(differ), "differ": differ}


def _duration_diffs(summary_a: dict[str, Any], summary_b: dict[str, Any], tolerance: float) -> list[DurationDiff]:
    diffs: list[DurationDiff] = []
    for key in sorted(set(summary_a["median_s"]) & set(summary_b["median_s"])):
        a_median, b_median = summary_a["median_s"][key], summary_b["median_s"][key]
        ratio = b_median / a_median if a_median else _RATIO_UNCOMPARABLE
        diffs.append(
            {
                "transport": key[0],
                "kind": key[1],
                "a_median": a_median,
                "b_median": b_median,
                "ratio": ratio,
                "flagged": abs(ratio - 1) > tolerance,
            }
        )
    return diffs


def _flags(comparison: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if not comparison["plan_identical"]:
        flags.append("plan differs between the two runs: outcomes and durations are not comparable")
    agreement = comparison["cycle_agreement"]
    if agreement and agreement["differ"]:
        flags.append(f"outcome differs at cycles {agreement['differ']}")
    for diff in comparison["duration_diffs"]:
        if not diff["flagged"]:
            continue
        slower = "slower" if diff["ratio"] > 1 else "faster"
        flags.append(
            f"duration: {diff['transport']} {diff['kind']} is {slower} on board 2 by "
            f"{abs(diff['ratio'] - 1) * 100:.0f} %"
        )
    summary_a, summary_b = comparison["summary"]["a"], comparison["summary"]["b"]
    if summary_a["pass_rate_pct"] != summary_b["pass_rate_pct"]:
        flags.append(f"pass rate differs: {summary_a['pass_rate_pct']} % vs {summary_b['pass_rate_pct']} %")
    return flags
