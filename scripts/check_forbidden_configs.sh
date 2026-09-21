#!/usr/bin/env bash
# check_forbidden_configs.sh — CI safety checks (BL-055 / PLAN §10).
# Ensures no eFuse burn commands, no hardware secure boot in defaults, and no committed keys/secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Checking for forbidden eFuse burning commands..."
if git -C "$ROOT" grep -iE "burn_efuse|burn_key|burn_bit" -- ":!PLAN.md" ":!RESUME.md" ":!scripts/evidence/*"; then
    echo "ERROR: Forbidden eFuse burning command found!"
    exit 1
fi

echo "Checking sdkconfig.defaults for hardware secure boot / flash encryption..."
if grep -q "CONFIG_SECURE_BOOT=y" "$ROOT/esp_idf/sdkconfig.defaults"; then
    echo "ERROR: CONFIG_SECURE_BOOT=y found in sdkconfig.defaults (must be software signed apps only)!"
    exit 1
fi
if grep -q "CONFIG_SECURE_FLASH_ENC_ENABLED=y" "$ROOT/esp_idf/sdkconfig.defaults"; then
    echo "ERROR: CONFIG_SECURE_FLASH_ENC_ENABLED=y found in sdkconfig.defaults!"
    exit 1
fi

echo "Checking for committed keys or secrets..."
if git -C "$ROOT" ls-files "*.pem" "credentials.env" "keys/*.pem" | grep -q .; then
    echo "ERROR: Key files or credentials committed to git!"
    exit 1
fi

echo "All forbidden-config checks passed!"
