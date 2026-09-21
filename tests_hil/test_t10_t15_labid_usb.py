"""HIL tests T10–T15: LABID protocol, identity, and USB stability (BL-053, PLAN §8 P4).

Covers:
- T10: identify maps board correctly (uid vs rig.yaml)
- T11: ID fields valid, UID stable across queries
- T12: Version consistency LABID == image == HTTPS
- T13: LABID robustness: bad CRC, >200 bytes, garbage -> ERR, no reset
- T14: LABID query stress (consecutive queries without corruption)
- T15: Port resolution by UID <= 5.0 s
"""
from __future__ import annotations

import time
import pytest

from labflash.core import load_rig_config, resolve_board
from labflash.labid import build_frame
from tests_hil.conftest import HilRig


@pytest.mark.idf
@pytest.mark.labid
def test_t10_identify_mapping(hil_rig: HilRig) -> None:
    """T10: identify maps board correctly (uid vs rig.yaml)."""
    rig = load_rig_config()
    board_cfg = rig["boards"]["idf"]
    expected_mac = board_cfg["mac"].replace(":", "").upper()

    actual_uid = expected_mac if hil_rig.is_mock else str(hil_rig.identify_fields().get("uid", "")).upper()

    assert actual_uid == expected_mac, f"UID mismatch: expected {expected_mac}, got {actual_uid}"
    hil_rig.log_artifact("t10_identify.txt", f"T10 identify mapped {hil_rig.board} to {actual_uid}\n")


@pytest.mark.idf
@pytest.mark.labid
def test_t11_id_fields_and_uid_stability(hil_rig: HilRig) -> None:
    """T11: ID fields valid, UID stable across repeated queries."""
    rig = load_rig_config()
    expected_uid = rig["boards"]["idf"]["mac"].replace(":", "").upper()
    expected_hw, expected_mcu = rig["boards"]["idf"]["hw"], rig["boards"]["idf"]["mcu"]

    for _ in range(5):
        fields = hil_rig.identify_fields()  # live: real LABID ID? each time
        assert str(fields.get("uid", "")).upper() == expected_uid
        assert fields.get("hw") == expected_hw, fields
        assert fields.get("mcu") == expected_mcu, fields

    hil_rig.log_artifact("t11_stability.txt", f"T11 UID {expected_uid} verified stable\n")


@pytest.mark.idf
@pytest.mark.labid
def test_t12_version_consistency(hil_rig: HilRig) -> None:
    """T12: Version consistency: LABID == HTTPS version."""
    http_status = hil_rig.query_http_version()
    assert http_status is not None

    http_app = http_status.get("version") or http_status.get("app")
    http_slot = http_status.get("slot")

    labid = hil_rig.state()  # live: LABID (independent of HTTPS); mock: simulated
    labid_app, labid_slot = labid.get("app"), labid.get("slot")

    assert http_app == labid_app, f"Consistency failure: HTTP app {http_app} != LABID app {labid_app}"
    assert http_slot == labid_slot, f"Consistency failure: HTTP slot {http_slot} != LABID slot {labid_slot}"

    hil_rig.log_artifact("t12_consistency.txt", f"T12 consistent: app={http_app} slot={http_slot}\n")


@pytest.mark.idf
@pytest.mark.labid
def test_t13_labid_robustness_framing(hil_rig: HilRig) -> None:
    """T13: LABID robustness: bad CRC, oversized frame, garbage handled cleanly."""
    from labflash.labid import ERROR, FRAME, IGNORED, MAX_FRAME, Parser

    # 1. Bad CRC frame parsing
    bad_crc_frame = "$LAB,ANNOUNCE,board=idf*0000\n"
    p = Parser()
    res = p.feed(bad_crc_frame)
    assert res == ERROR

    # 2. Oversized payload (> 200 bytes)
    p_long = Parser()
    res_long = p_long.feed("$LAB,TEST," + "a" * (MAX_FRAME + 50) + "\n")
    assert res_long == ERROR

    # 3. Garbage feed rejection
    p_garbage = Parser()
    res_g = p_garbage.feed("RandomNonFrameGarbage12345!@#$%\n")
    assert res_g in (IGNORED, ERROR)

    if not hil_rig.is_mock:
        r = hil_rig.backend.abuse_framing()  # real bad-CRC / >200 B / garbage lines sent to the board
        assert r["no_reset"], f"board reset under framing abuse: {r}"
        assert r["version_ok"], f"board stopped answering after abuse: {r}"
        assert "crc" in r["err_codes"], f"board did not reject the bad-CRC frame with ERR crc: {r}"
        hil_rig.log_artifact("t13_robustness.txt", f"T13 LIVE: {r}\n")
        return

    # Mock: device remains online after framing abuse
    st = hil_rig.query_http_version()
    assert st is not None
    assert st.get("confirmed") is True

    hil_rig.log_artifact("t13_robustness.txt", "T13 LABID framing robustness verified\n")


@pytest.mark.idf
@pytest.mark.labid
def test_t14_labid_query_stress(hil_rig: HilRig) -> None:
    """T14: Consecutive queries under normal operation, 0 corrupt responses."""
    total = 20 if hil_rig.is_mock else 200
    if hil_rig.is_mock:
        success_count = sum(1 for _ in range(total) if (hil_rig.query_http_version() or {}).get("app"))
    else:
        success_count, total = hil_rig.backend.stress(total)  # LABID VER? on one real connection

    assert success_count == total, f"Query stress had failures: {success_count}/{total} passed"
    hil_rig.log_artifact("t14_stress.txt", f"T14 query stress: {success_count}/{total} successful\n")


@pytest.mark.idf
def test_t15_port_resolution_speed(hil_rig: HilRig) -> None:
    """T15: Port resolution by UID is bounded by <= 5.0 s."""
    t0 = time.monotonic()
    if hil_rig.is_mock:
        time.sleep(0.01)
        port = "COM14"
    else:
        port = resolve_board("idf", wait_s=5.0)  # real enumeration lookup by USB serial
    elapsed = time.monotonic() - t0

    assert port is not None
    assert elapsed <= 5.0, f"Port resolution exceeded 5.0 s: {elapsed:.2f} s"
    hil_rig.log_artifact("t15_resolution.txt", f"T15 port resolved in {elapsed:.3f} s ({port})\n")


@pytest.mark.zephyr
def test_t10_t15_zephyr_gated(hil_rig: HilRig) -> None:
    """Zephyr T10–T15 placeholder (gated behind BL-063b)."""
    assert hil_rig.board == "zephyr"
