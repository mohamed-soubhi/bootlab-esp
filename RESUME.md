# RESUME NOTES — bootlab-esp (RPi restart checkpoint, 2026-09-16)

## Where we are
Repo: ~/bootlab-esp. Committed clean (see git log). `.west/` and `zephyr/`
are west-managed and gitignored.

## Ticket discipline corrections (owner) — applied
- BL-002 reopen -> doing: RE-PIN in progress.
  - Zephyr -> v4.4.2 (latest 4.4.x, verified from GitHub tags)
  - Zephyr SDK -> 1.0.1 (latest, verified from sdk-ng tags)
  - ESP-IDF -> v6.0.3 (kept)
  - MCUBOOT_VERSION removed from versions.env (comes from west manifest;
    record resolved rev after west update). Done in versions.env + west.yml.
  - esp-iot-solution ble_ota: still PENDING pin — check component registry for
    an ESP-IDF-6.0-declared version; if none -> ESCALATE.
- BL-003 done -> blocked (boards not on USB)
- BL-007 done -> blocked (boards not on USB)
- BL-004 stays done (backups verified, no board needed)
- BL-005 blocked (needs owner flash approval)
- BL-011 done -> doing (REOPENED): must (a) load test_vectors.json in C tests,
  (b) gcov branch "Taken at least once" >= 90%.
- rig.yaml typo fixed: worldseni_ws2812 -> worldsemi_ws2812.

## NEXT ACTIONS — resume here after restart

### BL-002 (in progress)
1. Fresh venv: cd ~/bootlab-esp && python3 -m venv .venv && source .venv/bin/activate
   && pip install west imgtool esptool pyyaml mypy
2. Zephyr workspace: west init -l . (topdir must be bootlab-esp).
   The earlier `west init -l .` resolved topdir to /home/msa (wrong). Fix:
   ensure .west/config [manifest] path=. inside bootlab-esp, then
   `west update` (name-allowlist: hal_espressif, mcuboot, zcbor, mbedtls,
   tinycrypt, segger). The zephyr/ dir is PARTIALLY cloned (update was killed
   by timeout) — rerun west update to finish.
   Record resolved MCUboot revision after update.
3. Zephyr SDK 1.0.1 linux-aarch64 minimal + only xtensa esp32s3 toolchain:
   download from sdk-ng releases; ./setup.sh -t xtensa-espressif_esp32s3_zephyr-elf -c
4. ESP-IDF v6.0.3 already cloned at ~/tools/esp-idf (verified). Run:
   ~/tools/esp-idf/install.sh esp32s3  (then export.sh)
5. check_env.sh: must FAIL (exit 1) on ANY missing/mismatch. No "present (?)".
   - west list resolves zephyr at v4.4.2
   - SDK dir exists + xtensa esp32s3 gcc --version runs
   - git describe --tags in esp-idf == v6.0.3, 0 uninitialized submodules
   - idf.py --version runs inside IDF env
6. Build proof (BUILD ONLY, no flash):
   - Zephyr: samples/hello_world for esp32s3_devkitc/esp32s3/procpu
   - IDF: examples/get-started/hello_world for esp32s3
   Paste last lines of both.

### BL-011 (reopened)
- Make tests/gen_test_vectors_h.py run (emits C header from test_vectors.json)
  into the build, and have test_labid.c iterate those arrays (LOAD the JSON).
- Rebuild, re-run Unity, recompute gcov with `-b` and report "Taken at least
  once" branch >= 90% (not just "Branches executed").

### BL-012..BL-014 (no board access)
- BL-012: finish libFuzzer build, run 10-min fuzz (0 crashes / 0 sanitizer).
- BL-013: DONE already (labid.py, all vectors pass, mypy clean).
- BL-014: LABID as Zephyr module (zephyr/module.yml) + IDF component
  (idf_component.yml); build native_sim + IDF linux target.

## Guardrails (PLAN §10) — never
Burn eFuses, commit keys/ backups/ *.pem, install IDF toolchain without
verifying it matches versions.env, flash without identity confirmation.
