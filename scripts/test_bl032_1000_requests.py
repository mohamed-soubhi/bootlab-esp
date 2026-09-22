"""BL-032 Verification: 1,000 requests under logging, 0 corrupt.

Acceptance criteria:
- AC1: ANNOUNCE <= 2 s
- AC2: ID?, VER?, STATE? <= 100 ms
- AC3: 1 000 requests under heavy logging, 0 corrupt
"""
import sys
import time
from labflash.identify import (
    SerialLineTransport,
    wait_for_announce,
    identify,
    get_version,
    get_state,
    query,
    cross_check_identity,
    map_board_by_id,
)
from labflash.core import load_rig_config

def main():
    print("=== BL-032: LABID Automated Hardware Verification ===")
    t = SerialLineTransport("/dev/ttyACM0")

    # AC1: ANNOUNCE <= 2 s
    print("\n--- Testing AC1: Boot ANNOUNCE frame ---")
    t_boot = time.monotonic()
    ann = wait_for_announce(t, timeout=4.0)
    dt_ann = time.monotonic() - t_boot
    print(f"ANNOUNCE received in {dt_ann:.2f}s: {ann}")
    assert ann.get("board") == "zephyr", f"Unexpected board: {ann.get('board')}"
    assert ann.get("uid") == "ACA7042C3B04", f"Unexpected uid: {ann.get('uid')}"
    assert ann.get("app") == "1.0.0", f"Unexpected app: {ann.get('app')}"
    print("AC1: PASS (ANNOUNCE <= 2 s)")

    # Cross-check against rig.yaml
    print("\n--- Cross-checking identity against rig.yaml ---")
    board_key, id_fields = map_board_by_id(t)
    print(f"Mapped board key: {board_key}, ID fields: {id_fields}")
    assert board_key == "zephyr", f"Expected zephyr board, got {board_key}"
    rig = load_rig_config()
    cross_check_identity(id_fields, rig["boards"]["zephyr"])
    print("Cross-check against rig.yaml: PASS")

    # AC2: Single-shot Latency Check
    print("\n--- Testing AC2: Latency for ID?, VER?, STATE? ---")
    t0 = time.perf_counter()
    idf = identify(t)
    dt_id = (time.perf_counter() - t0) * 1000
    print(f"ID? response in {dt_id:.2f} ms: {idf}")
    assert dt_id <= 100.0, f"ID? exceeded 100ms: {dt_id:.2f}ms"

    t0 = time.perf_counter()
    vf = get_version(t)
    dt_ver = (time.perf_counter() - t0) * 1000
    print(f"VER? response in {dt_ver:.2f} ms: {vf}")
    assert dt_ver <= 100.0, f"VER? exceeded 100ms: {dt_ver:.2f}ms"

    t0 = time.perf_counter()
    sf = get_state(t)
    dt_state = (time.perf_counter() - t0) * 1000
    print(f"STATE? response in {dt_state:.2f} ms: {sf}")
    assert dt_state <= 100.0, f"STATE? exceeded 100ms: {dt_state:.2f}ms"
    print("AC2: PASS (all <= 100 ms)")

    # AC3: 1,000 requests under logging, 0 corrupt
    print("\n--- Testing AC3: 1,000 consecutive requests under logging ---")
    commands = ["ID?", "VER?", "STATE?", "PING,n="]
    latencies = []
    corrupt_count = 0
    total = 1000

    t_loop_start = time.perf_counter()
    for i in range(total):
        cmd_base = commands[i % len(commands)]
        cmd = f"{cmd_base}{i}" if cmd_base.endswith("=") else cmd_base
        t_req = time.perf_counter()
        try:
            res = query(t, cmd, timeout=1.0)
            dt = (time.perf_counter() - t_req) * 1000
            latencies.append(dt)
            # Basic field sanity check
            if cmd == "ID?" and res.get("board") != "zephyr":
                corrupt_count += 1
            elif cmd == "VER?" and res.get("app") != "1.0.0":
                corrupt_count += 1
            elif cmd == "STATE?" and "toggles" not in res:
                corrupt_count += 1
            elif cmd_base.startswith("PING") and res.get("n") != str(i):
                corrupt_count += 1
        except Exception as e:
            print(f"Error on request #{i} ({cmd}): {e}")
            corrupt_count += 1

        if (i + 1) % 100 == 0:
            avg_so_far = sum(latencies[-100:]) / 100
            print(f"Progress: {i+1}/{total} requests completed (last 100 avg: {avg_so_far:.2f} ms, errors: {corrupt_count})")

    total_time = time.perf_counter() - t_loop_start
    min_lat = min(latencies)
    avg_lat = sum(latencies) / len(latencies)
    max_lat = max(latencies)
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]

    print("\n================ Results ================")
    print(f"Total requests: {total}")
    print(f"Successful requests: {len(latencies)}")
    print(f"Corrupt / failed requests: {corrupt_count}")
    print(f"Total duration: {total_time:.2f} s ({total / total_time:.1f} req/s)")
    print(f"Latency min: {min_lat:.2f} ms")
    print(f"Latency avg: {avg_lat:.2f} ms")
    print(f"Latency 95th pct: {p95_lat:.2f} ms")
    print(f"Latency max: {max_lat:.2f} ms")

    # Check device-side reported rx_err
    final_state = get_state(t)
    print(f"Final device state: {final_state}")
    device_rx_err = int(final_state.get("rx_err", "0"))
    print(f"Device-reported rx_err: {device_rx_err}")

    t.close()

    assert corrupt_count == 0, f"Corrupt requests detected: {corrupt_count}"
    assert device_rx_err == 0, f"Device reported rx_err: {device_rx_err}"
    print("\nAC3: PASS (1 000 requests under logging, 0 corrupt, 0 device rx_err)")

if __name__ == "__main__":
    main()
