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

## Acceptance Criteria (Zephyr Track) — PASS
- **AC: "Builds all 5 Zephyr images (v1, v2, no_confirm, hang, bad_sig)"** — PASS.

### Live Run Output (`python -m labflash build zephyr` verification):
```
=== Zephyr Build & Signature Verification Results ===
Variant      Version          Size (B)   Symbol Check    Signature   
---------------------------------------------------------------------------
v1           1.0.0            140779     PASS            PASS        
  -> esp_zephyr/app/build_v1/app/zephyr/zephyr.signed.bin (verified with primary key keys/zephyr_p256.pem)
v2           2.0.0            139436     PASS            PASS        
  -> esp_zephyr/app/build_v2/app/zephyr/zephyr.signed.bin (verified with primary key keys/zephyr_p256.pem)
no_confirm   1.0.0-noconfirm  139355     PASS            PASS        
  -> esp_zephyr/app/build_no_confirm/app/zephyr/zephyr.signed.bin (verified with primary key keys/zephyr_p256.pem)
hang         1.0.0-hang       139340     PASS            PASS        
  -> esp_zephyr/app/build_hang/app/zephyr/zephyr.signed.bin (verified with primary key keys/zephyr_p256.pem)
bad_sig      1.0.0-badsig     139450     PASS            PASS        
  -> esp_zephyr/app/build_bad_sig/app/zephyr/zephyr.signed.bin (refused by primary key, verified with foreign key keys/zephyr_foreign.pem)

All 5 built Zephyr variants verified successfully (PLAN R15).
```

## Zephyr Build Guardrails
- **Isolated per-variant build directories**: `-d esp_zephyr/app/build_<variant>`.
- **Kconfig overlay**: `-Dapp_EXTRA_CONF_FILE=<overlay>`.
- **Sysbuild overlay**: `-DSB_EXTRA_CONF_FILE=<sysbuild_conf>` (for signing with `keys/zephyr_foreign.pem` on `bad_sig`).
- **Post-build symbol verification**: reads `<build_dir>/app/zephyr/.config` after build and confirms expected symbol.
- **Post-build signature verification**: verified using `imgtool verify -k <key> <binary>`.
