#!/usr/bin/env bash
# check_env.sh — verify all tools present and matching scripts/versions.env.
# MUST exit 1 if any item is missing or a version mismatches. No "present (?)".
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/versions.env"

FAIL=0

# fail <name> [msg]
fail() { echo "  [FAIL] $1${2:+ — $2}"; FAIL=1; }

echo "=== bootlab-esp environment check ==="

# --- Python (host) ---
PYV=$(/usr/bin/python3 --version 2>&1 | sed 's/Python //')
echo "python3: $PYV (want ${PYTHON}+)"
if ! [[ "$PYV" =~ ^${PYTHON//./\.} ]]; then fail "python version ($PYV != ${PYTHON}+)"; fi

# --- Host build tools ---
CGV=$(gcc --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
NJV=$(ninja --version 2>/dev/null)
GTV=$(git --version 2>/dev/null | sed 's/git version //')
DTV=$(dtc --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
echo "gcc: ${CGV:-MISSING} (want ${GCC})"
echo "ninja: ${NJV:-MISSING} (want ${NINJA})"
echo "git: ${GTV:-MISSING} (want ${GIT})"
echo "dtc: ${DTV:-MISSING} (want ${DTC})"
[ -n "$CGV" ] || fail "gcc missing"
[ -n "$NJV" ] || fail "ninja missing"
[ -n "$GTV" ] || fail "git missing"
[ -n "$DTV" ] || fail "dtc missing"

# --- Python tooling (bootlab venv) ---
VENV="$SCRIPT_DIR/../.venv/bin"
. "$VENV/activate" 2>/dev/null || { fail "venv not found at $VENV"; }
EV=$(esptool.py version 2>/dev/null | tail -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
IV=$(imgtool version 2>/dev/null | tail -1)
WV=$(west --version 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+')
echo "esptool: ${EV:-MISSING} (want ${ESPTOOL})"
echo "imgtool: ${IV:-MISSING} (want ${IMGTOOL_VERSION})"
echo "west: ${WV:-MISSING} (want ${WEST})"
[ -n "$EV" ] || fail "esptool missing"
[ -n "$IV" ] || fail "imgtool missing"
[ -n "$WV" ] || fail "west missing"

# --- Zephyr workspace: west list resolves zephyr at the pinned tag ---
WESTROOT="$SCRIPT_DIR/.."
if git -C "$WESTROOT/zephyr" rev-parse --git-dir >/dev/null 2>&1; then
  ZREV=$(git -C "$WESTROOT/zephyr" describe --tags 2>/dev/null || git -C "$WESTROOT/zephyr" rev-parse --short HEAD)
  echo "zephyr repo: $ZREV (want ${ZEPHYR_VERSION})"
  [ "$ZREV" = "${ZEPHYR_VERSION}" ] || fail "zephyr revision mismatch ($ZREV)"
else
  fail "zephyr repo not checked out at $WESTROOT/zephyr"
fi

# --- MCUboot resolved via west manifest ---
if git -C "$WESTROOT/modules/lib/mcuboot" rev-parse --git-dir >/dev/null 2>&1; then
  MCREV=$(git -C "$WESTROOT/modules/lib/mcuboot" describe --tags 2>/dev/null || git -C "$WESTROOT/modules/lib/mcuboot" rev-parse --short HEAD)
  echo "mcuboot: $MCREV (from west manifest)"
else
  fail "mcuboot module not checked out (needs west update)"
fi

# --- Zephyr SDK: dir exists + xtensa esp32s3 gcc --version runs ---
ZSDK=""
for cand in "$HOME/tools/zephyr-sdk-1.0.1" "$HOME/tools/zephyr-sdk-$ZEPHYR_SDK_VERSION"; do
  [ -d "$cand" ] && { ZSDK="$cand"; break; }
done
if [ -n "$ZSDK" ]; then
  XGCC=$(find "$ZSDK" -name 'xtensa-espressif_esp32s3_zephyr-elf-gcc' -type f 2>/dev/null | head -1)
  echo "Zephyr SDK: $ZEPHYR_SDK_VERSION  ($ZSDK)"
  if [ -n "$XGCC" ]; then
    "$XGCC" --version 2>/dev/null | head -1 | sed 's/^/  /'
  else
    fail "xtensa esp32s3 toolchain missing in SDK (run setup.sh -t xtensa-espressif_esp32s3_zephyr-elf)"
  fi
else
  fail "Zephyr SDK $ZEPHYR_SDK_VERSION not found (expected ~/tools/zephyr-sdk-$ZEPHYR_SDK_VERSION)"
fi

# --- ESP-IDF: git describe == v6.0.3, 0 uninitialized submodules, idf.py runs ---
IDF="$HOME/tools/esp-idf"
if git -C "$IDF" rev-parse --git-dir >/dev/null 2>&1; then
  IDV=$(git -C "$IDF" describe --tags 2>/dev/null)
  echo "esp-idf: $IDV (want ${ESP_IDF_VERSION})"
  [ "$IDV" = "${ESP_IDF_VERSION}" ] || fail "esp-idf version mismatch ($IDV)"
  # uninitialized submodules
  UNINIT=$(git -C "$IDF" submodule status 2>/dev/null | grep -cE '^-' || true)
  echo "esp-idf uninitialized submodules: $UNINIT"
  [ "$UNINIT" -eq 0 ] || fail "esp-idf has $UNINIT uninitialized submodules"
  # idf.py --version inside IDF env
  if [ -f "$IDF/export.sh" ]; then
    IDFPYV=$(cd "$IDF" && bash -c '. ./export.sh >/dev/null 2>&1 && idf.py --version 2>&1' | tail -1)
    if [ -n "$IDFPYV" ]; then echo "idf.py: $IDFPYV"; else fail "idf.py --version produced no output"; fi
  else
    fail "esp-idf export.sh missing (tools not installed? run ./install.sh esp32s3)"
  fi
else
  fail "esp-idf not a git repo at $IDF"
fi

echo "=== result ==="
[ "$FAIL" -eq 0 ] && echo "ALL TOOLS OK" || echo "MISSING TOOLS / VERSION MISMATCH"
exit $FAIL
