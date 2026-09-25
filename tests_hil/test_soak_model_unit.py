"""BL-067: the pure model behind the randomized soak (seeded picker + expected-outcome model). Owner: Claude wrote the
spec, the cheap agent implements tests_hil/soak_model.py."""
from __future__ import annotations

import hashlib

import pytest
from labflash import imagefmt as fmt
from labflash import imagegen as gen
from labflash import poolmanifest as pm

from tests_hil import soak_model as sm


def _manifest():
    entries = []
    for i, v in enumerate(gen.gen_pool("soakmodel")):
        sl = {"near_limit": fmt.SLOT_SIZE - 4096 * 3, "too_big": fmt.SLOT_SIZE + 4096 * 5}.get(
            v.role, 1_249_280 + fmt.align_up(v.pad_bytes))
        data = bytes([i + 1]) * 64 + b"\0" * (sl + v.trailer_len - 64)
        entries.append(pm.make_entry(i, v, f"g{i:02d}.bin", data, sl))
    return pm.make_manifest("soakmodel", entries)


@pytest.fixture(scope="module")
def catalog():
    return sm.build_catalog(_manifest())


def test_unit_float_is_the_pinned_shake256_stream():
    want = int.from_bytes(hashlib.shake_256(b"7:3:transport").digest(8), "big") / 2**64
    assert sm.unit_float(7, 3, "transport") == want
    assert 0.0 <= sm.unit_float(1, 1, "x") < 1.0
    assert sm.unit_float(7, 3, "a") != sm.unit_float(7, 3, "b")


def test_catalog_fixed_failure_and_generated_images(catalog):
    assert [i.version for i in catalog.fixed] == ["1.0.0", "2.0.0", "3.0.0", "4.0.0"]
    assert [i.name for i in catalog.fixed] == ["v1", "v2", "v3", "v4"]
    assert {i.failure for i in catalog.failures} == {"bad_sig", "hang", "no_confirm"}
    assert {i.name: i.version for i in catalog.failures} == {
        "bad_sig": "1.0.0-badsig", "hang": "1.0.0-hang", "no_confirm": "1.0.0-noconfirm"}
    assert all(i.kind == "fixed" and i.accepts == {"wifi": True, "ble": True} for i in catalog.fixed)
    assert all(i.kind == "failure" for i in catalog.failures)
    m = _manifest()
    assert {i.version for i in catalog.generated} == {e["version"] for e in m["images"] if e["role"] != "too_big"}
    assert all(i.kind == "generated" and i.file for i in catalog.generated)


def test_generated_acceptance_comes_from_the_manifest(catalog):
    by_version = {e["version"]: e for e in _manifest()["images"]}
    for img in catalog.generated:
        e = by_version[img.version]
        assert img.accepts == {t: e["expected"][t]["accept"] for t in ("wifi", "ble")}
    assert any(not i.accepts["ble"] for i in catalog.generated)          # the unaligned-trailer ones


def test_catalog_without_a_manifest_has_no_generated_images():
    assert sm.build_catalog(None).generated == ()


def test_plan_is_deterministic_prefix_stable_and_seed_sensitive(catalog):
    a = sm.plan(1234, 200, catalog)
    assert a == sm.plan(1234, 200, catalog)
    assert sm.plan(1234, 50, catalog) == a[:50]
    assert sm.plan(1235, 200, catalog) != a
    assert len(a) == 200


@pytest.mark.parametrize("share", [0.5, 0.3])
def test_transport_share(catalog, share):
    picks = sm.plan(99, 4000, catalog, ble_share=share)
    got = sum(p.transport == "ble" for p in picks) / len(picks)
    assert abs(got - share) < 0.03


def test_mix_is_about_70_10_20(catalog):
    picks = sm.plan(5, 6000, catalog)
    n = len(picks)
    fixed = sum(p.image.kind == "fixed" for p in picks) / n
    generated = sum(p.image.kind == "generated" for p in picks) / n
    failure = sum(p.image.kind == "failure" for p in picks) / n
    assert abs(fixed - 0.70) < 0.04 and abs(generated - 0.10) < 0.03 and 0.17 < failure < 0.22


@pytest.mark.parametrize("cap", [0, 1, 2, 3])
def test_failure_images_never_exceed_the_consecutive_cap(catalog, cap):
    picks = sm.plan(42, 3000, catalog, failure_cap=cap)
    run = longest = 0
    for p in picks:
        run = run + 1 if p.image.kind == "failure" else 0
        longest = max(longest, run)
    assert longest <= cap
    if cap == 0:
        assert not any(p.image.kind == "failure" for p in picks)


def test_every_pick_is_accepted_by_its_transport(catalog):
    for p in sm.plan(8, 3000, catalog):
        if p.image.kind != "failure":
            assert p.image.accepts[p.transport], (p.image.name, p.transport)


def test_every_image_gets_picked_over_a_long_run(catalog):
    names = {p.image.name for p in sm.plan(3, 6000, catalog)}
    assert {"v1", "v2", "v3", "v4", "bad_sig", "hang", "no_confirm"} <= names
    assert len([n for n in names if n.startswith("gen-")]) >= 8


def test_without_generated_images_that_share_falls_back_to_fixed():
    cat = sm.build_catalog(None)
    picks = sm.plan(5, 2000, cat)
    assert not any(p.image.kind == "generated" for p in picks)
    assert sum(p.image.kind == "fixed" for p in picks) / len(picks) > 0.75


def _img(catalog, name):
    return next(i for i in (*catalog.fixed, *catalog.failures, *catalog.generated) if i.name == name or i.version == name)


def test_expected_after_a_valid_install(catalog):
    e = sm.expected_after(sm.State("1.0.0", 0, True), _img(catalog, "v3"), "wifi")
    assert (e.outcome, e.app, e.slot, e.confirmed) == ("installs", "3.0.0", 1, True)
    assert e.pending_app is None


def test_expected_after_bad_sig_leaves_the_board_alone(catalog):
    e = sm.expected_after(sm.State("2.0.0", 1, True), _img(catalog, "bad_sig"), "ble")
    assert (e.outcome, e.app, e.slot, e.confirmed) == ("rejected", "2.0.0", 1, True)


@pytest.mark.parametrize("name,version", [("no_confirm", "1.0.0-noconfirm"), ("hang", "1.0.0-hang")])
def test_expected_after_a_failure_image_rolls_back_to_the_last_confirmed(catalog, name, version):
    e = sm.expected_after(sm.State("4.0.0", 0, True), _img(catalog, name), "wifi")
    assert e.outcome == "rolls_back"
    assert (e.app, e.slot, e.confirmed) == ("4.0.0", 0, True)
    assert (e.pending_app, e.pending_slot) == (version, 1)


def test_expected_after_refuses_impossible_requests(catalog):
    unaligned = next(i for i in catalog.generated if not i.accepts["ble"])
    with pytest.raises(ValueError):
        sm.expected_after(sm.State("1.0.0", 0, True), unaligned, "ble")
    with pytest.raises(ValueError):
        sm.expected_after(sm.State("1.0.0", 0, False), _img(catalog, "v2"), "wifi")     # model must sit on a confirmed image


def test_next_state_is_the_expected_final_state(catalog):
    s = sm.State("1.0.0", 0, True)
    e = sm.expected_after(s, _img(catalog, "v2"), "wifi")
    assert sm.next_state(e) == sm.State("2.0.0", 1, True)
    e2 = sm.expected_after(sm.next_state(e), _img(catalog, "hang"), "wifi")
    assert sm.next_state(e2) == sm.State("2.0.0", 1, True)


def test_replaying_a_plan_through_the_model_keeps_state_consistent(catalog):
    s = sm.State("1.0.0", 0, True)
    for p in sm.plan(11, 500, catalog):
        s = sm.next_state(sm.expected_after(s, p.image, p.transport))
        assert s.confirmed and s.slot in (0, 1)


def test_plan_summary_counts(catalog):
    summary = sm.plan_summary(sm.plan(2, 300, catalog))
    assert summary["cycles"] == 300 and sum(summary["by_kind"].values()) == 300
    assert sum(summary["by_transport"].values()) == 300 and sum(summary["by_image"].values()) == 300


def test_only_no_confirm_asks_for_the_pending_check(catalog):
    s = sm.State("1.0.0", 0, True)
    assert sm.expected_after(s, _img(catalog, "no_confirm"), "wifi").check_pending is True
    assert sm.expected_after(s, _img(catalog, "hang"), "wifi").check_pending is False
    assert sm.expected_after(s, _img(catalog, "bad_sig"), "wifi").check_pending is False
    assert sm.expected_after(s, _img(catalog, "v2"), "wifi").check_pending is False


def test_a_valid_image_never_repeats_the_version_already_running(catalog):
    running = "1.0.0"
    for p in sm.plan(21, 4000, catalog):
        if p.image.kind != "failure":
            assert p.image.version != running, p
            running = p.image.version


def test_start_app_is_respected(catalog):
    first = sm.plan(4, 300, catalog, start_app="3.0.0")
    assert not any(p.image.version == "3.0.0" for p in first[:1] if p.image.kind != "failure")


def test_model_version_is_bumped_for_the_new_picker():
    assert sm.MODEL_VERSION == 2
