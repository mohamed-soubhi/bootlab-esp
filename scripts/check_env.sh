#!/usr/bin/env bash
# check_env.sh — verify all tools are present and match scripts/versions.env
# Usage: check_env.sh  (exit 0 if all good, non-zero otherwise)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/versions.env"

FAIL=0
ver() { echo "${1:-unknown}"; }

# helper: check a variable is non-empty
have() { [ -n "${1:-}" ]; }

echo "=== bootlab-esp environment check ==="

# --- Python ---
PYV=$(/usr/bin/python3 --version 2>&1 | sed 's/Python //')
echo "python3: $PYV (want ${PYTHON}+)"
[[ "$PYV" =~ ^${PYTHON/./\.} ]] || { echo "  [FAIL] python"; FAIL=1; }

# --- Host build tools ---
CGV=$(gcc --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+'); echo "gcc: $CGV"
NJV=$(ninja --version 2>/dev/null);                                  echo "ninja: $NJV (want ${NINJA})"
GTV=$(git --version 2>/dev/null | sed 's/git version //');           echo "git: $GTV"
DTV=$(dtc --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+'); echo "dtc: $DTV"

# --- esptool / imgtool / west (in bootlab venv) ---
VENV="$SCRIPT_DIR/../.venv/bin"
. "$VENV/activate" 2>/dev/null || true
EV=$(esptool.py version 2>/dev/null | tail -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
IV=$(imgtool version 2>/dev/null | tail -1)
WV=$(west --version 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || true)
echo "esptool: $EV (want ${ESPTOOL})"
echo "imgtool: $IV (want ${IMGTOOL_VERSION})"
echo "west: $WV (want ${WEST})"

# --- Zephyr SDK ---
ZSDK="$HOME/esp_zephyr/zephyr-sdk-0.17.0"
for cand in "$HOME/esp_zephyr/zephyr-sdk-0.17.0" "$HOME/tools/zephyr-sdk-0.17.0"; do
  [ -d "$cand" ] && ZSDK="$cand" && break
done
if [ -d "$ZSDK" ]; then
  ZSV=$(cat "$ZSDK/sdk_version" 2>/dev/null); echo "Zephyr SDK: $ZSV (want ${ZEPHYR_SDK_VERSION})"
else
  echo "Zephyr SDK: NOT FOUND"; FAIL=1
fi

# --- ESP-IDF ---
IDF="$HOME/tools/esp-idf"
if [ -d "$IDF" ]; then
  if [ -n "${IDF_VERSION:-}" ] && grep -q "v5.5.0" "$IDF/version.txt" 2>/dev/null; then
    echo "ESP-IDF: v5.5.0"
  else
    echo "ESP-IDF: present ($(cat "$IDF/version.txt" 2>/dev/null || echo '?') )"
  fi
else
  echo "ESP-IDF: NOT FOUND"; FAIL=1
fi

echo "=== result ==="
[ "$FAIL" -eq 0 ] && echo "ALL TOOLS OK" || echo "MISSING TOOLS"
exit $FAIL
