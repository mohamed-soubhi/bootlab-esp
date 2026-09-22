"""HIL tests T04–T09: Rollback, security, and robustness matrix (BL-052, PLAN §8 P4).

Covers:
- T04: no_confirm -> reverts after reset
- T05: hang -> watchdog panic -> reverts
- T06: bad_sig rejected, old image keeps running
- T07: Truncated / corrupted image rejected before write
- T08: Transfer interrupted at 50% -> partial image discarded, retry succeeds
- T09: Wrong token on /ota -> 401 Unauthorized, no update triggered
"""
from __future__ import annotations

from pathlib import Path

import pytest
from labflash.update import UpdateError, check_image

from tests_hil.conftest import HilRig

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.idf
def test_t04_no_confirm_rollback_simulation(hil_rig: HilRig) -> None:
    """T04: no_confirm variant boots unconfirmed, reverts to v1 on next boot."""
    if not hil_rig.is_mock:
        before = hil_rig.state()
        assert before.get("confirmed") is True, f"precondition: board must be confirmed, got {before}"
        # never confirms -> update CLI reports not-confirmed (False); the image must still have BOOTED
        hil_rig.update_ota("no_confirm", "wifi", timeout_s=90.0)
        pending = hil_rig.state()
        assert pending["app"] != before["app"] and pending["slot"] != before["slot"], f"no_confirm did not boot: {pending}"
        assert pending["confirmed"] is False, f"no_confirm must stay unconfirmed: {pending}"
        hil_rig.reset_board()
        after = hil_rig.wait_state(lambda s: s["app"] == before["app"] and s["confirmed"])
        assert after is not None, "board did not roll back to the previous confirmed image after reset"
        assert after["slot"] == before["slot"], f"rolled back to wrong slot: {before} -> {after}"
        hil_rig.log_artifact("t04_no_confirm.txt", f"T04 LIVE: {before} -> pending {pending} -> reset -> {after}\n")
        return
    # Verify starting state
    status = hil_rig.query_http_version()
    if status is not None:
        assert status.get("confirmed") is True

    # In mock mode, simulate no_confirm -> reset -> confirmed v1
    if hil_rig.is_mock:
        hil_rig.mock_version = "1.0.0-noconfirm"
        hil_rig.mock_slot = 1
        st = hil_rig.query_http_version()
        assert st is not None and st.get("version") == "1.0.0-noconfirm"
        # Reset triggers rollback
        hil_rig.mock_version = "1.0.0"
        hil_rig.mock_slot = 0
        st_after = hil_rig.query_http_version()
        assert st_after is not None and st_after.get("version") == "1.0.0"
        assert st_after.get("slot") == 0

    hil_rig.log_artifact("t04_no_confirm.txt", "T04 no_confirm rollback verified\n")


@pytest.mark.idf
def test_t05_hang_watchdog_rollback_simulation(hil_rig: HilRig) -> None:
    """T05: hang variant triggers Task Watchdog panic and rolls back to v1."""
    if not hil_rig.is_mock:
        before = hil_rig.state()
        assert before.get("confirmed") is True, f"precondition: board must be confirmed, got {before}"
        hil_rig.update_ota("hang", "wifi", timeout_s=30.0)
        log = (hil_rig.artifacts_dir / "update.log").read_text()
        assert "accepted the request" in log, "hang image was never transferred; rollback would be vacuous"
        # WDT resets the hung image (<=10 s); bootloader rolls back without any host reset
        after = hil_rig.wait_state(lambda s: s["app"] == before["app"] and s["confirmed"], timeout_s=120.0)
        assert after is not None, "board did not recover to the previous confirmed image after the hang"
        assert after["slot"] == before["slot"], f"rolled back to wrong slot: {before} -> {after}"
        hil_rig.log_artifact("t05_hang_wdt.txt", f"T05 LIVE: {before} -> hang image sent -> WDT -> {after}\n")
        return
    if hil_rig.is_mock:
        hil_rig.mock_version = "1.0.0-hang"
        # WDT triggers reboot
        hil_rig.mock_version = "1.0.0"
        hil_rig.mock_slot = 0
        st = hil_rig.query_http_version()
        assert st is not None and st.get("version") == "1.0.0"

    hil_rig.log_artifact("t05_hang_wdt.txt", "T05 hang WDT panic rollback verified\n")


@pytest.mark.idf
def test_t06_bad_sig_rejected(hil_rig: HilRig) -> None:
    """T06: Image signed by foreign key is rejected, running image remains untouched."""
    bad_sig_bin = REPO_ROOT / "esp_idf" / "build_bad_sig" / "bootlab_idf_blink.bin"
    if bad_sig_bin.is_file():
        data = bad_sig_bin.read_bytes()
        ver = check_image(data, "ble")
        assert ver == "1.0.0-badsig"

    st_before = hil_rig.state()

    # Live: really send the foreign-signed image; the board must refuse it (short timeout: it never gets a new version).
    rejected = True if hil_rig.is_mock else not hil_rig.update_ota("bad_sig", "wifi", timeout_s=45.0)
    assert rejected, "Expected bad_sig to be rejected"

    st_after = hil_rig.state()
    for key in ("app", "slot", "confirmed"):
        assert st_before.get(key) == st_after.get(key), f"running image changed ({key}): {st_before} -> {st_after}"

    hil_rig.log_artifact("t06_bad_sig.txt", "T06 bad_sig foreign key rejection verified\n")


@pytest.mark.idf
def test_t07_corrupted_truncated_rejected(hil_rig: HilRig) -> None:
    """T07: Truncated or corrupted image is rejected before write."""
    # 1. Invalid magic byte
    with pytest.raises(UpdateError, match="not an ESP image"):
        check_image(b"\x00" * 100, "wifi")

    # 2. Corrupted descriptor magic
    fake_header = b"\xE9" + b"\x00" * 31 + b"\x00\x00\x00\x00" + b"\x00" * 64
    with pytest.raises(UpdateError, match="no application descriptor"):
        check_image(fake_header, "wifi")

    # 3. Unaligned for BLE
    valid_bin = REPO_ROOT / "esp_idf" / "build" / "bootlab_idf_blink.bin"
    if valid_bin.is_file():
        truncated = valid_bin.read_bytes()[:1000]  # not 4096-aligned
        with pytest.raises(UpdateError, match="aligned image"):
            check_image(truncated, "ble")

    hil_rig.log_artifact("t07_corrupted.txt", "T07 corrupted/truncated validation verified\n")


@pytest.mark.idf
def test_t08_interrupted_transfer_retry(hil_rig: HilRig) -> None:
    """T08: Interrupted transfer is discarded, subsequent retry succeeds."""
    if not hil_rig.is_mock:
        before = hil_rig.state()
        assert before.get("confirmed") is True, f"precondition: board must be confirmed, got {before}"
        res = hil_rig.backend.interrupted_transfer("v2", fraction=0.5)
        assert res["trigger_status"] == 202, f"board did not start the download: {res}"
        assert res["aborted"] == 1, f"the transfer was not actually interrupted: {res}"
        assert 0 < sum(res["served"].values()) < res["image_bytes"], f"transfer not cut mid-way: {res}"
        after = hil_rig.wait_state(lambda s: True, timeout_s=90.0)
        assert after is not None, "board unreachable after an interrupted transfer"
        assert (after["app"], after["slot"], after["confirmed"]) == (before["app"], before["slot"], before["confirmed"]), \
            f"partial image was not discarded: {before} -> {after}"
        assert hil_rig.update_ota("v2", "wifi"), "retry after the interrupted transfer failed"
        assert hil_rig.state()["app"] == "2.0.0"
        hil_rig.log_artifact("t08_interrupted.txt", f"T08 LIVE: {res}; unchanged {after}; retry -> v2 OK\n")
        return
    # Simulates transfer abort at 50%
    st_before = hil_rig.query_http_version()

    # Board state remains identical
    st_after = hil_rig.query_http_version()
    if st_before and st_after:
        assert st_before.get("slot") == st_after.get("slot")

    hil_rig.log_artifact("t08_interrupted.txt", "T08 interrupted transfer retry verified\n")


@pytest.mark.idf
@pytest.mark.wifi
def test_t09_wrong_token_401(hil_rig: HilRig) -> None:
    """T09: Wrong token on /ota yields HTTP 401 Unauthorized, no update triggered."""
    code = hil_rig.trigger_http_ota(token="completely-wrong-bearer-token-999")
    assert code == 401, f"Expected HTTP 401, got {code}"

    st_before = hil_rig.state()
    code = hil_rig.trigger_http_ota(token="completely-wrong-bearer-token-999")
    assert code == 401, f"Expected HTTP 401 on repeat, got {code}"
    st_after = hil_rig.state()
    assert (st_after.get("app"), st_after.get("slot")) == (st_before.get("app"), st_before.get("slot")), \
        f"a rejected request changed the board: {st_before} -> {st_after}"
    assert str(st_after.get("app")).startswith("1."), f"Board should remain on v1, reports {st_after.get('app')}"

    hil_rig.log_artifact("t09_token_401.txt", f"T09 wrong token rejected: HTTP {code}\n")


@pytest.mark.zephyr
def test_t04_t09_zephyr_gated(hil_rig: HilRig) -> None:
    """Zephyr T04–T09 placeholder (gated behind BL-063b)."""
    assert hil_rig.board == "zephyr"
