"""BL-069: pool manifest (AC3). Owner: cheap agent implements, Claude wrote the spec."""
import copy
import json

import pytest
from labflash import imagefmt as fmt
from labflash import imagegen as gen
from labflash import poolmanifest as pm

BASE_SIGNED = 1_249_280


def _signed_len(i, v):
    if v.role == "near_limit":
        return fmt.SLOT_SIZE
    if v.role == "too_big":
        return fmt.SLOT_SIZE + fmt.SECTOR
    return BASE_SIGNED + fmt.align_up(v.pad_bytes)          # sector-multiple by construction


def _fake_manifest(seed_base="t"):
    entries = []
    for i, v in enumerate(gen.gen_pool(seed_base)):
        sl = _signed_len(i, v)
        data = bytes([i]) * 16 + b"\0" * (sl + v.trailer_len - 16)
        entries.append(pm.make_entry(i, v, f"g{i:02d}.bin", data, sl))
    return pm.make_manifest(seed_base, entries)


def test_expected_outcomes_per_role():
    ok = pm.expected_outcomes("valid", 0)
    assert ok["wifi"]["accept"] and ok["ble"]["accept"]
    un = pm.expected_outcomes("unaligned_trailer", 100)
    assert un["wifi"]["accept"] and not un["ble"]["accept"] and "4096" in un["ble"]["reason"]
    nl = pm.expected_outcomes("near_limit", 0)
    assert nl["wifi"]["accept"] and nl["ble"]["accept"]
    tb = pm.expected_outcomes("too_big", 0)
    assert not tb["wifi"]["accept"] and not tb["ble"]["accept"]
    for role, tl in (("valid", 0), ("unaligned_trailer", 5), ("near_limit", 0), ("too_big", 0)):
        for t in ("wifi", "ble"):
            assert pm.expected_outcomes(role, tl)[t]["reason"].strip()


def test_make_entry_fields():
    v = gen.gen_pool("t")[0]
    data = b"\xE9" * (BASE_SIGNED)
    e = pm.make_entry(0, v, "g00.bin", data, BASE_SIGNED)
    assert e["index"] == 0 and e["seed"] == v.seed and e["role"] == "valid" and e["version"] == v.version
    assert e["file"] == "g00.bin" and e["size"] == BASE_SIGNED and e["signed_len"] == BASE_SIGNED
    assert e["trailer_len"] == 0 and len(e["sha256"]) == 64
    assert e["params"] == {"pad_bytes": v.pad_bytes, "blink_ms": v.blink_ms,
                           "led_rgb": list(v.led_rgb), "pins": list(v.pins)}
    assert set(e["expected"]) == {"wifi", "ble"}


def test_make_entry_trailer_length_must_match_variant():
    v = next(x for x in gen.gen_pool("t") if x.role == "unaligned_trailer")
    with pytest.raises(pm.ManifestError):
        pm.make_entry(0, v, "x.bin", b"\0" * 8192, 8192)         # no trailer present


def test_full_manifest_validates():
    m = _fake_manifest()
    assert m["schema"] == 1 and m["seed_base"] == "t" and m["slot_size"] == fmt.SLOT_SIZE
    pm.validate_manifest(m)


@pytest.mark.parametrize("mutate,match", [
    (lambda m: m.update(schema=2), "schema"),
    (lambda m: m["images"][1].update(version=m["images"][0]["version"]), "version"),
    (lambda m: m["images"][1].update(file=m["images"][0]["file"]), "file"),
    (lambda m: m["images"][0].update(sha256="xyz"), "sha256"),
    (lambda m: m["images"][0].update(size="big"), "size"),
    (lambda m: m["images"][3].update(index=9), "index"),
    (lambda m: m["images"][0].update(size=m["images"][0]["size"] + 1), "aligned"),
    (lambda m: m["images"][-1]["expected"]["wifi"].update(accept=True), "too_big"),
    (lambda m: next(i for i in m["images"] if i["role"] == "unaligned_trailer")["expected"]["ble"].update(accept=True), "ble"),
    (lambda m: m["images"][0].update(size=fmt.SLOT_SIZE + 4096, signed_len=fmt.SLOT_SIZE + 4096), "slot"),
])
def test_validate_rejects(mutate, match):
    m = copy.deepcopy(_fake_manifest())
    mutate(m)
    with pytest.raises(pm.ManifestError, match=match):
        pm.validate_manifest(m)


def test_validate_requires_twelve_valid_images_and_size_spread():
    m = _fake_manifest()
    short = copy.deepcopy(m)
    short["images"] = short["images"][:6] + short["images"][-1:]
    for n, e in enumerate(short["images"]):
        e["index"] = n
    with pytest.raises(pm.ManifestError, match="12"):
        pm.validate_manifest(short)
    flat = copy.deepcopy(m)
    for e in flat["images"]:
        if e["role"] == "valid":
            e["size"] = e["signed_len"] = BASE_SIGNED
    with pytest.raises(pm.ManifestError, match="spread"):
        pm.validate_manifest(flat)


def test_write_is_deterministic_and_timestamp_free(tmp_path):
    m = _fake_manifest()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    pm.write_manifest(a, m)
    pm.write_manifest(b, _fake_manifest())
    assert a.read_bytes() == b.read_bytes() and a.read_bytes().endswith(b"\n")

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for x in o:
                yield from keys(x)
    assert not any(("time" in k or "date" in k) for k in keys(json.loads(a.read_text())))


def test_load_round_trips_and_validates(tmp_path):
    m = _fake_manifest()
    p = tmp_path / "manifest.json"
    pm.write_manifest(p, m)
    assert pm.load_manifest(p) == m
    assert [e["index"] for e in pm.load_manifest(p)["images"]] == list(range(13))
    bad = json.loads(p.read_text())
    bad["schema"] = 9
    p.write_text(json.dumps(bad))
    with pytest.raises(pm.ManifestError):
        pm.load_manifest(p)


def test_write_refuses_an_invalid_manifest(tmp_path):
    m = _fake_manifest()
    m["schema"] = 0
    with pytest.raises(pm.ManifestError):
        pm.write_manifest(tmp_path / "x.json", m)
    assert not (tmp_path / "x.json").exists()


def test_content_sha256_ignores_the_signature_sector_and_the_trailer():
    import hashlib
    v = next(x for x in gen.gen_pool("t") if x.role == "unaligned_trailer")
    body = b"\xE9" * (BASE_SIGNED - fmt.SECTOR)
    a = pm.make_entry(0, v, "a.bin", body + b"\x01" * fmt.SECTOR + b"T" * v.trailer_len, BASE_SIGNED)
    b = pm.make_entry(0, v, "a.bin", body + b"\x02" * fmt.SECTOR + b"U" * v.trailer_len, BASE_SIGNED)
    assert a["content_sha256"] == b["content_sha256"] == hashlib.sha256(body).hexdigest()
    assert a["sha256"] != b["sha256"]


def test_validate_rejects_a_bad_content_sha256():
    m = copy.deepcopy(_fake_manifest())
    m["images"][2]["content_sha256"] = "nope"
    with pytest.raises(pm.ManifestError, match="content_sha256"):
        pm.validate_manifest(m)


def test_validate_rejects_a_too_big_image_that_would_fit():
    m = copy.deepcopy(_fake_manifest())
    big = m["images"][-1]
    big["size"] = big["signed_len"] = fmt.SLOT_SIZE                       # the bootloader would accept this one
    with pytest.raises(pm.ManifestError, match="would fit"):
        pm.validate_manifest(m)
