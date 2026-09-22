"""BL-060 soak runner: N alternating OTA cycles (v1 <-> v2, WiFi and BLE mixed) against the REAL board.

Run natively (Windows workstation / RPi4), never under WSL (R14). Every cycle is verified twice: the update CLI's own
LABID checks AND an independent LABID snapshot here. Results are appended to cycles.jsonl as they happen (a crash
loses nothing), a heartbeat is kept in status.json, the run aborts after repeated consecutive failures, the board is
restored to confirmed v1 at the end, and every report is labelled "mode": "live".

    python -m tests_hil.soak --port COM14 --board-ip 192.168.1.152 --keys-dir keys --env-file credentials.env \
        --cycles 100 --out scripts/evidence/bl060_soak_<date> [--resume]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

EXPECTED = {"v1": "1.0.0", "v2": "2.0.0"}
TRANSPORT_PATTERN = ("wifi", "wifi", "ble", "ble")   # per PLAN T16: mixed transports, WiFi and BLE both exercised
PASS_TARGET_PCT = 99.0


def plan_cycle(cycle: int) -> tuple[str, str]:
    """(target variant, transport) for 1-based `cycle`: odd -> v2, even -> v1."""
    return ("v2" if cycle % 2 == 1 else "v1", TRANSPORT_PATTERN[(cycle - 1) % len(TRANSPORT_PATTERN)])


def _read_done(jsonl: Path) -> list[dict]:
    if not jsonl.is_file():
        return []
    return [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]


def _one_cycle(backend, cycle: int, log_path: Path, timeout_s: float | None) -> tuple[bool, str]:
    variant, transport = plan_cycle(cycle)
    try:
        ok = backend.update(variant, transport, log_path, timeout_s)
    except Exception as err:  # noqa: BLE001 - a failing cycle must be recorded, not crash the soak
        return False, f"update raised {type(err).__name__}: {err}"
    if not ok:
        return False, f"update {variant} via {transport} failed (see update.log)"
    try:
        s = backend.snapshot()
    except Exception as err:  # noqa: BLE001
        return False, f"board unreadable after update: {err}"
    if s.app != EXPECTED[variant] or not s.confirmed:
        return False, f"expected {EXPECTED[variant]} confirmed, board reports {s.app} confirmed={s.confirmed}"
    return True, ""


def run_soak(backend, cycles: int, out_dir: Path, pause_s: float = 5.0, max_consecutive_failures: int = 3,
             resume: bool = False, timeout_s: float | None = None,
             sleep_fn: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl, log_path = out_dir / "cycles.jsonl", out_dir / "update.log"
    done = _read_done(jsonl) if resume else []
    if not resume and jsonl.exists():
        raise FileExistsError(f"{jsonl} exists; pass --resume to continue it or choose a new --out")
    start_cycle = len(done) + 1
    t0 = clock()
    consecutive, aborted = 0, False

    if not done and not backend.reset_to_v1(log_path):
        raise RuntimeError("precondition failed: could not bring the board to confirmed v1")

    for cycle in range(start_cycle, cycles + 1):
        tc = clock()
        ok, cause = _one_cycle(backend, cycle, log_path, timeout_s)
        variant, transport = plan_cycle(cycle)
        rec = {"cycle": cycle, "variant": variant, "transport": transport, "ok": ok, "cause": cause,
               "duration_s": round(clock() - tc, 1)}
        with jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        done.append(rec)
        (out_dir / "status.json").write_text(json.dumps({"mode": "live", "cycle": cycle, "of": cycles,
                                                         "passes": sum(r["ok"] for r in done)}))
        consecutive = 0 if ok else consecutive + 1
        if consecutive >= max_consecutive_failures:
            aborted = True
            break
        if not ok:
            try:
                backend.reset_to_v1(log_path)   # best-effort recovery; a failure here must not kill the run
            except Exception as err:  # noqa: BLE001 - recorded, run continues
                with jsonl.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"cycle": cycle, "note": f"recovery reset raised {type(err).__name__}: {err}"}) + "\n")
        sleep_fn(pause_s)

    try:
        final_v1 = bool(backend.reset_to_v1(log_path))
    except Exception:  # noqa: BLE001
        final_v1 = False
    passes = sum(r["ok"] for r in done)
    total = len(done)
    by_transport: dict[str, dict[str, int]] = {}
    for r in done:
        t = by_transport.setdefault(r["transport"], {"total": 0, "passes": 0})
        t["total"] += 1
        t["passes"] += int(r["ok"])
    rate = passes / total * 100.0 if total else 0.0
    report = {
        "mode": "live", "requested_cycles": cycles, "total_cycles": total, "passes": passes, "failures": total - passes,
        "pass_rate_pct": round(rate, 2), "target_pct": PASS_TARGET_PCT, "aborted": aborted,
        "final_state_v1": final_v1, "elapsed_s": round(clock() - t0, 1), "by_transport": by_transport,
        "resumed_from": start_cycle - 1 if resume and start_cycle > 1 else 0,
        "failure_log": [{"cycle": r["cycle"], "cause": r["cause"]} for r in done if not r["ok"]],
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--board-ip", required=True)
    ap.add_argument("--keys-dir")
    ap.add_argument("--env-file")
    ap.add_argument("--images-dir")
    ap.add_argument("--rig-config")
    ap.add_argument("--cycles", type=int, default=100)
    ap.add_argument("--pause", type=float, default=5.0, help="seconds between cycles")
    ap.add_argument("--max-consecutive-failures", type=int, default=3)
    ap.add_argument("--out", required=True, help="output dir (cycles.jsonl, status.json, report.json, update.log)")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args(argv)

    from tests_hil.live_backend import LiveBackend, LiveRigError
    try:
        backend = LiveBackend.create(port=a.port, board_ip=a.board_ip,
                                     images_dir=Path(a.images_dir) if a.images_dir else None,
                                     keys_dir=Path(a.keys_dir) if a.keys_dir else None,
                                     env_file=a.env_file, rig_path=a.rig_config)
    except LiveRigError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    report = run_soak(backend, a.cycles, Path(a.out), a.pause, a.max_consecutive_failures, a.resume)
    print(json.dumps(report, indent=2))
    ok = report["pass_rate_pct"] >= PASS_TARGET_PCT and not report["aborted"] and report["final_state_v1"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
