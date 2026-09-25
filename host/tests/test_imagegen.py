"""BL-069: deterministic variant generator (AC1, AC6). Owner: cheap agent implements, Claude wrote the spec."""
import dataclasses
import hashlib
import re
from pathlib import Path

import pytest
from labflash import imagefmt as fmt
from labflash import imagegen as gen
from labflash import pinpolicy as pp

FORBIDDEN_TOKENS = {"labid", "wifi", "ble", "nimble", "ota", "confirm", "https", "token"}
ALLOWED_KEYS = {
    "CONFIG_APP_GEN_POOL", "CONFIG_APP_GEN_PAD_BYTES", "CONFIG_APP_GEN_BLINK_MS", "CONFIG_APP_GEN_BLINK_HZ",
    "CONFIG_APP_GEN_LED_R", "CONFIG_APP_GEN_LED_G", "CONFIG_APP_GEN_LED_B",
    "CONFIG_APP_GEN_PIN_A", "CONFIG_APP_GEN_PIN_B", "CONFIG_APP_REPRODUCIBLE_BUILD",
}


def test_pad_blob_is_the_pinned_shake256_stream():
    assert gen.pad_blob(5, 64) == hashlib.shake_256(b"pad:5").digest(64)
    assert gen.pad_blob(5, 0) == b""
    assert gen.pad_blob(5, 100)[:64] == gen.pad_blob(5, 64)     # prefix-stable
    assert gen.pad_blob(5, 64) != gen.pad_blob(6, 64)


def test_seed_for_is_pinned_and_distinct():
    want = int.from_bytes(hashlib.sha256(b"base:3").digest()[:8], "big")
    assert gen.seed_for("base", 3) == want
    assert len({gen.seed_for("base", i) for i in range(50)}) == 50


def test_gen_variant_is_deterministic_and_frozen():
    a, b = gen.gen_variant(42), gen.gen_variant(42)
    assert a == b
    assert gen.gen_variant(43) != a
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.seed = 1                                              # type: ignore[misc]


def test_gen_variant_parameters_are_in_bounds():
    for seed in range(200):
        v = gen.gen_variant(seed)
        assert v.seed == seed and v.role == "valid"
        assert 0 <= v.pad_bytes <= gen.MAX_VALID_PAD
        assert 100 <= v.blink_ms <= 1000
        assert len(v.led_rgb) == 3 and all(0 <= c <= 255 for c in v.led_rgb) and v.led_rgb != (0, 0, 0)
        assert len(v.pins) == 2 and len(set(v.pins)) == 2
        assert set(v.pins) <= pp.SAFE_OUTPUT_PINS
        assert re.fullmatch(r"gen-[0-9a-f]{8}", v.version)
        assert v.trailer_len == 0 and v.target_len is None


def test_versions_fit_the_32_byte_app_descriptor_field():
    assert all(len(gen.gen_variant(s).version) <= 31 for s in range(100))


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        gen.gen_variant(1, role="bogus")


def test_role_specific_fields():
    t = gen.gen_variant(9, role="unaligned_trailer")
    assert 1 <= t.trailer_len <= 4095 and t.target_len is None
    n = gen.gen_variant(9, role="near_limit")
    assert n.target_len == fmt.SLOT_SIZE and n.trailer_len == 0
    b = gen.gen_variant(9, role="too_big")
    assert b.target_len == fmt.SLOT_SIZE + fmt.SECTOR and b.trailer_len == 0


def test_defaults_text_is_whitelisted_and_never_touches_protected_paths():
    v = gen.gen_variant(11)
    text = gen.defaults_text(v)
    assert text.endswith("\n")
    keys = set()
    for line in filter(None, text.splitlines()):
        assert not line.startswith("#") or True
        key, _, _val = line.partition("=")
        keys.add(key)
    assert keys <= ALLOWED_KEYS and "CONFIG_APP_GEN_POOL" in keys and "CONFIG_APP_REPRODUCIBLE_BUILD" in keys
    tokens = {t.lower() for t in re.split(r"[^A-Za-z0-9]+", text) if t}
    assert not (tokens & FORBIDDEN_TOKENS)


def test_defaults_text_carries_the_variant_values():
    v = gen.gen_variant(11)
    text = gen.defaults_text(v)
    assert f"CONFIG_APP_GEN_BLINK_MS={v.blink_ms}\n" in text
    assert f"CONFIG_APP_GEN_PIN_A={v.pins[0]}\n" in text and f"CONFIG_APP_GEN_PIN_B={v.pins[1]}\n" in text
    assert f"CONFIG_APP_GEN_LED_R={v.led_rgb[0]}\n" in text
    assert "CONFIG_APP_GEN_POOL=y\n" in text and "CONFIG_APP_REPRODUCIBLE_BUILD=y\n" in text
    assert text == gen.defaults_text(v)


def test_gen_pool_composition():
    pool = gen.gen_pool("bl069-test")
    assert len(pool) == 13
    roles = [v.role for v in pool]
    assert roles[-1] == "too_big" and roles.count("too_big") == 1
    assert roles.count("near_limit") == 1 and roles.count("unaligned_trailer") == 2
    assert roles.count("valid") == 9
    assert len({v.version for v in pool}) == 13
    assert len({v.seed for v in pool}) == 13
    trailers = [v.trailer_len for v in pool if v.role == "unaligned_trailer"]
    assert len(set(trailers)) == 2


def test_gen_pool_is_deterministic_and_seed_base_sensitive():
    assert gen.gen_pool("a") == gen.gen_pool("a")
    assert gen.gen_pool("a") != gen.gen_pool("b")
    assert gen.gen_pool("a")[4].seed == gen.seed_for("a", 4)


def test_gen_pool_valid_pads_spread():
    pads = [v.pad_bytes for v in gen.gen_pool("spread") if v.role == "valid"]
    assert len(set(pads)) == len(pads)
    assert max(pads) - min(pads) >= 1_000_000


def test_gen_pool_larger_n_adds_valid_images_before_too_big():
    pool = gen.gen_pool("x", 16)
    assert len(pool) == 16 and pool[-1].role == "too_big"
    assert [v.role for v in pool].count("valid") == 12
    with pytest.raises(ValueError):
        gen.gen_pool("x", 12)


def test_led_peak_never_falls_below_the_firmware_floor():
    assert all(max(gen.gen_variant(x).led_rgb) >= gen.LED_FLOOR for x in range(5000))


def test_reported_blink_rate_matches_the_half_period():
    assert gen.blink_hz(500) == "1.000" and gen.blink_hz(100) == "5.000" and gen.blink_hz(1000) == "0.500"
    v = gen.gen_variant(11)
    assert f'CONFIG_APP_GEN_BLINK_HZ="{gen.blink_hz(v.blink_ms)}"\n' in gen.defaults_text(v)


@pytest.mark.parametrize("pins", [(19, 20), (0, 4), (48, 5), (4, 43)])
def test_defaults_text_refuses_a_variant_with_an_unsafe_pin(pins):
    with pytest.raises(pp.PinNotAllowedError):
        gen.defaults_text(dataclasses.replace(gen.gen_variant(11), pins=pins))


def test_firmware_static_assert_matches_the_python_allowlist():
    """esp_idf/main/app_main.c carries a compile-time copy of SAFE_OUTPUT_PINS; the two must agree for every GPIO."""
    src = (Path(__file__).resolve().parents[2] / "esp_idf" / "main" / "app_main.c").read_text()
    body = re.search(r"#define GEN_PIN_OK\(p\)\s*(.+)", src).group(1)
    expr = body.replace("||", " or ").replace("&&", " and ")
    for pin in range(-1, 60):
        assert eval(expr, {"p": pin}) == (pin in pp.SAFE_OUTPUT_PINS), pin
