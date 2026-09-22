#!/usr/bin/env bash
# BL-033: Run Zephyr self-test unit tests under Twister (native_sim).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZEPHYR_BASE="${ZEPHYR_BASE:-/home/msoubhi/zephyrproject/zephyr}"
export ZEPHYR_BASE
export ZEPHYR_TOOLCHAIN_VARIANT=host

# Clean PATH from Windows mounts to prevent slow 9P network RPCs in WSL2
CLEAN_PATH=$(echo "$PATH" | tr ':' '\n' | grep -v '^/mnt/c' | paste -sd: -)
export PATH="$CLEAN_PATH"

TWISTER="$ZEPHYR_BASE/scripts/twister"
PYTHON="$ROOT/.venv/bin/python"

echo "=== Running Zephyr Twister Tests (native_sim) ==="
"$PYTHON" "$TWISTER" -T "$ROOT/esp_zephyr/tests/self_test" -p native_sim -v --outdir "$ROOT/twister-out"
