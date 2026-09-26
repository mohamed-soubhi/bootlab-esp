# BL-067 randomized soak test

Runner: `tests_hil/soak_random.py`. Runs 200 cycles against board 1, where each cycle's image and transport come from
a seeded random stream, and the pass condition for the cycle is whatever the outcome model says the board must show
afterwards. The model lives in `tests_hil/soak_model.py` (no I/O, no board). Run natively (Windows workstation),
never under WSL (R14).

## How it works

**One cycle** = one planned pick (`soak_model.Pick`: an image plus a transport) sent over that transport, then a
serial check of the board against `soak_model.expected_after`. Nothing about the pick is decided from the board's
live state: the plan is fixed before the run starts.

**Seeded stream.** Every draw is `unit_float(seed, index, tag)` = SHAKE-256 over `"{seed}:{index}:{tag}"` reduced to
`[0, 1)`, with the tags `transport`, `category` and `image`. Nothing draws from `random`.

**Setup.** `reset_to_v1()` first; the board must reach a confirmed image or the run stops ("precondition failed:
could not bring the board to confirmed v1").

**Warm-up.** Before cycle 1 the runner installs v2 over WiFi and v1 over BLE (`WARMUP`). A reject is never trusted
over a link that has not already carried a successful install, so both transports are proven first. Warm-up records
are written with `cycle: 0` and `kind: warmup`, and are excluded from the pass-rate arithmetic. A failed warm-up
aborts the run with a `SoakError`.

**Per cycle.** Append the cycle record to `cycles.jsonl`, rewrite `status.json` (`mode`, `seed`, `cycle`, `of`,
`passes`), then sleep `--pause` (default 5 s).

**On an unexpected outcome.** Re-sync to the real board (`_resync`): if the board reports a confirmed image, believe
it as-is; otherwise `reset_to_v1()` (which accepts only a real v1 release, never `1.0.0-hang`, `-badsig` or `-noconfirm`).
Three consecutive unexpected outcomes abort the run (`--max-consecutive-unexpected`, default 3). If the board is found on a
different confirmed image than the model expects at the start of a cycle, the model is re-synced to the board and the
record is flagged `resynced_from_board`; an unconfirmed board at that point stops the run.

**Always restored.** Restoring v1 and writing `report.json` happen in a `finally`, so an error, an abort or Ctrl-C still
leaves the board on a confirmed image and a report on disk (`report.json` field `error` carries a `SoakError` message).

## Images

The catalog is built from the manifest plus three built-in groups (`soak_model.build_catalog`):

| Group | Names | Versions | Transports |
|---|---|---|---|
| `fixed` | `v1`, `v2`, `v3`, `v4` | `1.0.0` .. `4.0.0` | both accept |
| `generated` | manifest entries, name = the entry's `version` (`gen-<8 hex>`) | from the BL-069 manifest | per entry, from `expected[transport].accept` |
| `failure` | `bad_sig`, `hang`, `no_confirm` | `1.0.0-badsig`, `1.0.0-hang`, `1.0.0-noconfirm` | both accept |

Manifest entries with role `too_big` are dropped from the catalog, so the soak never sends an image known to be
larger than the slot.

**Mix.** A `category` draw picks fixed below 0.70, generated below 0.80, failure otherwise: 70 % fixed / 10 %
generated / 20 % failure over a long run. If the category draw lands on failure while the failure streak has reached
`--failure-cap` (default 2), the cycle falls back to fixed. The streak counts consecutive failure picks, so at most
`--failure-cap` failure images are ever sent back to back.

**Transport.** `transport` draw below `--ble-share` (default 0.5) means BLE, otherwise WiFi.

**Image within a category.** A fixed or failure cycle draws uniformly from its group. A generated cycle draws from
the generated images that accept the cycle's transport; if none does, it falls back to the fixed group. The `image`
draw is `unit_float(seed, index, "image") * len(pool)`.

## Outcome model

`soak_model.expected_after(state, image, transport)` returns the `Expectation` for the cycle. The model sits on a
confirmed image, `state` = (app, slot, confirmed); a valid image installs into the slot the board is not running
from (`state.slot ^ 1`).

| Image | Outcome | What the board must show afterwards |
|---|---|---|
| `fixed`, or `generated` accepted over the cycle's transport | `installs` | app = the image's version, slot = `state.slot ^ 1`, confirmed |
| `bad_sig` | `rejected` | app, slot, confirmed all unchanged |
| `hang` | `rolls_back` | boots the image unconfirmed in slot `state.slot ^ 1`, then rolls back to the previous app/slot, confirmed |
| `no_confirm` | `rolls_back` | same as `hang`; the pending unconfirmed state is read explicitly before the reset |

`expected_after` raises `ValueError` when the model is not on a confirmed image, or when a `generated` image does not
accept the cycle's transport — the planner never produces that second case.

The state carried into the next cycle is `soak_model.next_state(expectation)`, so a rollback returns the model to
where it already was, while an install advances it to the other slot.

## How a cycle is checked

`soak_random._check`, in the order the outcomes are handled:

| Case | Check |
|---|---|
| any failure image | the update log of THIS cycle must show the whole image delivered: WiFi `host served: {'update.bin': N} (image was N bytes)` with all bytes served, BLE `BLE: sector N/N` as the last sector. Otherwise the cycle fails as unverified, so a dead or half-finished link can never pass as a refusal or a rollback |
| `installs` | update returned ok, and the serial snapshot reports `(image.version, expected slot, confirmed)` |
| `rejected` | update did **not** return ok, and `(app, slot, confirmed)` equals the pre-cycle snapshot (`_same`) |
| `rolls_back` while the update reported ok | fail immediately: "a failure image reported a successful update" |
| `no_confirm` (`Expectation.check_pending`) | snapshot must read `(image version, state.slot ^ 1, unconfirmed)`; then `backend.reset()` |
| `hang` | needs positive evidence the hang image really ran: `Task watchdog got triggered` in this cycle's console capture, or `[PASS] running the new image` in the update log. Without it the cycle fails, because the untouched old image looks identical to a rollback |
| `rolls_back` (both) | `backend.wait_snapshot(...)` until app/slot are back and confirmed, within `ROLLBACK_TIMEOUT_S` (120 s) |

The send timeout is the passed `timeout_s` for an `installs` cycle and `REJECT_TIMEOUT_S` (120 s) for a failure
image. `_send` catches any exception from the update CLI and records it as a cycle failure with
`update raised <Type>: <message>` rather than crashing the soak; `run_soak` does the same for an exception anywhere
in the cycle.

## Determinism

| Piece | Behaviour |
|---|---|
| seed | `--seed`; without it the seed is derived from the clock and printed (`seed <N>: {...}`) |
| plan | `soak_model.plan(seed, cycles, catalog, ble_share, failure_cap)` |
| replay | every draw depends only on `(seed, cycle, tag)` and on the failure streak immediately before the cycle, so a longer plan always begins with the shorter one |
| `--dry-run` | prints the plan summary and the first 30 picks, no board, no writes |
| header record | the first line of `cycles.jsonl` is `{"header": plan_id}`, with `plan_id` = seed, cycles, ble_share, failure_cap, `manifest_sha256`, `model_version` (`soak_model.MODEL_VERSION`, bumped whenever picking or expectations change) |
| `manifest_sha256` | sha256 of `json.dumps(manifest["images"], sort_keys=True)` |
| `--resume` | reads the existing `cycles.jsonl` and refuses it if the header does not match the requested plan |

`--resume` therefore has to be given the same seed, cycles, ble-share, failure-cap and pool as the run it continues;
a mismatch stops with `... was written for a different plan ...; refusing to resume it`. An `--out` that already has
a `cycles.jsonl` is rejected without `--resume`. A torn last line (the run was killed mid-write) is dropped on resume;
cycle numbers that are not contiguous from 1 are refused.

## Running it

Native Windows, from the repo checkout (the module docstring's example):

```
python -m tests_hil.soak_random --pool esp_idf\build_pool --port COM14 --board-ip 192.168.1.152 --keys-dir keys --env-file credentials.env --out evidence\bl067_<date> --cycles 200 [--seed N] [--ble-share 0.5] [--resume]
```

Plan only, no board and no writes:

```
python -m tests_hil.soak_random --pool esp_idf\build_pool --out X --cycles 200 --seed N --dry-run
```

`--pool` is the directory holding the BL-069 pool (`manifest.json` plus the `.bin` files); the manifest is loaded
from it. `--port` and `--board-ip` are required for a real run (missing them exits 2), and a rig failure at backend
creation exits 2 as well.

Other flags: `--cycles` (default 200), `--seed`, `--ble-share` (0.5), `--failure-cap` (2), `--pause` (5.0),
`--max-consecutive-unexpected` (3), `--keys-dir`, `--env-file`, `--rig-config`, `--resume`, `--dry-run`,
`--no-console-log`.

### Output directory

| File | Content |
|---|---|
| `cycles.jsonl` | header record, then one record per cycle and per warm-up step: cycle, image, kind, transport, version, ok, cause, expected, observed, duration_s |
| `status.json` | heartbeat, rewritten every cycle: mode, seed, cycle, of, passes |
| `report.json` | final summary |
| `update.log` | update CLI output |
| `console.log` | raw board console capture (omitted with `--no-console-log`) |

### report.json fields

From `soak_random._report`:

| Field | Meaning |
|---|---|
| `mode` | `live` |
| `seed`, `plan` | the seed and the full `plan_id` record |
| `planned_cycles` | cycles in the plan (`len(picks)`) |
| `total_cycles` | cycles actually run, excluding warm-up (`cycle >= 1`) |
| `passes`, `failures` | counts over `total_cycles` |
| `pass_rate_pct` | `passes / total_cycles * 100`, rounded to 2 dp |
| `target_pct` | the pass target, `99.0` |
| `aborted` | true when the consecutive-unexpected limit stopped the run |
| `stopped_early` | true when a `stop_after` limit ended the run before the plan did |
| `final_state_confirmed` | the board was restored to a confirmed image at the end |
| `elapsed_s` | wall time of the run |
| `resumed_from` | number of already-recorded cycles the run skipped |
| `plan_summary` | cycles, per kind, per transport, per image name |
| `by_image`, `by_transport` | total and passes for each image name / transport |
| `generated_slots` | for each generated image that passed, per transport, the sorted list of distinct slots it landed in |
| `failure_log` | cycle, image, transport, cause for every failed cycle |
| `error` | the `SoakError` message when the run stopped on one (for example a failed warm-up), otherwise null |

## Time budget

From the BL-060 run (`docs/LESSONS_LEARNED.md` Trap 24): WiFi cycles run ~32 s each, BLE cycles drift from ~170 s to
~280 s each over a long run, and failure cycles are slower again because a rollback has to be waited out (up to
120 s). At the default 50 % BLE share, 200 cycles is therefore many hours of wall time.

Plan for the drift rather than the first-cycle rate, schedule the run inside a window that fits, and use `--resume`
with the same settings when a window ends mid-run. No single total is quoted here; the cycle mix and the BLE drift
both move it.

## Pass criteria

The run exits 0 only when all three hold:

1. `pass_rate_pct >= 99.0` (`PASS_TARGET_PCT`) over the non-warm-up cycles,
2. `aborted` is false — the run was not stopped by 3 consecutive unexpected outcomes,
3. `final_state_confirmed` is true — the board was brought back to a confirmed image at the end.

Otherwise the runner exits 1; configuration and precondition problems exit 2. Warm-up steps do not count toward the
pass rate.

## Hardware rules

- Run natively on the Windows workstation. Never open COM14 from WSL (`docs/LESSONS_LEARNED.md` R14: the WSL2 /
  `usbipd` bridge drops DTR/RTS on attach and resets the board into the bootloader).
- Serial is for verification only (snapshots, the raw console capture). OTA data travels over WiFi/BLE.
- The runner restores v1 at the end of the run itself, also after an error or Ctrl-C; the board must be on a confirmed image when the run starts.
- Evidence is written to the Windows-side `--out` directory and stays there until it is copied into the repo
  checkout.

## Options added by later runs

| Flag | Use |
|---|---|
| `--infra-retries N` (default 3) | retries for host-side send trouble (a host exception, or an image that never reached the board) while the board is unchanged; counted as `infra_retries` |
| `--rerun-cycles 42,53` (with `--resume`) | executes already-run cycles again first, for cycles that failed because of the runner rather than the board; the log keeps both records and the report counts the latest per cycle |
| `--http-port N` (default 8443) | local HTTPS port for WiFi OTAs; give every parallel run its own |
| `--ble-lock FILE` | one lock file shared by parallel runs so their BLE transfers take turns on the single adapter |
| `--rig-config FILE` | rig file for the run; `host/config/rig-board2.yaml` pins a run to the second board (uid, mac, ip, BLE scan) |

Running two boards at once (BL-072): one process per board with its own `--port`, `--board-ip`, `--rig-config`, `--out` and `--http-port`, the same `--seed` and `--cycles`, and the same `--ble-lock`.
Evidence: `scripts/evidence/bl072_two_boards_2026-09-26/`. Board-vs-board report: `tests_hil/compare_boards.py`.
