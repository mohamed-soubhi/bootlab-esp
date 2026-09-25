"""BL-069 AC5: hardware-free tests for the pool install schedule. Owner: cheap agent implements, Claude wrote the spec."""
from __future__ import annotations

import itertools

import pytest
from labflash import imagefmt as fmt
from labflash import imagegen as gen
from labflash import poolmanifest as pm

from tests_hil import pool_schedule as ps


def _manifest():
    entries = []
    for i, v in enumerate(gen.gen_pool("sched")):
        sl = {"near_limit": fmt.SLOT_SIZE, "too_big": fmt.SLOT_SIZE + fmt.SECTOR}.get(
            v.role, 1_249_280 + fmt.align_up(v.pad_bytes))
        data = bytes([i]) * 16 + b"\0" * (sl + v.trailer_len - 16)
        entries.append(pm.make_entry(i, v, f"g{i:02d}.bin", data, sl))
    return pm.make_manifest("sched", entries)


def _valid(m, transport):
    return [e for e in m["images"] if e["expected"][transport]["accept"]]


def test_wifi_steps_all_precede_ble_steps():
    steps = ps.plan_sweeps(_manifest())
    transports = [s.transport for s in steps if not s.skip]
    first_ble = transports.index("ble")
    assert set(transports[:first_ble]) == {"wifi"} and set(transports[first_ble:]) == {"ble"}


def test_each_accepted_image_appears_once_per_sweep_per_transport():
    m = _manifest()
    steps = ps.plan_sweeps(m, sweeps=2)
    for t in ("wifi", "ble"):
        want = sorted(e["index"] for e in _valid(m, t))
        for sweep in (1, 2):
            got = sorted(s.image_index for s in steps if s.transport == t and s.sweep == sweep and s.expect_accept)
            assert got == want, (t, sweep)


def test_second_sweep_order_differs_from_first():
    steps = ps.plan_sweeps(_manifest(), sweeps=2)
    for t in ("wifi", "ble"):
        s1 = [s.image_index for s in steps if s.transport == t and s.sweep == 1 and s.expect_accept]
        s2 = [s.image_index for s in steps if s.transport == t and s.sweep == 2 and s.expect_accept]
        assert s1 != s2


@pytest.mark.parametrize("start_slot", [0, 1])
def test_every_accepted_image_lands_on_both_slots_per_transport(start_slot):
    m = _manifest()
    steps = ps.plan_sweeps(m, sweeps=2, start_slot=start_slot)
    for t in ("wifi", "ble"):
        for e in _valid(m, t):
            slots = {s.expected_slot for s in steps if s.transport == t and s.image_index == e["index"] and s.expect_accept}
            assert slots == {0, 1}, (t, e["index"], slots)


def test_predicted_slot_flips_on_each_accepted_install_only():
    steps = ps.plan_sweeps(_manifest(), start_slot=0)
    slot = 0
    for s in steps:
        if s.skip:
            assert s.expected_slot is None
        elif s.expect_accept:
            slot ^= 1
            assert s.expected_slot == slot
        else:
            assert s.expected_slot == slot


def test_too_big_is_an_expected_reject_once_per_transport_in_sweep_one():
    m = _manifest()
    steps = ps.plan_sweeps(m, sweeps=2)
    big = [s for s in steps if s.image_index == 12]
    assert sorted(s.transport for s in big) == ["ble", "wifi"]
    assert all(not s.expect_accept and not s.skip and s.sweep == 1 and s.expected_version is None for s in big)


def test_ble_skips_the_unaligned_images_with_the_manifest_reason():
    m = _manifest()
    steps = ps.plan_sweeps(m, sweeps=2)
    unaligned = {e["index"] for e in m["images"] if e["role"] == "unaligned_trailer"}
    skipped = [s for s in steps if s.skip]
    assert {s.image_index for s in skipped} == unaligned and all(s.transport == "ble" for s in skipped)
    assert all(s.skip_reason.strip() for s in skipped)
    assert not [s for s in steps if s.transport == "wifi" and s.skip]


def test_steps_carry_manifest_file_and_version():
    m = _manifest()
    for s in ps.plan_sweeps(m):
        e = m["images"][s.image_index]
        assert s.file == e["file"]
        if s.expect_accept:
            assert s.expected_version == e["version"]


def test_step_keys_are_unique_and_stable():
    a, b = ps.plan_sweeps(_manifest()), ps.plan_sweeps(_manifest())
    assert [s.key for s in a] == [s.key for s in b]
    assert len({s.key for s in a}) == len(a)


def test_remaining_skips_done_keys_and_keeps_order():
    steps = ps.plan_sweeps(_manifest())
    done = {s.key for s in steps[:5]}
    assert ps.remaining(steps, done) == steps[5:]
    assert ps.remaining(steps, set()) == steps


def _result(step, accepted=True, confirmed=True, slot=None, version=None):
    return {"key": step.key, "image_index": step.image_index, "transport": step.transport,
            "accepted": accepted, "confirmed": confirmed,
            "slot": step.expected_slot if slot is None else slot,
            "version": step.expected_version if version is None else version}


def test_classify():
    m = _manifest()
    steps = ps.plan_sweeps(m)
    ok = next(s for s in steps if s.expect_accept)
    assert ps.classify(ok, _result(ok)) == "pass"
    assert ps.classify(ok, _result(ok, confirmed=False)) == "fail"
    assert ps.classify(ok, _result(ok, accepted=False)) == "fail"
    assert ps.classify(ok, _result(ok, version="9.9.9")) == "fail"
    big = next(s for s in steps if s.image_index == 12)
    assert ps.classify(big, _result(big, accepted=False, confirmed=True, slot=big.expected_slot)) == "expected_reject"
    assert ps.classify(big, _result(big, accepted=True)) == "fail"
    sk = next(s for s in steps if s.skip)
    assert ps.classify(sk, None) == "skipped"


def test_coverage_gaps():
    m = _manifest()
    steps = ps.plan_sweeps(m)
    results = [_result(s) for s in steps if not s.skip]
    assert ps.coverage_gaps(m, results) == []
    dropped = next(s for s in steps if s.transport == "ble" and s.expect_accept)
    thin = [r for r in results if r["key"] != dropped.key]
    gaps = ps.coverage_gaps(m, thin)
    assert gaps and all(g[1] == "ble" for g in gaps)
    assert (m["images"][dropped.image_index]["version"], "ble", dropped.expected_slot) in gaps


def test_failed_results_do_not_count_toward_coverage():
    m = _manifest()
    steps = ps.plan_sweeps(m)
    results = [_result(s, confirmed=False) for s in steps if not s.skip and s.expect_accept]
    assert ps.coverage_gaps(m, results)


@pytest.mark.parametrize("start_slot", [0, 1])
@pytest.mark.parametrize("sweeps", [1, 2, 3])
def test_the_same_image_is_never_installed_twice_in_a_row(start_slot, sweeps):
    steps = [s for s in ps.plan_sweeps(_manifest(), sweeps=sweeps, start_slot=start_slot) if s.expect_accept]
    for a, b in itertools.pairwise(steps):
        assert a.image_index != b.image_index, (a.key, b.key)
    assert steps[0].expected_version != "1.0.0"


def test_both_slots_are_still_covered_with_an_odd_number_of_accepted_images():
    m = _manifest()
    m["images"] = [e for e in m["images"] if e["index"] != 0]            # 11 accepted over wifi, odd
    for e in m["images"]:
        e["index"] -= 1
    for start in (0, 1):
        steps = ps.plan_sweeps(m, transports=("wifi",), sweeps=2, start_slot=start)
        for e in (x for x in m["images"] if x["expected"]["wifi"]["accept"]):
            assert {s.expected_slot for s in steps if s.image_index == e["index"] and s.expect_accept} == {0, 1}
