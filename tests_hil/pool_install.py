"""BL-069 AC5: install every pool image on the REAL board over WiFi and BLE, in both OTA slots.

Run natively (Windows workstation / RPi4), never under WSL (R14). The pool is verified against its manifest first
(sizes and sha256, so a bad WSL->Windows copy fails before the board is touched). Every install is checked against the
manifest's expected outcome for that transport; the real slot is read before each step so one failure cannot cascade
into false slot mismatches. Results are appended to results.jsonl as they happen, so --resume loses nothing.

    python -m tests_hil.pool_install --pool esp_idf\\build_pool --port COM14 --board-ip 192.168.1.152 \\
        --keys-dir keys --env-file credentials.env --out scripts\\evidence\\bl069_pool_install_<date> [--resume]
    python -m tests_hil.pool_install --pool esp_idf\\build_pool --out X --dry-run      # print the plan, no board
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from labflash import poolmanifest

from tests_hil import pool_schedule as ps
from tests_hil.otaretry import INFRA_RETRIES, send_with_retry

DEFAULT_REJECT_TIMEOUT_S = 120.0
MAX_CONSECUTIVE_UNEXPECTED = 3
TOPUP_LIMIT = 12                        # extra installs allowed to close slot-coverage gaps after failures


class PoolError(RuntimeError):
    """The pool on disk does not match its manifest."""


def verify_pool(manifest: dict, pool_dir: Path) -> None:
    """Every manifest file exists with the recorded size and sha256; name each offender."""
    bad = []
    for e in manifest["images"]:
        f = pool_dir / e["file"]
        if not f.is_file():
            bad.append(f"{e['file']} missing")
            continue
        data = f.read_bytes()
        if len(data) != e["size"] or hashlib.sha256(data).hexdigest() != e["sha256"]:
            bad.append(f"{e['file']} does not match the manifest")
    if bad:
        raise PoolError("; ".join(bad))


def _manifest_id(manifest: dict) -> dict:
    """What ties a results file to one pool: the seed base and a hash of the manifest's images."""
    digest = hashlib.sha256(json.dumps(manifest["images"], sort_keys=True).encode()).hexdigest()
    return {"seed_base": manifest["seed_base"], "manifest_sha256": digest}


def _read_results(path: Path, manifest: dict) -> list[dict]:
    """Result records of a previous run, latest record per step key; refuses another pool's file."""
    if not path.is_file():
        return []
    raw = [x for x in path.read_text().splitlines() if x.strip()]
    lines = []
    for n, text in enumerate(raw):
        try:
            lines.append(json.loads(text))
        except json.JSONDecodeError:
            if n != len(raw) - 1:
                raise PoolError(f"{path}: line {n + 1} is not valid JSON") from None
            path.write_text("".join(x + "\n" for x in raw[:-1]))       # a torn last line (killed mid-write): drop it
    header = next((r["header"] for r in lines if "header" in r), None)
    if header != _manifest_id(manifest):
        raise PoolError(f"{path} belongs to a different pool ({header}); refusing to resume it")
    latest: dict[str, dict] = {}
    for rec in lines:
        if "key" in rec:
            latest[rec["key"]] = rec
    return list(latest.values())


def _append(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _failed(cause: str, expected_slot: int | None = None) -> dict:
    return {"verdict": "fail", "cause": cause, "accepted": False, "confirmed": False, "slot": None,
            "version": None, "expected_slot": expected_slot}


def _do_step(backend, step: ps.Step, entry: dict, pool_dir: Path, log_path: Path,
             timeout_s: float | None, reject_timeout_s: float, transport_proven: bool,
             retries: int = INFRA_RETRIES, sleep_fn: Callable[[float], None] = time.sleep) -> dict:
    try:
        pre = backend.snapshot()
    except Exception as err:  # noqa: BLE001 - an unreadable board is a recorded failure, not a crashed run
        return _failed(f"board unreadable before update: {err}")
    step = dataclasses.replace(step, expected_slot=pre.slot ^ 1 if step.expect_accept else pre.slot)
    if not step.expect_accept and not transport_proven:
        return _failed(f"reject of {step.file} over {step.transport} is unverified: no install over it has passed yet, "
                       "so a dead link would look identical to a refusal", step.expected_slot)
    ok, err_cause, retries_used = send_with_retry(backend, pool_dir / step.file, step.transport, log_path,
                                                  timeout_s if step.expect_accept else reject_timeout_s,
                                                  retries=retries, sleep_fn=sleep_fn)
    if err_cause:
        return {**_failed(err_cause, step.expected_slot), "infra_retries": retries_used}
    cause = ""
    try:
        post = backend.snapshot()
    except Exception as err:  # noqa: BLE001
        return _failed(f"board unreadable after update: {err}", step.expected_slot)
    accepted = post.app == entry["version"] and (ok or not step.expect_accept)
    result = {"accepted": accepted, "confirmed": post.confirmed, "slot": post.slot, "version": post.app}
    verdict = ps.classify(step, result)
    if verdict == "expected_reject" and (post.app != pre.app or post.slot != pre.slot or not post.confirmed):
        verdict, cause = "fail", "board changed on an install it should have rejected"
    if verdict == "fail" and not cause:
        cause = (f"expected {step.expected_version} confirmed in slot {step.expected_slot}, board reports "
                 f"{post.app} confirmed={post.confirmed} slot={post.slot} (update ok={ok})")
    return {**result, "verdict": verdict, "cause": cause, "expected_slot": step.expected_slot,
            "infra_retries": retries_used}


def _topup_step(manifest: dict, results: list[dict], real_slot: int, round_no: int) -> ps.Step | None:
    """The next install that closes a coverage gap given the board's real slot, or None when nothing is missing.

    A successful install lands on the slot opposite to the current one, so a gap can be closed only by an image whose
    missing slot is real_slot ^ 1. If every gap needs the current slot, a spacer install of any image the transport
    accepts flips the parity first (it also counts toward coverage).
    """
    gaps = ps.coverage_gaps(manifest, results)
    if not gaps:
        return None
    by_version = {e["version"]: e for e in manifest["images"]}
    wanted = [g for g in gaps if g[2] == real_slot ^ 1]
    version, transport, _ = (wanted or gaps)[0]
    entry = by_version[version]
    if not wanted:
        entry = next(e for e in manifest["images"] if e["expected"][transport]["accept"] and e["role"] == "valid")
    return ps.Step(sweep=100 + round_no, transport=transport, image_index=entry["index"], file=entry["file"],
                   expect_accept=True, skip=False, skip_reason="", expected_version=entry["version"],
                   expected_slot=real_slot ^ 1)


def _summarize(manifest: dict, steps: list[ps.Step], results: list[dict]) -> tuple[dict, dict]:
    counts = {"pass": 0, "fail": 0, "expected_reject": 0, "skipped": 0}
    for r in results:
        counts[r["verdict"]] += 1
    coverage: dict[str, dict[str, list[int]]] = {}
    for r in results:
        if r["verdict"] == "pass":
            version = manifest["images"][r["image_index"]]["version"]
            slots = coverage.setdefault(version, {}).setdefault(r["transport"], [])
            if r["slot"] not in slots:
                slots.append(r["slot"])
    return counts, {v: {t: sorted(s) for t, s in ts.items()} for v, ts in coverage.items()}


def run_pool_install(backend, manifest: dict, pool_dir: Path, out_dir: Path, transports=("wifi", "ble"),
                     sweeps: int = 2, pause_s: float = 5.0, resume: bool = False, timeout_s: float | None = None,
                     reject_timeout_s: float = DEFAULT_REJECT_TIMEOUT_S,
                     max_consecutive_unexpected: int = MAX_CONSECUTIVE_UNEXPECTED, stop_after: int | None = None,
                     infra_retries: int = INFRA_RETRIES,
                     sleep_fn: Callable[[float], None] = time.sleep,
                     clock: Callable[[], float] = time.monotonic) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl, log_path = out_dir / "results.jsonl", out_dir / "update.log"
    if jsonl.exists() and not resume:
        raise FileExistsError(f"{jsonl} exists; pass --resume to continue it or choose a new --out")
    verify_pool(manifest, pool_dir)
    results = _read_results(jsonl, manifest) if resume else []
    if not jsonl.exists():
        _append(jsonl, {"header": _manifest_id(manifest)})
    resumed_from = len(results)
    if not results and not backend.reset_to_v1(log_path):
        raise RuntimeError("precondition failed: could not bring the board to confirmed v1")
    steps = ps.plan_sweeps(manifest, tuple(transports), sweeps, start_slot=backend.snapshot().slot)
    todo = ps.remaining(steps, {r["key"] for r in results if r["verdict"] != "fail"})   # failed steps run again
    results = [r for r in results if r["key"] not in {s.key for s in todo}]
    proven = {r["transport"] for r in results if r["verdict"] == "pass"}
    t0, consecutive, aborted, stopped, recovery_failures = clock(), 0, False, False, 0

    for n, step in enumerate(todo):
        if stop_after is not None and n >= stop_after:
            stopped = True
            break
        entry, t_step = manifest["images"][step.image_index], clock()
        if step.skip:
            rec = {"verdict": "skipped", "cause": step.skip_reason, "accepted": False, "confirmed": False,
                   "slot": None, "version": None, "expected_slot": None}
        else:
            rec = _do_step(backend, step, entry, pool_dir, log_path, timeout_s, reject_timeout_s,
                           step.transport in proven, infra_retries, sleep_fn)
        rec.update({"key": step.key, "sweep": step.sweep, "transport": step.transport, "image_index": step.image_index,
                    "file": step.file, "expected_version": step.expected_version, "duration_s": round(clock() - t_step, 1)})
        _append(jsonl, rec)
        results.append(rec)
        if rec["verdict"] == "pass":
            proven.add(step.transport)
        counts, _ = _summarize(manifest, steps, results)
        (out_dir / "status.json").write_text(json.dumps({"mode": "live", "done": len(results), "of": len(steps),
                                                         **counts}))
        if rec["verdict"] == "fail":
            consecutive += 1
            if consecutive >= max_consecutive_unexpected:
                aborted = True
                break
            try:
                restored = bool(backend.reset_to_v1(log_path))   # best effort; the next step re-reads the real slot
            except Exception as err:  # noqa: BLE001
                restored = False
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(f"--- recovery reset raised {type(err).__name__}: {err}\n")
            if not restored:
                recovery_failures += 1
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(f"--- recovery after {step.key} did not restore confirmed v1\n")
        elif rec["verdict"] != "skipped":
            consecutive = 0
        if rec["verdict"] != "skipped":
            sleep_fn(pause_s)

    topups = 0
    while not aborted and not stopped and topups < TOPUP_LIMIT:
        try:
            real_slot = backend.snapshot().slot
        except Exception:  # noqa: BLE001 - the final reset below reports an unreadable board
            break
        step = _topup_step(manifest, results, real_slot, topups + 1)
        if step is None:
            break
        topups += 1
        t_step = clock()
        rec = _do_step(backend, step, manifest["images"][step.image_index], pool_dir, log_path, timeout_s,
                       reject_timeout_s, True, infra_retries, sleep_fn)
        rec.update({"key": f"{step.transport}:top{topups}:{step.image_index}", "sweep": step.sweep,
                    "transport": step.transport, "image_index": step.image_index, "file": step.file,
                    "expected_version": step.expected_version, "duration_s": round(clock() - t_step, 1),
                    "topup": True})
        _append(jsonl, rec)
        results.append(rec)
        if rec["verdict"] == "fail":
            consecutive += 1
            if consecutive >= max_consecutive_unexpected:
                aborted = True
        else:
            consecutive = 0
        sleep_fn(pause_s)

    final_v1 = False
    if not stopped:
        try:
            backend.reset_to_v1(log_path)
            snap = backend.snapshot()
            final_v1 = snap.app.startswith("1.") and snap.confirmed
        except Exception:  # noqa: BLE001
            final_v1 = False
    counts, coverage = _summarize(manifest, steps, results)
    report = {
        "mode": "live", "seed_base": manifest["seed_base"], "steps_total": len(steps), "steps_done": len(results), "infra_retries": sum(r.get("infra_retries", 0) for r in results),
        "counts": counts, "coverage_gaps": [list(g) for g in ps.coverage_gaps(manifest, results)],
        "aborted": aborted, "stopped_early": stopped, "recovery_failures": recovery_failures, "topup_installs": topups, "final_state_v1": final_v1,
        "elapsed_s": round(clock() - t0, 1), "resumed_from": resumed_from,
        "failure_log": [{"key": r["key"], "cause": r["cause"]} for r in results if r["verdict"] == "fail"],
    }
    (out_dir / "slot_coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True))
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", required=True, help="directory with the pool .bin files and manifest.json")
    ap.add_argument("--out", required=True, help="evidence dir (results.jsonl, status.json, report.json, ...)")
    ap.add_argument("--port")
    ap.add_argument("--board-ip")
    ap.add_argument("--keys-dir")
    ap.add_argument("--env-file")
    ap.add_argument("--rig-config")
    ap.add_argument("--transports", default="wifi,ble")
    ap.add_argument("--sweeps", type=int, default=2)
    ap.add_argument("--pause", type=float, default=5.0)
    ap.add_argument("--reject-timeout", type=float, default=DEFAULT_REJECT_TIMEOUT_S)
    ap.add_argument("--max-consecutive-unexpected", type=int, default=MAX_CONSECUTIVE_UNEXPECTED)
    ap.add_argument("--infra-retries", type=int, default=INFRA_RETRIES,
                    help="retries for host-side send trouble while the board is unchanged (default 3)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; no board, no writes")
    ap.add_argument("--no-console-log", action="store_true")
    a = ap.parse_args(argv)

    pool_dir, out_dir = Path(a.pool), Path(a.out)
    manifest = poolmanifest.load_manifest(pool_dir / "manifest.json")
    transports = tuple(t for t in a.transports.split(",") if t)
    if a.dry_run:
        verify_pool(manifest, pool_dir)
        for s in ps.plan_sweeps(manifest, transports, a.sweeps):
            state = "skip: " + s.skip_reason if s.skip else ("install" if s.expect_accept else "expect-reject")
            print(f"{s.key:<10} {s.file}  {state}  slot->{s.expected_slot}")
        return 0
    if not (a.port and a.board_ip):
        print("ERROR: --port and --board-ip are required for a real run", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    from tests_hil.live_backend import LiveBackend, LiveRigError
    try:
        backend = LiveBackend.create(port=a.port, board_ip=a.board_ip,
                                     keys_dir=Path(a.keys_dir) if a.keys_dir else None, env_file=a.env_file,
                                     rig_path=a.rig_config,
                                     console_log=None if a.no_console_log else out_dir / "console.log")
    except LiveRigError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    try:
        report = run_pool_install(backend, manifest, pool_dir, out_dir, transports, a.sweeps, a.pause, a.resume,
                                  reject_timeout_s=a.reject_timeout,
                                  max_consecutive_unexpected=a.max_consecutive_unexpected,
                                  infra_retries=a.infra_retries)
    finally:
        backend.shutdown()
    print(json.dumps(report, indent=2))
    good = not report["counts"]["fail"] and not report["coverage_gaps"] and not report["aborted"]
    return 0 if good and report["final_state_v1"] else 1


if __name__ == "__main__":
    sys.exit(main())
