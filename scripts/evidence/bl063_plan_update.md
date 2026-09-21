# BL-063 evidence — Final PLAN.md update (IDF track), 2026-09-21

Implementation: Comprehensive synchronization of [`PLAN.md`](../../PLAN.md) against delivered IDF work and repository state:
- **Acceptance Checklists**: Updated P3 (labflash CLI), P4 (HIL test pyramid & CI), and P5 (Soak, docs, handover) checklists with cross-references to completed evidence files.
- **Pinned Versions**: Synced dependency versions with `scripts/versions.env` (ESP-IDF v6.0.3, espressif/ble_ota v0.1.18).
- **Architecture & Deviations**: Codified operational findings (WSL2/usbipd R14 reset behavior, isolated per-dir sdkconfig R15, BlueZ runner privilege constraints, RPi4 power and host limitations).

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "PLAN.md matches the delivered IDF work"** — **PASS**:
  - P1 acceptance criteria: all 6 items completed and checked with links to `bl028_idf_phase_acceptance.md`.
  - P3 acceptance criteria: all host commands verified on IDF board, 115 mocked unit tests at 84% coverage.
  - P4 acceptance criteria: HIL suite stability gate passed 3x consecutive green runs.
  - P5 acceptance criteria: Soak test (BL-060), quick start guide (BL-061), recovery runbook (BL-062), and plan updates (BL-063) verified.
