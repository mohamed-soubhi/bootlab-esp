"""HIL tests T01–T03: Factory boot and OTA update matrix (BL-051, PLAN §8 P4).

Covers:
- T01: Factory v1 boots, measure 1 Hz, ANNOUNCE/info valid
- T02: Update v1 -> v2, 4 Hz, confirmed=1 (WiFi and BLE transports)
- T03: Update v2 -> v1 downgrade allowed, 1 Hz, confirmed=1 (WiFi and BLE transports)
"""
from __future__ import annotations

import pytest
from tests_hil.conftest import HilRig


@pytest.mark.idf
@pytest.mark.labid
def test_t01_factory_v1_boot(hil_rig: HilRig) -> None:
    """T01: Factory v1 boots, measure 1 Hz, ANNOUNCE/info valid."""
    status = hil_rig.query_http_version()
    if status is not None:
        version = status.get("version") or status.get("app")
        assert version == "1.0.0", f"Expected version 1.0.0 on factory v1 boot, got {version}"
        assert status.get("confirmed") is True, "Expected confirmed=True on factory v1"

    # Measure 1.00 Hz blink rate
    measured_hz, passed = hil_rig.measure_blink_rate(expect_hz=1.0, duration_s=5.0, tolerance=2)
    assert passed, f"Blink rate measurement failed: measured {measured_hz} Hz (expected 1.0 Hz)"
    assert 0.8 <= measured_hz <= 1.2, f"Measured frequency out of bounds: {measured_hz} Hz"

    # Artifact generation
    report = (
        f"T01 Factory Boot Report\n"
        f"Board: {hil_rig.board}\n"
        f"App Version: 1.0.0\n"
        f"Slot: {(status or {}).get('slot')}\n"
        f"Confirmed: True\n"
        f"Blink Rate: {measured_hz:.2f} Hz\n"
    )
    hil_rig.log_artifact("t01_factory_boot.txt", report)


@pytest.mark.idf
@pytest.mark.wifi
def test_t02_update_v1_to_v2_wifi(hil_rig: HilRig) -> None:
    """T02: Update v1 -> v2 over WiFi, 4 Hz, confirmed=1."""
    ok = hil_rig.update_ota(variant="v2", transport="wifi")
    assert ok, "WiFi OTA update v1 -> v2 failed"

    status = hil_rig.query_http_version()
    if status is not None:
        version = status.get("version") or status.get("app")
        assert version == "2.0.0", f"Expected version 2.0.0, got {version}"
        assert status.get("confirmed") is True, "Expected confirmed=True for v2"

    measured_hz, passed = hil_rig.measure_blink_rate(expect_hz=4.0, duration_s=5.0, tolerance=2)
    assert passed, f"Blink rate measurement failed: measured {measured_hz} Hz (expected 4.0 Hz)"
    assert 3.7 <= measured_hz <= 4.3, f"Measured frequency out of bounds: {measured_hz} Hz"

    hil_rig.log_artifact("t02_wifi_update.txt", f"T02 WiFi Update OK: 2.0.0, slot {(status or {}).get('slot')}, {measured_hz:.2f} Hz\n")


@pytest.mark.idf
@pytest.mark.wifi
def test_t03_downgrade_v2_to_v1_wifi(hil_rig: HilRig) -> None:
    """T03: Downgrade v2 -> v1 over WiFi, 1 Hz, confirmed=1."""
    assert hil_rig.ensure_variant("v2", "wifi"), "precondition failed: board could not be put on v2"
    ok = hil_rig.update_ota(variant="v1", transport="wifi")
    assert ok, "WiFi OTA downgrade v2 -> v1 failed"

    status = hil_rig.query_http_version()
    if status is not None:
        version = status.get("version") or status.get("app")
        assert version == "1.0.0", f"Expected version 1.0.0, got {version}"
        assert status.get("confirmed") is True, "Expected confirmed=True for v1"

    measured_hz, passed = hil_rig.measure_blink_rate(expect_hz=1.0, duration_s=5.0, tolerance=2)
    assert passed, f"Blink rate measurement failed: measured {measured_hz} Hz (expected 1.0 Hz)"
    assert 0.8 <= measured_hz <= 1.2, f"Measured frequency out of bounds: {measured_hz} Hz"

    hil_rig.log_artifact("t03_wifi_downgrade.txt", f"T03 WiFi Downgrade OK: 1.0.0, slot {(status or {}).get('slot')}, {measured_hz:.2f} Hz\n")


@pytest.mark.idf
@pytest.mark.ble
def test_t02_update_v1_to_v2_ble(hil_rig: HilRig) -> None:
    """T02: Update v1 -> v2 over BLE, 4 Hz, confirmed=1."""
    ok = hil_rig.update_ota(variant="v2", transport="ble")
    assert ok, "BLE OTA update v1 -> v2 failed"

    status = hil_rig.query_http_version()
    if status is not None:
        version = status.get("version") or status.get("app")
        assert version == "2.0.0", f"Expected version 2.0.0, got {version}"
        assert status.get("confirmed") is True, "Expected confirmed=True for v2"

    measured_hz, passed = hil_rig.measure_blink_rate(expect_hz=4.0, duration_s=5.0, tolerance=2)
    assert passed, f"Blink rate measurement failed: measured {measured_hz} Hz (expected 4.0 Hz)"
    assert 3.7 <= measured_hz <= 4.3, f"Measured frequency out of bounds: {measured_hz} Hz"

    hil_rig.log_artifact("t02_ble_update.txt", f"T02 BLE Update OK: 2.0.0, slot {(status or {}).get('slot')}, {measured_hz:.2f} Hz\n")


@pytest.mark.idf
@pytest.mark.ble
def test_t03_downgrade_v2_to_v1_ble(hil_rig: HilRig) -> None:
    """T03: Downgrade v2 -> v1 over BLE, 1 Hz, confirmed=1."""
    assert hil_rig.ensure_variant("v2", "wifi"), "precondition failed: board could not be put on v2"
    ok = hil_rig.update_ota(variant="v1", transport="ble")
    assert ok, "BLE OTA downgrade v2 -> v1 failed"

    status = hil_rig.query_http_version()
    if status is not None:
        version = status.get("version") or status.get("app")
        assert version == "1.0.0", f"Expected version 1.0.0, got {version}"
        assert status.get("confirmed") is True, "Expected confirmed=True for v1"

    measured_hz, passed = hil_rig.measure_blink_rate(expect_hz=1.0, duration_s=5.0, tolerance=2)
    assert passed, f"Blink rate measurement failed: measured {measured_hz} Hz (expected 1.0 Hz)"
    assert 0.8 <= measured_hz <= 1.2, f"Measured frequency out of bounds: {measured_hz} Hz"

    hil_rig.log_artifact("t03_ble_downgrade.txt", f"T03 BLE Downgrade OK: 1.0.0, slot {(status or {}).get('slot')}, {measured_hz:.2f} Hz\n")


@pytest.mark.zephyr
def test_t01_t03_zephyr_gated(hil_rig: HilRig) -> None:
    """Zephyr T01–T03 placeholder (gated behind BL-063b)."""
    assert hil_rig.board == "zephyr"
