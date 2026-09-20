#!/usr/bin/env bash
# bootlab-esp — board visibility + identity check (WSL2 side)
#
# Run this after reattach-boards.ps1 (Windows side) has attached both
# boards. Read-only throughout: lsusb, udevadm, esptool chip-id with
# --before no-reset --after no-reset, and `labflash resolve`. Nothing
# here writes, flashes, or erases anything.
#
# Checks, in order:
#   1. lsusb sees the expected VID (303a)
#   2. /dev/lab-esp-* symlinks exist (udev rule working)
#   3. Each symlink's live USB serial matches its expected MAC
#      (host/config/rig.yaml) -- this is the R13 check: a board running
#      normal app firmware may present a placeholder serial like
#      "123456" instead of its MAC, which `labflash resolve` should
#      then correctly refuse to match rather than silently misattribute.
#   4. `labflash resolve` output, both plain and --json
#
# Usage: ./check-boards.sh   (from anywhere; paths below are absolute)

set -uo pipefail  # deliberately not -e: we want every check to run and
                   # report, not abort on the first failure

REPO="$HOME/bootlab-esp"
RIG_YAML="$REPO/host/config/rig.yaml"

# Expected MACs (also in rig.yaml -- duplicated here so this script has
# zero dependencies beyond bash/python3/esptool and can be dropped
# anywhere, including onto a machine that hasn't set up the venv yet)
declare -A EXPECTED_MAC=(
  [lab-esp-zephyr]="ac:a7:04:2c:3b:04"
  [lab-esp-idf]="e0:72:a1:aa:23:90"
)

PASS=0
FAIL=0

pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }
info() { echo "  info: $*"; }

echo "=== 1. lsusb — Espressif devices (VID 303a) ==="
if command -v lsusb >/dev/null 2>&1; then
    LSUSB_OUT="$(lsusb 2>&1)"
    echo "$LSUSB_OUT" | grep -i '303a' || true
    COUNT=$(echo "$LSUSB_OUT" | grep -ci '303a' || true)
    if [ "$COUNT" -ge 2 ]; then
        pass "found $COUNT device(s) at VID 303a (expected 2)"
    elif [ "$COUNT" -eq 1 ]; then
        fail "only 1 device at VID 303a (expected 2) -- one board likely not attached or still in download mode (303a:4001)"
    else
        fail "0 devices at VID 303a -- neither board attached. Run reattach-boards.ps1 on the Windows side."
    fi
else
    info "lsusb not installed, skipping (labflash resolve below doesn't need it)"
fi
echo

echo "=== 2. udev symlinks (/dev/lab-esp-*) ==="
for name in lab-esp-zephyr lab-esp-idf; do
    if [ -L "/dev/$name" ]; then
        target="$(readlink -f "/dev/$name" 2>/dev/null || echo '?')"
        pass "/dev/$name -> $target"
    else
        fail "/dev/$name does not exist (udev rule not applied, or board not present)"
    fi
done
echo

echo "=== 3. Live USB serial vs expected MAC (the R13 check) ==="
echo "    A board running normal app firmware may present a placeholder"
echo "    serial (e.g. '123456') instead of its MAC -- see PLAN.md R13."
echo
for name in lab-esp-zephyr lab-esp-idf; do
    dev="/dev/$name"
    expected="${EXPECTED_MAC[$name]}"
    if [ ! -e "$dev" ]; then
        fail "$name: device path missing, can't check serial"
        continue
    fi

    # Prefer udevadm (fast, no serial I/O) over esptool for this specific
    # check; fall back to esptool chip-id if udevadm can't find the attr.
    real_dev="$(readlink -f "$dev")"
    sysfs_serial="$(udevadm info -q property -n "$real_dev" 2>/dev/null \
                     | grep -i '^ID_SERIAL_SHORT=' | cut -d= -f2)"

    if [ -n "$sysfs_serial" ]; then
        norm_serial="$(echo "$sysfs_serial" | tr 'A-F' 'a-f' | sed 's/../&:/g;s/:$//')"
        # udevadm's ID_SERIAL_SHORT is usually the raw hex MAC without
        # colons (e.g. ACA7042C3B04); normalize both sides for comparison
        norm_expected="$(echo "$expected" | tr -d ':' | tr 'A-F' 'a-f')"
        norm_actual="$(echo "$sysfs_serial" | tr -d ':' | tr 'A-F' 'a-f')"

        if [ "$norm_actual" = "$norm_expected" ]; then
            pass "$name: udev serial matches expected MAC ($sysfs_serial)"
        else
            fail "$name: udev serial is '$sysfs_serial', expected MAC '$expected' -- placeholder/mismatch (R13 in effect)"
        fi
    else
        info "$name: udevadm gave no ID_SERIAL_SHORT, falling back to esptool chip-id (read-only)"
        chip_out="$(esptool --port "$dev" --before no-reset --after no-reset chip-id 2>&1)"
        if echo "$chip_out" | grep -qi "$expected"; then
            pass "$name: esptool chip-id confirms MAC $expected"
        else
            fail "$name: esptool chip-id did not confirm MAC $expected. Output:"
            echo "$chip_out" | sed 's/^/         /'
        fi
    fi
done
echo

echo "=== 4. labflash resolve ==="
cd "$REPO" || { fail "cannot cd to $REPO"; }
if [ -x ".venv/bin/python3" ]; then
    PY=".venv/bin/python3"
else
    PY="python3"
    info "using system python3, not .venv (venv not found at $REPO/.venv)"
fi

echo "--- plain ---"
$PY -m labflash resolve 2>&1 | sed 's/^/  /'
echo
echo "--- --json ---"
$PY -m labflash resolve --json 2>&1 | sed 's/^/  /'
echo

echo "=== Summary ==="
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo
    echo "  If boards are missing entirely: run reattach-boards.ps1 on Windows first."
    echo "  If a board shows 303a:4001 in 'usbipd list' on Windows: it's stuck in"
    echo "    ROM download mode -- hold BOOT, tap RESET, release BOOT, then retry."
    echo "  If serial mismatch (section 3) but board IS visible: this is the R13"
    echo "    finding -- expected once app firmware is flashed and running normally,"
    echo "    not yet fixed at the firmware level. Not a bug in this script."
    exit 1
fi
exit 0
