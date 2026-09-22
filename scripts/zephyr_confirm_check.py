#!/usr/bin/env python3
"""BL-033 live acceptance check for image self-test & confirmation on the Zephyr board."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "host"))

from labflash.identify import (
    SerialLineTransport,
    _read_frame,
    query,
    get_state,
    get_version,
    identify,
    map_board_by_id,
    measure,
)

PORT = "/dev/ttyACM0"
BAUD = 115200

def main():
    print(f"=== BL-033 Confirmation Check on {PORT} ===")
    t0 = time.monotonic()
    tr = SerialLineTransport(PORT, BAUD, timeout=0.02)
    print("Port opened. Waiting up to 4.0s for boot ANNOUNCE...")

    # 1. Catch boot ANNOUNCE
    deadline = time.monotonic() + 4.0
    announced = False
    while time.monotonic() < deadline:
        got = _read_frame(tr, deadline)
        if got and got[0] == "ANNOUNCE":
            print(f"[{time.monotonic()-t0:.2f}s] SUCCESS: Received ANNOUNCE: {got[1]}")
            announced = True
            break

    if not announced:
        print("Warning: ANNOUNCE not seen, querying board directly...")

    # 2. Early window check (uptime < 4000 ms)
    st = get_state(tr)
    uptime_ms = int(st.get("uptime_ms", 999999))
    toggles = int(st.get("toggles", 0))
    print(f"Early STATE?: {st}")
    print(f"Current uptime={uptime_ms} ms, toggles={toggles}")

    ver = get_version(tr)
    print(f"Early VER?: {ver}")
    confirmed_early = ver.get("confirmed", "")

    early_ok = (uptime_ms < 4000 and confirmed_early == "0")
    print(f"Early check (uptime < 4s -> confirmed == '0'): {'PASS' if early_ok else 'FAIL'} (confirmed={confirmed_early})")
    assert early_ok, f"Expected confirmed == '0' early, got {confirmed_early}"

    # 3. Wait until uptime >= 5500 ms
    target_uptime = 5500
    print(f"Waiting until uptime >= {target_uptime} ms...")
    while uptime_ms < target_uptime:
        time.sleep(0.4)
        st = get_state(tr)
        uptime_ms = int(st.get("uptime_ms", 0))
        print(f"  [Waiting] uptime={uptime_ms} ms, toggles={st.get('toggles')}")

    # 4. Check post-5s confirmation
    ver_post = get_version(tr)
    print(f"Post-5s VER?: {ver_post}")
    confirmed_post = ver_post.get("confirmed", "")
    st_post = get_state(tr)
    print(f"Post-5s STATE?: {st_post}")

    post_ok = (confirmed_post == "1")
    print(f"Post-5s check (uptime >= 5.5s -> confirmed == '1'): {'PASS' if post_ok else 'FAIL'}")
    assert post_ok, f"Expected confirmed == '1' after 5s, got {confirmed_post}"

    # 5. Check ID? and measure (BL-041 verification)
    print("\n--- Testing BL-041 identify and measure on Zephyr board ---")
    idf = identify(tr)
    print(f"identify(): {idf}")
    assert idf.get("uid") == "ACA7042C3B04", f"Expected uid ACA7042C3B04, got {idf.get('uid')}"
    assert idf.get("board") == "zephyr", f"Expected board zephyr, got {idf.get('board')}"

    board_key, id_fields = map_board_by_id(tr)
    print(f"map_board_by_id(): board={board_key}")
    assert board_key == "zephyr"

    delta, hz, meas_ok = measure(tr, duration_s=4.0, expect_hz=1.0)
    print(f"measure(4.0s): delta={delta} toggles, measured_hz={hz:.2f} Hz, passed={meas_ok}")
    assert meas_ok, f"Expected measure to pass, got delta={delta}, hz={hz}"

    tr.close()
    print("\nALL ACs PASSED for BL-033 and BL-041 on Zephyr hardware!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
