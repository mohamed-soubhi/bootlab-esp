# BL-002 — Zephyr hello_world build proof (DONE)

Date: 2026-09-16
Status: SUCCESS (rc=0)

## What was built
  board  : esp32s3_devkitc/esp32s3/procpu
  app    : zephyr/samples/hello_world (Zephyr v4.4.2)
  build  : ~/zephyr-ws/build/hello_world_esp32s3

## Successful tail (clean)
```
esptool now resolves to: /home/msa/bootlab-esp/.venv/bin/esptool v5.4.0
[1/1] Linking C executable zephyr/zephyr.elf
Generating files from .../zephyr.elf for board: esp32s3_devkitc/esp32s3/procpu
esptool v5.4.0
Creating ESP32-S3 image...
Successfully created ESP32-S3 image.
ZEPHYR_HELLO_BUILD_DONE rc=0
```

## Artifacts
  FLASH: 134868 B (1.61% of 8MB)
  zephyr.bin = 134868 B   (present)
  zephyr.elf             (present)

## Root cause + fix (full diagnostic chain)
- SYMPTOM: `west build` failed 3x at image-gen:
  `esptool: error: unrecognized arguments: --flash-mode --flash-freq 80m --flash-size 8MB <elf>`
- WRONG HYPOTHESIS: esptool 5.x CLI incompatibility / Zephyr CMake bug.
  Verified NO upstream fix needed: Zephyr 4.4.2 AND upstream main BOTH already
  emit the correct `elf2image` subcommand form (soc/espressif/common/CMakeLists.txt);
  build.ninja:1826 + `ninja -t commands` confirmed the resolved rule is correct.
- CORRECTION: the executed command was produced by `esptool` resolving via PATH
  to the Debian SYSTEM esptool v4.7.0 (`/usr/bin/esptool`, old pre-`elf2image`
  CLI) — NOT the venv 5.4.0. The agent shell PATH did not place .venv/bin first.
- FIX: `export PATH="$HOME/bootlab-esp/.venv/bin:$PATH"` before `west build` ->
  esptool v5.4.0 (has `elf2image`) -> clean image. rc=0.

## Checks (per gate)
  git fsck        : clean (only benign dangling blob), fsck_exit=0
  boards          : kept unplugged throughout (build-only, no flash)
  ESP-IDF proof   : unchanged (shared venv esptool 5.4.0 untouched)

## For reproducibility
This PATH shadowing is specific to this host's agent-shell PATH (Hermes venv
first, bootlab .venv NOT on PATH). Any future Zephyr build for an ESP board on
this host must ensure ~/bootlab-esp/.venv/bin precedes /usr/bin on PATH.
