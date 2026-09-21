# BL-045 evidence — `labflash build` orchestration (IDF track), 2026-09-21

Implementation: `host/labflash/build.py`, wired into `host/labflash/__main__.py` and `scripts/build_all.sh`.
Tests: `host/tests/test_build.py` (7 tests, all passing; full host suite: 39 passed).

## Acceptance Criteria (IDF Track) — PASS
- **AC: "Builds all 5 IDF images (v1, v2, no_confirm, hang, bad_sig)"** — PASS.

### Live Run Output (`python -m labflash build idf` / `scripts/build_all.sh`):
```
=== Build & Signature Verification Results ===
Variant      Version          Size (B)   Symbol Check    Signature   
---------------------------------------------------------------------------
v1           1.0.0            1249280    PASS            PASS        
  -> /home/msoubhi/bootlab-esp/esp_idf/build/bootlab_idf_blink.bin (verified with primary key (keys/idf_sbv2.pem))
v2           2.0.0            1249280    PASS            PASS        
  -> /home/msoubhi/bootlab-esp/esp_idf/build_v2/bootlab_idf_blink.bin (verified with primary key (keys/idf_sbv2.pem))
no_confirm   1.0.0-noconfirm  1249280    PASS            PASS        
  -> /home/msoubhi/bootlab-esp/esp_idf/build_no_confirm/bootlab_idf_blink.bin (verified with primary key (keys/idf_sbv2.pem))
hang         1.0.0-hang       266240     PASS            PASS        
  -> /home/msoubhi/bootlab-esp/esp_idf/build_hang/bootlab_idf_blink.bin (verified with primary key (keys/idf_sbv2.pem))
bad_sig      1.0.0-badsig     1249280    PASS            PASS        
  -> /home/msoubhi/bootlab-esp/esp_idf/build_bad_sig/bootlab_idf_blink.bin (refused by primary key, verified with foreign key (keys/idf_foreign.pem))

All built variants verified successfully (PLAN R15).
```

## PLAN R15 Guardrail Enforcement
- **Isolated per-variant build directories**: `-B esp_idf/build*`.
- **Per-directory sdkconfig**: `-DSDKCONFIG=<build_dir>/sdkconfig` and `-DSDKCONFIG_DEFAULTS=...`.
- **Stale project sdkconfig removal**: deletes any project-level `esp_idf/sdkconfig` before building so it never contaminates variant builds.
- **Post-build symbol verification**: reads `<build_dir>/sdkconfig` after the build and verifies `CONFIG_APP_VARIANT_<X>=y`.
- **Post-build signature verification**:
  - `v1`, `v2`, `no_confirm`, `hang`: verified against `keys/idf_sbv2.pem`.
  - `bad_sig`: verified against `keys/idf_foreign.pem` AND confirmed rejected when checked against primary key `keys/idf_sbv2.pem`.

## Zephyr Gate Enforcement
Attempting to build the Zephyr track (`labflash build zephyr`) fails closed:
```
$ python -m labflash build zephyr
[BLOCKED] Zephyr track is on hold pending BL-063b (HTML presentation & retrospective) per replan (2026-09-21).
```
(Exit code: 2)
