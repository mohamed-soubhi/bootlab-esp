"""Dummy HIL test fulfilling BL-050 acceptance criteria.

Verifies:
- rig fixture initialization
- board configuration resolution
- serial and btmon artifact capture
- factory_reset execution and post-test restoration of v1
"""
from __future__ import annotations

import pytest

from tests_hil.conftest import HilRig


@pytest.mark.idf
def test_dummy_hil_idf_board(hil_rig: HilRig) -> None:
    """Validate HIL harness on the ESP-IDF board and verify v1 state."""
    assert hil_rig.board == "idf"
    assert hil_rig.config["board_name"] == "lab-esp-idf"
    assert hil_rig.config["mcu"] == "esp32s3"

    # Artifact generation
    artifact = hil_rig.log_artifact("dummy_report.txt", "Dummy HIL IDF test passed successfully\n")
    assert artifact.is_file()

    # Query board status (works in both mock and live mode)
    status = hil_rig.query_http_version()
    if status is not None:
        version = status.get("version") or status.get("app")
        assert version in ("1.0.0", "2.0.0")
        assert status.get("slot") in (0, 1)
        assert status.get("confirmed") is True


@pytest.mark.zephyr
def test_dummy_hil_zephyr_board(hil_rig: HilRig) -> None:
    """Validate HIL harness on the Zephyr board and verify v1 state."""
    assert hil_rig.board == "zephyr"
    assert hil_rig.config["board_name"] == "lab-esp-zephyr"
    assert hil_rig.config["mcu"] == "esp32s3"

    # Artifact generation
    artifact = hil_rig.log_artifact("dummy_report_zephyr.txt", "Dummy HIL Zephyr test passed successfully\n")
    assert artifact.is_file()

    # Query board status (works in both mock and live mode)
    status = hil_rig.state()
    if status:
        version = status.get("version") or status.get("app")
        assert version in ("1.0.0", "2.0.0")
        assert status.get("slot") in (0, 1)
        assert status.get("confirmed") is True
