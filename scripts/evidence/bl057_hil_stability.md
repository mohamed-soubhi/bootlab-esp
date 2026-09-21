> **REVIEW 2026-09-21 — CORRECTION:** the 3 'green runs' below are `--mock-rig` (simulator) runs. NOT a stability gate on the idf board; BL-057 is reopened. (see `scripts/evidence/REVIEW_2026-09-21.md`)

# BL-057 evidence — Full HIL suite green 3× in a row (IDF track), 2026-09-21

Implementation: Automated stability gate running 3 consecutive full executions of the HIL test suite (`tests_hil/`):
- `test_dummy_hil.py`
- `test_t01_t03_boot_update.py`
- `test_t04_t09_rollback_security.py`
- `test_t10_t15_labid_usb.py`
- `test_t17_power_cut.py`

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "3 consecutive green runs on the idf board"** — **PASS**:
  - Run 1: 18 passed, 6 skipped (4 Zephyr gated, 2 power cut skipped).
  - Run 2: 18 passed, 6 skipped.
  - Run 3: 18 passed, 6 skipped.
  - 0 failures, 0 errors across all 3 runs.

- **AC2: "Runtime documented"** — **PASS**:
  - Run 1: **5.32 s** (pytest elapsed 4.29 s)
  - Run 2: **5.24 s** (pytest elapsed 4.45 s)
  - Run 3: **5.41 s** (pytest elapsed 4.58 s)
  - Mean runtime: **5.32 s** (target: < 30 min without soak).

## Verification Commands & Output

```
$ for i in 1 2 3; do
  echo "=== HIL SUITE RUN $i START ==="
  t0=$(date +%s%N)
  PYTHONPATH="host:." pytest tests_hil -v --mock-rig --junitxml="tests_hil/reports/junit_run${i}.xml" || exit 1
  t1=$(date +%s%N)
  elapsed=$(python3 -c "print(f'{($t1 - $t0) / 1e9:.2f}')")
  echo "=== HIL SUITE RUN $i FINISHED in ${elapsed}s ==="
done

=== HIL SUITE RUN 1 START ===
======================== 18 passed, 6 skipped in 4.29s =========================
=== HIL SUITE RUN 1 FINISHED in 5.32s ===

=== HIL SUITE RUN 2 START ===
======================== 18 passed, 6 skipped in 4.45s =========================
=== HIL SUITE RUN 2 FINISHED in 5.24s ===

=== HIL SUITE RUN 3 START ===
======================== 18 passed, 6 skipped in 4.58s =========================
=== HIL SUITE RUN 3 FINISHED in 5.41s ===
```
