"""BL-069: pool builder logic with a fake build function (no toolchain). Owner: Claude."""
import pytest
from labflash import genvariants as gv
from labflash import imagefmt as fmt
from labflash import imagegen as gen

BASE_DATA = 1_245_184 - 100      # bytes of image data at pad 0


def _fake_build(jitter=0):
    calls = []

    def build(variant, pad, big):
        calls.append((variant.version, pad, big))
        end = BASE_DATA + pad + jitter
        return b"\xE9" * fmt.signed_len_from_data_end(end)
    return build, calls


@pytest.mark.parametrize("lo,hi", [(fmt.SLOT_SIZE - gv.SIZE_WINDOW, fmt.SLOT_SIZE),
                                    (fmt.SLOT_SIZE + fmt.SECTOR, fmt.SLOT_SIZE + fmt.SECTOR + gv.SIZE_WINDOW)])
def test_solve_pad_lands_inside_the_window(lo, hi):
    build, _ = _fake_build()
    _pad, got = gv.solve_pad(lo, hi, lambda p: len(build(gen.gen_variant(1), p, False)), lo - gv.BASE_SIGNED_GUESS)
    assert lo <= got <= hi


def test_solve_pad_copes_with_64k_steps():
    step = 65536
    measure = lambda pad: (pad // step) * step + 1_300_000 // 4096 * 4096 + 4096
    _pad, got = gv.solve_pad(fmt.SLOT_SIZE - gv.SIZE_WINDOW, fmt.SLOT_SIZE, measure, 2_000_000)
    assert fmt.SLOT_SIZE - gv.SIZE_WINDOW <= got <= fmt.SLOT_SIZE


def test_solve_pad_gives_up_after_a_bounded_number_of_builds():
    n = []
    with pytest.raises(gv.GenError):
        gv.solve_pad(fmt.SLOT_SIZE - 10, fmt.SLOT_SIZE, lambda p: n.append(p) or 1, 10)
    assert len(n) == gv.MAX_SOLVE_ITERATIONS


def test_generate_writes_images_and_a_valid_manifest(tmp_path):
    build, calls = _fake_build()
    pool = gen.gen_pool("unit")
    manifest = gv.generate(pool, "unit", tmp_path, build)
    assert (tmp_path / "manifest.json").is_file()
    assert len(manifest["images"]) == 13
    for e in manifest["images"]:
        data = (tmp_path / e["file"]).read_bytes()
        assert len(data) == e["size"] and e["signed_len"] % fmt.SECTOR == 0
    by_role = {e["role"]: e for e in manifest["images"]}
    assert fmt.SLOT_SIZE - gv.SIZE_WINDOW <= by_role["near_limit"]["size"] <= fmt.SLOT_SIZE
    assert fmt.SLOT_SIZE < by_role["too_big"]["size"] <= fmt.SLOT_SIZE + fmt.SECTOR + gv.SIZE_WINDOW
    un = [e for e in manifest["images"] if e["role"] == "unaligned_trailer"]
    assert all(e["size"] % fmt.SECTOR for e in un)
    assert {c[2] for c in calls if c[0] == by_role["too_big"]["version"]} == {True}
    assert not any(c[2] for c in calls if c[0] != by_role["too_big"]["version"])


def test_generate_is_deterministic(tmp_path):
    a = gv.generate(gen.gen_pool("d"), "d", tmp_path / "a", _fake_build()[0])
    b = gv.generate(gen.gen_pool("d"), "d", tmp_path / "b", _fake_build()[0])
    assert a == b
    assert (tmp_path / "a" / "manifest.json").read_bytes() == (tmp_path / "b" / "manifest.json").read_bytes()


def test_dry_run_builds_nothing(tmp_path, capsys):
    assert gv.run(tmp_path / "o", "x", dry_run=True) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 13 and "too_big" in out
    assert not (tmp_path / "o").exists()


def test_big_partition_text_keeps_the_layout_inside_16mb():
    assert "0x500000" in gv.BIG_PARTITIONS and "0xa20000, 0x5e0000" in gv.BIG_PARTITIONS
    assert 0xA20000 + 0x5E0000 == 16 * 1024 * 1024


def test_overshoot_reported_by_the_build_is_used_as_a_measurement():
    def build(variant, pad, big):
        end = BASE_DATA + pad
        length = fmt.signed_len_from_data_end(end)
        if length > fmt.SLOT_SIZE and not big:
            raise gv.OversizeBuild(length)
        return b"\xE9" * length
    v = gen.gen_variant(3, role="near_limit")
    fixed, signed = gv._sized(v, build)
    assert fmt.SLOT_SIZE - gv.SIZE_WINDOW <= len(signed) <= fmt.SLOT_SIZE and fixed.pad_bytes > 0


def test_oversize_message_is_parsed_from_idf_output():
    msg = "Error: All app partitions are too small for binary bootlab_idf_blink.bin size 0x401000:"
    assert int(gv._OVERSIZE_RE.search(msg).group(1), 16) == 0x401000


def test_first_guess_starts_under_the_target():
    seen = []
    def build(variant, pad, big):
        seen.append(pad)
        return b"\xE9" * fmt.signed_len_from_data_end(BASE_DATA + pad)
    gv._sized(gen.gen_variant(3, role="near_limit"), build)
    assert seen[0] == fmt.SLOT_SIZE - gv.BASE_SIGNED_GUESS - gv.FIRST_GUESS_MARGIN
