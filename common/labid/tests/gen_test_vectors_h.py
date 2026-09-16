#!/usr/bin/env python3
"""gen_test_vectors_h.py — BL-011: turn test_vectors.json into a C header
so the Unity host tests consume the SAME JSON as the Python labid self-test
(single source of truth). Run at build time via CMake.

Usage: python3 gen_test_vectors_h.py <vectors.json> <out.h>
"""
import json
import sys

def main():
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <vectors.json> <out.h>")
    vectors = json.load(open(sys.argv[1]))
    out = []
    w = out.append
    w("/* Auto-generated from test_vectors.json by gen_test_vectors_h.py */")
    w("#ifndef TEST_VECTORS_H")
    w("#define TEST_VECTORS_H")
    # crc check
    cc = vectors["crc_check"]
    w(f'#define CRC_CHECK_INPUT "{cc["input"]}"')
    w(f'#define CRC_CHECK_VAL 0x{cc["crc"]}u')
    # valid
    w("static const char *TEST_VALID[] = {")
    for f in vectors["valid"]:
        w(f'    "{esc(f)}",')
    w("    NULL")
    w("};")
    # bad_crc
    w("static const char *TEST_BAD_CRC[] = {")
    for f in vectors["bad_crc"]:
        w(f'    "{esc(f)}",')
    w("    NULL")
    w("};")
    # too_long
    w("static const char *TEST_TOO_LONG[] = {")
    for f in vectors["too_long"]:
        w(f'    "{esc(f)}",')
    w("    NULL")
    w("};")
    # unknown_keys
    w("static const char *TEST_UNKNOWN_KEYS[] = {")
    for f in vectors["unknown_keys"]:
        w(f'    "{esc(f)}",')
    w("    NULL")
    w("};")
    # garbage (non-frames)
    w("static const char *TEST_GARBAGE[] = {")
    for f in vectors["garbage"]:
        w(f'    "{esc(f)}",')
    w("    NULL")
    w("};")
    w("#endif /* TEST_VECTORS_H */")
    open(sys.argv[2], "w").write("\n".join(out) + "\n")
    print(f"wrote {sys.argv[2]}")

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

if __name__ == "__main__":
    main()
