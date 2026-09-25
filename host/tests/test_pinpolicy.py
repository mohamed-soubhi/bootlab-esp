"""BL-069: safe-pin allowlist for generated images (AC4). Owner: Claude."""
from pathlib import Path

import pytest
from labflash import pinpolicy as pp

ALL_S3_GPIOS = set(range(22)) | set(range(26, 49))   # ESP32-S3 has no GPIO22-25
DOC = Path(__file__).resolve().parents[2] / "docs" / "BL069_IMAGE_POOL.md"


def test_allowlist_and_groups_partition_every_gpio():
    excluded = set()
    for name, (pins, _reason) in pp.EXCLUDED_PIN_GROUPS.items():
        assert not (excluded & pins), f"group {name} overlaps an earlier group"
        excluded |= pins
    assert not (excluded & pp.SAFE_OUTPUT_PINS)
    assert excluded | pp.SAFE_OUTPUT_PINS == ALL_S3_GPIOS


def test_every_excluded_group_has_a_reason():
    for name, (pins, reason) in pp.EXCLUDED_PIN_GROUPS.items():
        assert pins and len(reason.strip()) >= 20, name


def test_safe_pins_exclude_the_known_hazards():
    hazards = {0, 3, 45, 46, 19, 20, 43, 44, 48} | set(range(26, 38))
    assert not (hazards & pp.SAFE_OUTPUT_PINS)


@pytest.mark.parametrize("pin", [0, 3, 19, 20, 26, 32, 37, 43, 44, 45, 46, 48])
def test_hazard_pins_refused(pin):
    with pytest.raises(pp.PinNotAllowedError):
        pp.check_pins([pin])


def test_every_excluded_pin_refused():
    for pins, _ in pp.EXCLUDED_PIN_GROUPS.values():
        for pin in pins:
            with pytest.raises(pp.PinNotAllowedError):
                pp.check_pins([pin])


@pytest.mark.parametrize("pin", [-1, 22, 23, 24, 25, 49, 100])
def test_nonexistent_pins_refused(pin):
    with pytest.raises(pp.PinNotAllowedError):
        pp.check_pins([pin])


def test_safe_pins_accepted_and_returned_as_tuple():
    pins = sorted(pp.SAFE_OUTPUT_PINS)[:2]
    assert pp.check_pins(pins) == tuple(pins)
    assert pp.check_pins([]) == ()


def test_one_bad_pin_among_good_refuses_all():
    with pytest.raises(pp.PinNotAllowedError):
        pp.check_pins([min(pp.SAFE_OUTPUT_PINS), 48])


def test_doc_lists_every_group_and_every_safe_pin():
    text = DOC.read_text(encoding="utf-8")
    for name in pp.EXCLUDED_PIN_GROUPS:
        assert name in text, f"doc missing excluded group {name}"
    for pin in pp.SAFE_OUTPUT_PINS:
        assert f"GPIO{pin}" in text, f"doc missing safe pin GPIO{pin}"
