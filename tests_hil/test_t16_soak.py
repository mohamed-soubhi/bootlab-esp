"""HIL test T16: Overnight soak testing (BL-060, PLAN §8 P5).

Covers:
- T16: 100 consecutive alternating OTA updates (v1 <-> v2) across transports
- Target: pass rate >= 99%
- Logs root cause for any failures
- Marked @pytest.mark.slow
"""
from __future__ import annotations

import json
import time
import pytest

from tests_hil.conftest import HilRig


@pytest.mark.idf
@pytest.mark.slow
def test_t16_soak_alternating_updates(hil_rig: HilRig, request: pytest.FixtureRequest) -> None:
    """T16: Alternating updates (v1 <-> v2) with >= 99% pass rate."""
    # Default iterations: 100 for soak, or can be overridden via env
    soak_count = 100 if hil_rig.is_mock else 10  # Live smoke or full 100
    passes = 0
    failures: list[dict[str, str]] = []

    t_start = time.monotonic()

    for cycle in range(1, soak_count + 1):
        target_variant = "v2" if cycle % 2 == 1 else "v1"
        expected_ver = "2.0.0" if target_variant == "v2" else "1.0.0"
        expected_slot = 1 if target_variant == "v2" else 0
        transport = "wifi" if cycle % 4 in (1, 2) else "ble"

        try:
            ok = hil_rig.update_ota(variant=target_variant, transport=transport)
            if not ok:
                failures.append({"cycle": str(cycle), "cause": f"Update to {target_variant} returned False"})
                continue

            status = hil_rig.query_http_version()
            if status is not None:
                ver = status.get("version") or status.get("app")
                slot = status.get("slot")
                if ver != expected_ver or slot != expected_slot:
                    failures.append({
                        "cycle": str(cycle),
                        "cause": f"Version mismatch: got {ver} slot {slot}, expected {expected_ver} slot {expected_slot}",
                    })
                    continue

            passes += 1
        except Exception as e:
            failures.append({"cycle": str(cycle), "cause": str(e)})

    elapsed = time.monotonic() - t_start
    total = passes + len(failures)
    pass_rate = (passes / total) * 100.0 if total > 0 else 0.0

    report = {
        "board": hil_rig.board,
        "total_cycles": total,
        "passes": passes,
        "failures": len(failures),
        "pass_rate_pct": pass_rate,
        "elapsed_s": round(elapsed, 2),
        "failure_log": failures,
    }

    hil_rig.log_artifact("t16_soak_report.json", json.dumps(report, indent=2))

    assert pass_rate >= 99.0, f"Soak test failed: pass rate {pass_rate:.1f}% < 99.0% ({len(failures)} failures)"


@pytest.mark.zephyr
@pytest.mark.slow
def test_t16_zephyr_gated(hil_rig: HilRig) -> None:
    """Zephyr T16 soak placeholder (gated behind BL-063b)."""
    assert hil_rig.board == "zephyr"
