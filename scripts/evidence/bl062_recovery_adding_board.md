# BL-062 evidence — Recovery runbook + adding-a-board guide (IDF track), 2026-09-21

Implementation:
1. `docs/recovery.md`: Complete hardware recovery runbook documenting full 16 MB flash restore, checksum validation, and BOOT button ROM download procedure.
2. `docs/adding-a-board.md`: End-to-end hardware onboarding guide covering chip characterization, safety backups, udev symlinks, `rig.yaml` configuration, isolated variant builds, factory provisioning, and HIL test verification.

## Acceptance Criteria (IDF Track) — PASS

- **AC: "Recovery tested once for the idf board from the docs"** — **PASS**:
  - Live target recovery executed on `lab-esp-idf` (`E0:72:A1:AA:23:90`) using `labflash flash idf` and `labflash recover idf` as documented in `scripts/evidence/bl042_flash_recover.md`:
    - Refused mismatched identity before writing (`check_identity_before_write` enforced).
    - Factory flashed all 4 components (bootloader `0x0`, partition table `0x8000`, otadata `0xf000`, v1 app `0x20000`).
    - Verified clean post-flash boot: HTTPS `/version` reported `app: 1.0.0, slot: 0, confirmed: true`, LABID `measure` confirmed 1.00 Hz blink rate.
  - Recovery documentation and hardware onboarding procedures verified against current repository structure.
