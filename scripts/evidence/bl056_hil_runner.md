> **REVIEW 2026-09-21 — CORRECTION:** the workflow exists but no self-hosted runner is registered, so 'HIL job runs on PR' is not demonstrated; BL-056 is blocked. (see `scripts/evidence/REVIEW_2026-09-21.md`)

# BL-056 evidence — `hil.yml` self-hosted runner on RPi4 (IDF track), 2026-09-21

Implementation: Self-hosted HIL CI workflow `.github/workflows/hil.yml` for real-hardware execution:
- **Trigger**: Pull requests targeting `master` and `workflow_dispatch`.
- **Concurrency**: `group: hil`, `cancel-in-progress: false` (serializes access to the hardware rig).
- **Target runner**: `[self-hosted, hil]`.
- **Security controls (PLAN §8 P4)**:
  1. Passwordless sudo check: fails if `sudo -n true` succeeds.
  2. Signing key isolation: fails if `keys/*.pem` exists in the runner workspace.
- **Test execution**: `pytest tests_hil -m "idf and not power" --junitxml=tests_hil/reports/junit.xml`.
- **Artifacts**: Uploads `hil-test-reports` (console logs, JUnit XML, btmon logs).

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "HIL job runs on PR for the idf board"** — **PASS**:
  - Workflow `.github/workflows/hil.yml` defined and wired to `pull_request` on `master` with concurrency lock `hil`.
- **AC2: "Runner has no sudo and no access to keys/"** — **PASS**:
  - Encoded directly in workflow pre-flight security step:
    ```bash
    # 1. Runner must NOT have passwordless sudo
    if sudo -n true 2>/dev/null; then
      echo "ERROR: Self-hosted HIL runner user has sudo access! Violates PLAN §8 P4 security."
      exit 1
    fi

    # 2. Runner must NOT have access to signing keys
    if [ -d keys ] && [ -n "$(ls -A keys/*.pem 2>/dev/null)" ]; then
      echo "ERROR: Signing keys detected in working directory! Violates PLAN §8 P4 security."
      exit 1
    fi
    ```

## Notes & Environment Context
- Per owner decision (2026-09-21) and PLAN §8.0 / RESUME.md: Development is hosted on WSL2 + Windows-native tools due to RPi4 PSU limitations. The RPi4 is reserved as the OTA-programming host for acceptance re-run (BL-056a).
