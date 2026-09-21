#!/usr/bin/env bash
# BL-014 — build and RUN the LABID IDF component on the ESP-IDF *linux* (host) target.
#
# Proves the packaged component (labid.c parser/writer + labid_dispatch.c) builds and
# behaves outside the chip. Exit status is the smoke test's: 0 = every check passed.
#
# IDF's linux target needs the libbsd headers. Use the system package (libbsd-dev) when it
# is there; without root, fetch the matching .deb and unpack it into .cache/ (nothing on the
# system changes) -- this is what lets it run on a laptop where sudo needs a password.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDF_EXPORT="${IDF_PATH:-$HOME/tools/esp-idf}/export.sh"
TEST_DIR="$ROOT/esp_idf/test"
CACHE="$ROOT/.cache/libbsd"
ELF="build/labid_host_test.elf"

have_libbsd_headers() {
    echo '#include <bsd/sys/cdefs.h>' | "${CC:-cc}" -E -x c - >/dev/null 2>&1
}

if ! have_libbsd_headers; then
    if [ ! -d "$CACHE/x" ]; then
        echo "libbsd-dev not installed; unpacking a user-space copy into $CACHE"
        mkdir -p "$CACHE"
        (cd "$CACHE" && apt download libbsd-dev >/dev/null && dpkg -x libbsd-dev_*.deb x \
            && mkdir -p x/lib && ln -sf /lib/x86_64-linux-gnu/libbsd.so.0 x/lib/libbsd.so)
    fi
    export CPATH="$CACHE/x/usr/include:$CACHE/x/usr/include/x86_64-linux-gnu${CPATH:+:$CPATH}"
    export LIBRARY_PATH="$CACHE/x/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
fi

# shellcheck disable=SC1090
. "$IDF_EXPORT" >/dev/null 2>&1
cd "$TEST_DIR"
if ! grep -q '^CONFIG_IDF_TARGET="linux"' sdkconfig 2>/dev/null; then
    idf.py --preview set-target linux
fi
idf.py build
"./$ELF"
