"""BL-067: heavy randomized OTA soak against the REAL board (seeded picks, expected-outcome model).

Every cycle picks an image and a transport from a seeded stream (tests_hil/soak_model.py), sends it, and checks the board
against what the model expects: valid images install and confirm, bad_sig is rejected, no_confirm and hang boot and roll back.
Run natively (Windows workstation), never under WSL (R14). Results are appended to cycles.jsonl as they happen, so
--resume loses nothing; the plan is tied to the seed, so --resume must use the same settings.

    python -m tests_hil.soak_random --pool esp_idf\\build_pool --port COM14 --board-ip 192.168.1.152 --keys-dir keys \\
        --env-file credentials.env --out evidence\\bl067_<date> --cycles 200 [--seed N] [--ble-share 0.5] [--resume]
    python -m tests_hil.soak_random --pool esp_idf\\build_pool --out X --cycles 200 --seed N --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from labflash import poolmanifest

from tests_hil import soak_model as sm
from tests_hil.otaretry import (
    INFRA_RETRIES,
    log_since,
    log_size,
    send_with_retry,
    transfer_seen,
)

PASS_TARGET_PCT = 99.0
MAX_CONSECUTIVE_UNEXPECTED = 3
ROLLBACK_TIMEOUT_S = 120.0
REJECT_TIMEOUT_S = 120.0
WARMUP = (("wifi", "v2"), ("ble", "v1"))       # proves both transports work before any reject is trusted


class SoakError(RuntimeError):
    """The run cannot start or continue (bad resume file, board not confirmed)."""


def _plan_id(seed: int, cycles: int, ble_share: float, failure_cap: int, manifest: dict | None) -> dict:
    digest = hashlib.sha256(json.dumps(manifest["images"], sort_keys=True).encode()).hexdigest() if manifest else ""
    return {"seed": seed, "cycles": cycles, "ble_share": ble_share, "failure_cap": failure_cap,
            "manifest_sha256": digest, "model_version": sm.MODEL_VERSION}


def _read_records(path: Path, plan_id: dict) -> list[dict]:
    if not path.is_file():
        return []
    raw = [x for x in path.read_text().splitlines() if x.strip()]
    lines = []
    for n, text in enumerate(raw):
        try:
            lines.append(json.loads(text))
        except json.JSONDecodeError:
            if n != len(raw) - 1:
                raise SoakError(f"{path}: line {n + 1} is not valid JSON") from None
            path.write_text("".join(x + "\n" for x in raw[:-1]))       # a torn last line (killed mid-write): drop it
    header = next((r["header"] for r in lines if "header" in r), None)
    if header != plan_id:
        raise SoakError(f"{path} was written for a different plan ({header}); refusing to resume it")
    records = [r for r in lines if "cycle" in r]
    cycles = [r["cycle"] for r in records if r["cycle"] >= 1]
    if cycles != list(range(1, len(cycles) + 1)):
        raise SoakError(f"{path}: cycle numbers are not contiguous from 1; refusing to resume it")
    return records


def _append(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _same(a, b) -> bool:
    return (a.app, a.slot, a.confirmed) == (b.app, b.slot, b.confirmed)


def _image_path(backend, pool_dir: Path, image: sm.Image) -> Path:
    return pool_dir / image.file if image.kind == "generated" and image.file else backend.image_for(image.file)


def _hang_ran(update_log: str, console: str) -> bool:
    """Positive evidence that the hang image really booted: the watchdog fired, or the update CLI saw it running."""
    return "Task watchdog got triggered" in console or "[PASS] running the new image" in update_log


def _check(backend, exp: sm.Expectation, pre, ok: bool, cause: str, evidence: dict) -> tuple[bool, str, dict]:
    """Compare the board with what the model expects; returns (passed, cause, observed).

    A failure image only counts when its whole transfer was seen (a dead link looks like a refusal) and, for hang, when
    the hang image is shown to have really run (otherwise "rolled back" is just the untouched old image).
    """
    if cause:
        return False, cause, {}
    if exp.outcome != "installs" and not evidence["transferred"]:
        return False, "no complete transfer in the update log: the image never fully reached the board, so the outcome is unverified", {}
    if exp.outcome == "installs":
        post = backend.snapshot()
        good = ok and (post.app, post.slot, post.confirmed) == (exp.app, exp.slot, True)
        return good, "" if good else f"expected {exp.app} slot {exp.slot} confirmed (update ok={ok}), board reports {post}", \
            {"app": post.app, "slot": post.slot, "confirmed": post.confirmed}
    if exp.outcome == "rejected":
        post = backend.snapshot()
        good = (not ok) and _same(pre, post)
        return good, "" if good else f"a rejected image changed the board or was accepted (ok={ok}): {pre} -> {post}", \
            {"app": post.app, "slot": post.slot, "confirmed": post.confirmed}
    if ok:
        return False, "a failure image reported a successful update", {}
    observed: dict = {}
    if exp.check_pending:
        pending = backend.snapshot()
        observed["pending"] = {"app": pending.app, "slot": pending.slot, "confirmed": pending.confirmed}
        if (pending.app, pending.slot, pending.confirmed) != (exp.pending_app, exp.pending_slot, False):
            return False, f"no_confirm did not boot unconfirmed: expected {exp.pending_app} slot {exp.pending_slot}, got {pending}", observed
        backend.reset()
    elif not evidence["hang_ran"]:
        return False, "no evidence that the hang image ran (no watchdog message in the console, update CLI never saw it running)", observed
    post = backend.wait_snapshot(lambda s: (s.app, s.slot, s.confirmed) == (exp.app, exp.slot, True), ROLLBACK_TIMEOUT_S)
    if post is None:
        return False, f"no rollback to {exp.app} slot {exp.slot} within {ROLLBACK_TIMEOUT_S:.0f} s", observed
    observed.update({"app": post.app, "slot": post.slot, "confirmed": post.confirmed})
    return True, "", observed


def _resync(backend, log_path: Path) -> sm.State:
    """After an unexpected outcome, believe the real board: a confirmed image as-is, otherwise restore v1."""
    try:
        s = backend.snapshot()
        if s.confirmed:
            return sm.State(s.app, s.slot, True)
    except Exception as err:  # noqa: BLE001 - falls through to the restore below, but say why
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"--- resync: snapshot failed ({type(err).__name__}: {err}); restoring v1\n")
    if not backend.reset_to_v1(log_path):
        raise SoakError("board could not be brought back to a confirmed image")
    s = backend.snapshot()
    return sm.State(s.app, s.slot, s.confirmed)


def _cycle(backend, catalog: sm.Catalog, pool_dir: Path, pick: sm.Pick, state: sm.State, log_path: Path,
           timeout_s: float | None, console_log: Path | None, retries: int = INFRA_RETRIES,
           sleep_fn: Callable[[float], None] = time.sleep) -> tuple[dict, sm.Expectation | None]:
    pre = backend.snapshot()
    resynced = (pre.app, pre.slot, pre.confirmed) != (state.app, state.slot, state.confirmed)
    if resynced:                                                     # the board is not where the model thinks: trust the board
        if not pre.confirmed:
            raise SoakError(f"board is on an unconfirmed image before the cycle: {pre}")
        state = sm.State(pre.app, pre.slot, True)
    exp = sm.expected_after(state, pick.image, pick.transport)
    path = _image_path(backend, pool_dir, pick.image)
    log_offset, console_offset = log_size(log_path), log_size(console_log)
    ok, cause, retries_used = send_with_retry(backend, path, pick.transport, log_path,
                                              timeout_s if exp.outcome == "installs" else REJECT_TIMEOUT_S,
                                              retries=retries, sleep_fn=sleep_fn)
    update_log, console = log_since(log_path, log_offset), log_since(console_log, console_offset)
    evidence = {"transferred": transfer_seen(log_since(log_path, log_offset), pick.transport),
                "hang_ran": _hang_ran(update_log, console)}
    passed, cause, observed = _check(backend, exp, pre, ok, cause, evidence)
    rec = {"ok": passed, "cause": cause, "expected": {"outcome": exp.outcome, "app": exp.app, "slot": exp.slot},
           "observed": observed}
    if resynced:
        rec["resynced_from_board"] = True
    if retries_used:
        rec["infra_retries"] = retries_used
    return rec, exp


def _warmup(backend, catalog: sm.Catalog, pool_dir: Path, state: sm.State, log_path: Path,
            timeout_s: float | None, console_log: Path | None, retries: int,
            sleep_fn: Callable[[float], None]) -> tuple[list[dict], sm.State]:
    recs = []
    by_name = {i.name: i for i in catalog.fixed}
    for transport, name in WARMUP:
        rec, exp = _cycle(backend, catalog, pool_dir, sm.Pick(by_name[name], transport), state, log_path, timeout_s,
                          console_log, retries, sleep_fn)
        recs.append({"cycle": 0, "image": name, "kind": "warmup", "transport": transport, **rec})
        if not rec["ok"]:
            raise SoakError(f"warm-up install of {name} over {transport} failed: {rec['cause']}")
        assert exp is not None
        state = sm.next_state(exp)
    return recs, state


def _write_status(out_dir: Path, status: dict) -> None:
    tmp = out_dir / "status.json.tmp"
    tmp.write_text(json.dumps(status))
    tmp.replace(out_dir / "status.json")


def run_soak(backend, catalog: sm.Catalog, picks: list[sm.Pick], plan_id: dict, pool_dir: Path, out_dir: Path,
             pause_s: float = 5.0, resume: bool = False, timeout_s: float | None = None,
             max_consecutive_unexpected: int = MAX_CONSECUTIVE_UNEXPECTED, stop_after: int | None = None,
             sleep_fn: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
             console_log: Path | None = None, infra_retries: int = INFRA_RETRIES) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl, log_path = out_dir / "cycles.jsonl", out_dir / "update.log"
    if jsonl.exists() and not resume:
        raise FileExistsError(f"{jsonl} exists; pass --resume to continue it or choose a new --out")
    done = _read_records(jsonl, plan_id) if resume else []
    if not jsonl.exists():
        _append(jsonl, {"header": plan_id})
    resumed_from = len([r for r in done if r["cycle"] >= 1])
    t0 = clock()
    state: sm.State | None = None
    state_box = {"aborted": False, "stopped": False, "error": None}
    try:
        if not done and not backend.reset_to_v1(log_path):
            raise SoakError("precondition failed: could not bring the board to confirmed v1")
        state = _resync(backend, log_path)
        if not done:
            warm, state = _warmup(backend, catalog, pool_dir, state, log_path, timeout_s, console_log,
                                infra_retries, sleep_fn)
            for rec in warm:
                _append(jsonl, rec)
            done.extend(warm)
        consecutive = 0
        for index in range(resumed_from, len(picks)):
            if stop_after is not None and index - resumed_from >= stop_after:
                state_box["stopped"] = True
                break
            pick, t_cycle = picks[index], clock()
            try:
                rec, exp = _cycle(backend, catalog, pool_dir, pick, state, log_path, timeout_s, console_log,
                                  infra_retries, sleep_fn)
            except SoakError:
                raise
            except Exception as err:  # noqa: BLE001 - an unreadable board is a recorded failure, not a crash
                rec, exp = {"ok": False, "cause": f"cycle raised {type(err).__name__}: {err}", "expected": {},
                            "observed": {}}, None
            rec.update({"cycle": index + 1, "image": pick.image.name, "kind": pick.image.kind,
                        "transport": pick.transport, "version": pick.image.version,
                        "duration_s": round(clock() - t_cycle, 1)})
            _append(jsonl, rec)
            done.append(rec)
            real = [r for r in done if r["cycle"] >= 1]
            _write_status(out_dir, {"mode": "live", "seed": plan_id["seed"], "cycle": index + 1, "of": len(picks),
                                    "passes": sum(r["ok"] for r in real)})
            if rec["ok"] and exp is not None:
                state, consecutive = sm.next_state(exp), 0
            else:
                consecutive += 1
                if consecutive >= max_consecutive_unexpected:
                    state_box["aborted"] = True
                    break
                state = _resync(backend, log_path)
            sleep_fn(pause_s)
    except SoakError as err:
        state_box["error"] = str(err)
    finally:
        final_ok = False
        if not state_box["stopped"]:
            try:
                final_ok = bool(backend.reset_to_v1(log_path)) and backend.snapshot().confirmed
            except BaseException:  # noqa: BLE001 - even a second Ctrl-C must not lose the report; it says the restore failed
                final_ok = False
        report = _report(catalog, picks, plan_id, done, state_box["aborted"], state_box["stopped"], final_ok,
                         resumed_from, clock() - t0, out_dir)
        report["error"] = state_box["error"]
        (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    if state_box["error"]:
        raise SoakError(state_box["error"])
    return report


def _report(catalog, picks, plan_id, done, aborted, stopped, final_ok, resumed_from, elapsed, out_dir) -> dict:
    real = [r for r in done if r["cycle"] >= 1]
    passes = sum(r["ok"] for r in real)
    by_image: dict[str, dict[str, int]] = {}
    by_transport: dict[str, dict[str, int]] = {}
    slots: dict[str, dict[str, list[int]]] = {}
    for r in real:
        for table, key in ((by_image, r["image"]), (by_transport, r["transport"])):
            t = table.setdefault(key, {"total": 0, "passes": 0})
            t["total"] += 1
            t["passes"] += int(r["ok"])
        if r["kind"] == "generated" and r["ok"]:
            landed = slots.setdefault(r["image"], {}).setdefault(r["transport"], [])
            slot = r["observed"].get("slot")
            if slot not in landed:
                landed.append(slot)
    rate = passes / len(real) * 100.0 if real else 0.0
    report = {
        "mode": "live", "seed": plan_id["seed"], "plan": plan_id, "planned_cycles": len(picks), "total_cycles": len(real),
        "passes": passes, "failures": len(real) - passes, "pass_rate_pct": round(rate, 2), "target_pct": PASS_TARGET_PCT,
        "aborted": aborted, "stopped_early": stopped, "final_state_confirmed": final_ok, "elapsed_s": round(elapsed, 1),
        "resumed_from": resumed_from, "infra_retries": sum(r.get("infra_retries", 0) for r in real),
        "plan_summary": sm.plan_summary(picks),
        "by_image": by_image, "by_transport": by_transport,
        "generated_slots": {k: {t: sorted(s) for t, s in v.items()} for k, v in slots.items()},
        "failure_log": [{"cycle": r["cycle"], "image": r["image"], "transport": r["transport"], "cause": r["cause"]}
                        for r in real if not r["ok"]],
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", required=True, help="directory with the BL-069 pool (manifest.json + .bin files)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cycles", type=int, default=200)
    ap.add_argument("--seed", type=int, default=None, help="default: derived from the clock and printed")
    ap.add_argument("--ble-share", type=float, default=0.5)
    ap.add_argument("--failure-cap", type=int, default=2)
    ap.add_argument("--pause", type=float, default=5.0)
    ap.add_argument("--max-consecutive-unexpected", type=int, default=MAX_CONSECUTIVE_UNEXPECTED)
    ap.add_argument("--infra-retries", type=int, default=INFRA_RETRIES,
                    help="retries for host-side send trouble while the board is unchanged (default 3)")
    ap.add_argument("--port")
    ap.add_argument("--board-ip")
    ap.add_argument("--keys-dir")
    ap.add_argument("--env-file")
    ap.add_argument("--rig-config")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the seeded plan; no board, no writes")
    ap.add_argument("--no-console-log", action="store_true")
    a = ap.parse_args(argv)

    pool_dir, out_dir = Path(a.pool), Path(a.out)
    manifest = poolmanifest.load_manifest(pool_dir / "manifest.json")
    catalog = sm.build_catalog(manifest)
    seed = a.seed if a.seed is not None else int(time.time())
    picks = sm.plan(seed, a.cycles, catalog, a.ble_share, a.failure_cap)
    plan_id = _plan_id(seed, a.cycles, a.ble_share, a.failure_cap, manifest)
    print(f"seed {seed}: {json.dumps(sm.plan_summary(picks))}")
    if a.dry_run:
        for i, p in enumerate(picks[:30], 1):
            print(f"{i:>4} {p.transport:<4} {p.image.kind:<9} {p.image.name}")
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
                                     console_log=None if a.no_console_log else out_dir / "console.log",
                          infra_retries=a.infra_retries)
    except LiveRigError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    try:
        report = run_soak(backend, catalog, picks, plan_id, pool_dir, out_dir, a.pause, a.resume,
                          max_consecutive_unexpected=a.max_consecutive_unexpected,
                          console_log=None if a.no_console_log else out_dir / "console.log",
                          infra_retries=a.infra_retries)
    except SoakError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    finally:
        backend.shutdown()
    print(json.dumps({k: v for k, v in report.items() if k not in ("by_image", "generated_slots", "plan_summary")}, indent=2))
    good = report["pass_rate_pct"] >= PASS_TARGET_PCT and not report["aborted"] and report["final_state_confirmed"]
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
