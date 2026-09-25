"""BL-069: build the signed image pool offline (WSL only: needs the IDF toolchain and keys/idf_sbv2.pem).

    python -m labflash gen-images --out esp_idf/build_pool --seed-base <name> [--limit N] [--dry-run]

Every image is the V1 variant plus a generated overlay (CONFIG_APP_GEN_POOL). All builds share one build dir so
only the changed sources rebuild; sdkconfig is deleted before each so it regenerates from the new defaults (R15).
near_limit and too_big are sized by iterating the pad until the signed file lands within 64 KiB of the slot limit
(just under it, or just over it). too_big
is built against a temporary larger partition table, because IDF's own size check refuses an over-partition image.
"""
from __future__ import annotations

import dataclasses
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from labflash import build, imagefmt, imagegen, pinpolicy, poolmanifest

BASE_SIGNED_GUESS = 1_249_280           # signed v1 length; only the starting point for the size solver
MAX_SOLVE_ITERATIONS = 6
SIZE_WINDOW = 64 * 1024                 # flash-mapped segments are 64 KiB aligned, so exact sizes are not reachable
FIRST_GUESS_MARGIN = 64 * 1024          # start under the target: IDF's check_sizes fails an over-partition build
_OVERSIZE_RE = re.compile(r"too small for binary \S+ size 0x([0-9a-f]+)")
BIG_PARTITIONS = """\
# BL-069 too_big builds only: 5 MB app slots so IDF's size check lets the over-4 MB image build
nvs,      data, nvs,     0x9000,   0x6000,
otadata,  data, ota,     0xf000,   0x2000,
phy_init, data, phy,     0x11000,  0x1000,
ota_0,    app,  ota_0,   0x20000,  0x500000,
ota_1,    app,  ota_1,   0x520000, 0x500000,
storage,  data, spiffs,  0xa20000, 0x5e0000,
"""

# (variant, pad_bytes, big_partitions) -> signed image bytes
BuildFn = Callable[[imagegen.Variant, int, bool], bytes]


class GenError(RuntimeError):
    pass


class OversizeBuild(GenError):
    """IDF refused the image because it does not fit the partition; carries the size it measured."""

    def __init__(self, size: int) -> None:
        super().__init__(f"image of {size} bytes does not fit the partition")
        self.size = size


def solve_pad(lo: int, hi: int, measure: Callable[[int], int], first_guess: int) -> tuple[int, int]:
    """Find a pad whose signed length lands in [lo, hi]. measure(pad) builds and returns the signed length.

    Flash-mapped segments are 64 KiB aligned, so image size grows in steps and one exact byte count is not always
    reachable; each attempt aims for the middle of the window and corrects by the measured miss.
    """
    aim = (lo + hi) // 2
    pad = max(0, first_guess)
    for _ in range(MAX_SOLVE_ITERATIONS):
        got = measure(pad)
        print(f"  pad {pad} -> signed {got} (window {lo}..{hi})", flush=True)
        if lo <= got <= hi:
            return pad, got
        pad = max(0, pad + (aim - got))
    raise GenError(f"could not size an image into {lo}..{hi} in {MAX_SOLVE_ITERATIONS} builds (last pad {pad})")


def _window(variant: imagegen.Variant) -> tuple[int, int]:
    """Accepted signed length range: near_limit sits just under the slot, too_big just over it."""
    assert variant.target_len is not None
    if variant.role == "near_limit":
        return variant.target_len - SIZE_WINDOW, variant.target_len
    return variant.target_len, variant.target_len + SIZE_WINDOW


def _sized(variant: imagegen.Variant, build_fn: BuildFn) -> tuple[imagegen.Variant, bytes]:
    """Return the variant with its final pad and the signed bytes, solving the pad for target_len roles."""
    big = variant.role == "too_big"
    if variant.target_len is None:
        return variant, build_fn(variant, variant.pad_bytes, False)
    cache: dict[int, bytes] = {}

    def measure(pad: int) -> int:
        try:
            cache[pad] = build_fn(variant, pad, big)
        except OversizeBuild as e:
            return e.size
        return len(cache[pad])

    lo, hi = _window(variant)
    pad, _ = solve_pad(lo, hi, measure, variant.target_len - BASE_SIGNED_GUESS - FIRST_GUESS_MARGIN)
    return dataclasses.replace(variant, pad_bytes=pad), cache[pad]


def plan_lines(pool: list[imagegen.Variant]) -> list[str]:
    return [f"g{i:02d} {v.role:<18} {v.version} pad={v.pad_bytes} blink={v.blink_ms}ms rgb={v.led_rgb} "
            f"pins={v.pins} trailer={v.trailer_len} target={v.target_len}" for i, v in enumerate(pool)]


def generate(pool: list[imagegen.Variant], seed_base: str, out_dir: Path, build_fn: BuildFn,
             verify_key: Path | None = None, verify_runner: Callable | None = None) -> dict:
    """Build every variant, write out_dir/gNN.bin and manifest.json, return the manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, planned in enumerate(pool):
        variant, signed = _sized(planned, build_fn)
        data = imagefmt.append_trailer(signed, variant.trailer_len, variant.seed)
        if (verify_key is not None and variant.trailer_len
                and not imagefmt.verify_device_signature(data, len(signed), verify_key, runner=verify_runner)):
            raise GenError(f"g{i:02d}: signature does not verify once the trailer is stripped")
        name = f"g{i:02d}.bin"
        (out_dir / name).write_bytes(data)
        entries.append(poolmanifest.make_entry(i, variant, name, data, len(signed)))
    manifest = poolmanifest.make_manifest(seed_base, entries)
    poolmanifest.write_manifest(out_dir / "manifest.json", manifest)
    return manifest


def idf_build_fn(repo_root: Path, work_dir: Path, runner: Callable | None = None) -> BuildFn:
    """A BuildFn that drives build.build_idf_image in one shared build dir under work_dir."""
    build_dir = work_dir / "build"
    inputs = work_dir / "inputs"

    def build_one(variant: imagegen.Variant, pad_bytes: int, big: bool) -> bytes:
        v = dataclasses.replace(variant, pad_bytes=pad_bytes)
        inputs.mkdir(parents=True, exist_ok=True)
        (inputs / "pad.bin").write_bytes(imagegen.pad_blob(v.seed, pad_bytes))
        text = imagegen.defaults_text(v)
        if big:
            (inputs / "big_partitions.csv").write_text(BIG_PARTITIONS)
            text += f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="{inputs / "big_partitions.csv"}"\n'
        defaults = inputs / "pool.defaults"
        defaults.write_text(text)
        (build_dir / "sdkconfig").unlink(missing_ok=True)            # R15: regenerate from these defaults
        try:
            result = build.build_idf_image(
                build_dir=build_dir, project_ver=v.version,
                defaults=f"sdkconfig.defaults;{defaults}", kconfig_sym="CONFIG_APP_GEN_POOL=y",
                repo_root=repo_root, runner=runner,
                extra_cmake_defs=(f"-DGEN_PAD_FILE={inputs / 'pad.bin'}",), label=v.version,
            )
        except build.BuildError as e:
            found = _OVERSIZE_RE.search(str(e))
            if found:
                raise OversizeBuild(int(found.group(1), 16)) from e
            raise
        sdkconfig = (build_dir / "sdkconfig").read_text()
        if "CONFIG_APP_VARIANT_V1=y" not in sdkconfig:
            raise GenError(f"{v.version}: generated image is not the V1 variant")
        built_pins = [int(x) for x in re.findall(r"^CONFIG_APP_GEN_PIN_[AB]=(\d+)$", sdkconfig, re.MULTILINE)]
        if len(built_pins) != 2:
            raise GenError(f"{v.version}: sdkconfig does not carry exactly two generated pins")
        pinpolicy.check_pins(built_pins)        # the pins the image was really built with, not just those planned
        return result.binary_path.read_bytes()

    return build_one


def run(out_dir: Path, seed_base: str, limit: int | None = None, dry_run: bool = False,
        repo_root: Path | None = None, runner: Callable | None = None, only: list[int] | None = None) -> int:
    root = (repo_root or build.DEFAULT_REPO_ROOT).resolve()
    out_dir = out_dir.resolve()      # idf.py runs from esp_idf/, so a relative path would land in the wrong place
    full = imagegen.gen_pool(seed_base)
    pool = full[:limit] if limit is not None else full
    for line in plan_lines(pool):
        print(line)
    if dry_run:
        return 0
    if only is not None or len(pool) < len(full):
        indices = only if only is not None else list(range(len(pool)))
        print(f"partial pool (indices {indices}): manifest is not written")
        build_one = idf_build_fn(root, out_dir / "work", runner)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i in indices:
            variant, signed = _sized(full[i], build_one)
            (out_dir / f"g{i:02d}.bin").write_bytes(imagefmt.append_trailer(signed, variant.trailer_len, variant.seed))
            print(f"g{i:02d} built: {len(signed)} signed bytes, pad {variant.pad_bytes}")
        return 0
    work = out_dir / "work"
    manifest = generate(pool, seed_base, out_dir, idf_build_fn(root, work, runner),
                        verify_key=root / "keys" / "idf_sbv2.pem", verify_runner=runner)
    shutil.rmtree(work / "inputs", ignore_errors=True)
    print(f"wrote {len(manifest['images'])} images + manifest.json to {out_dir}")
    return 0
