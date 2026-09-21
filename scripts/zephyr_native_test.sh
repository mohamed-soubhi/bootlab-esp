#!/usr/bin/env bash
# BL-014b — build and RUN the LABID Zephyr module on the Zephyr native_sim target.
#
# Proves the packaged Zephyr module (labid.c parser/writer + labid_dispatch.c) builds and
# behaves under Zephyr native_sim. Exit status is the smoke test's: 0 = every check passed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZEPHYR_BASE="${ZEPHYR_BASE:-/home/msoubhi/zephyrproject/zephyr}"
TEST_DIR="$ROOT/esp_zephyr/test"
BUILD_DIR="$TEST_DIR/build"
EXE="$BUILD_DIR/zephyr/zephyr.exe"

# shellcheck disable=SC1090
. "$ROOT/.venv/bin/activate"
export ZEPHYR_BASE
export ZEPHYR_TOOLCHAIN_VARIANT=host

# Build the native_sim smoke test
west build -b native_sim "$TEST_DIR" -d "$BUILD_DIR" -p auto

# Run the executable
"$EXE"
