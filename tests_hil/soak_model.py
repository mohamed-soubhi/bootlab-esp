"""BL-067: the pure model behind the randomized soak — a seeded picker and the outcome it expects of the device.

No I/O and no board: every pick is a function of the run seed, so a schedule can be replayed, audited and compared
against what a real device reported.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

MODEL_VERSION = 2                       # bump when picking or expectations change: it is part of every plan id

START_APP = "1.0.0"                     # the runner's warm-up leaves the board on v1
_TRANSPORTS: tuple[str, ...] = ("wifi", "ble")
_FIXED_KIND = "fixed"
_GENERATED_KIND = "generated"
_FAILURE_KIND = "failure"
_BAD_SIG = "bad_sig"
_OVERSIZED_ROLE = "too_big"

_TRANSPORT_TAG = "transport"
_CATEGORY_TAG = "category"
_IMAGE_TAG = "image"

_FIXED_CUTOFF = 0.70
_GENERATED_CUTOFF = 0.80

_FIXED_IMAGES: tuple[tuple[str, str], ...] = (
    ("v1", "1.0.0"),
    ("v2", "2.0.0"),
    ("v3", "3.0.0"),
    ("v4", "4.0.0"),
)
_FAILURE_IMAGES: tuple[tuple[str, str], ...] = (
    ("bad_sig", "1.0.0-badsig"),
    ("hang", "1.0.0-hang"),
    ("no_confirm", "1.0.0-noconfirm"),
)

_INSTALLS = "installs"
_REJECTED = "rejected"
_ROLLS_BACK = "rolls_back"


@dataclass(frozen=True)
class Image:
    """One image the soak can send, and what each transport should do with it."""

    name: str
    kind: str
    version: str
    file: str | None
    accepts: dict[str, bool]
    failure: str | None


@dataclass(frozen=True)
class Catalog:
    """Everything a run can pick from: the synthetic fixed and failure images plus the manifest's own."""

    fixed: tuple[Image, ...]
    failures: tuple[Image, ...]
    generated: tuple[Image, ...]


@dataclass(frozen=True)
class Pick:
    """One planned cycle: the image to send and the transport to send it over."""

    image: Image
    transport: str


@dataclass(frozen=True)
class State:
    """Where the model believes the device is: the confirmed app, its slot, and whether that is trustworthy."""

    app: str
    slot: int
    confirmed: bool


@dataclass(frozen=True)
class Expectation:
    """What one cycle should leave behind, plus what a rollback should be pending on."""

    outcome: str
    app: str
    slot: int
    confirmed: bool
    pending_app: str | None
    pending_slot: int | None
    check_pending: bool = False


def unit_float(seed: int, index: int, tag: str) -> float:
    """One draw from the run's keystream: the same (seed, index, tag) always gives the same value in [0, 1)."""
    digest = hashlib.shake_256(f"{seed}:{index}:{tag}".encode()).digest(8)
    return int.from_bytes(digest, "big") / 2**64


def _accepts_both() -> dict[str, bool]:
    return {transport: True for transport in _TRANSPORTS}


def _generated_image(entry: dict) -> Image:
    return Image(
        name=entry["version"],
        kind=_GENERATED_KIND,
        version=entry["version"],
        file=entry["file"],
        accepts={transport: bool(entry["expected"][transport]["accept"]) for transport in _TRANSPORTS},
        failure=None,
    )


def build_catalog(manifest: dict | None) -> Catalog:
    """The catalog of a run; without a manifest there are no generated images to pick."""
    fixed = tuple(
        Image(name, _FIXED_KIND, version, name, _accepts_both(), None) for name, version in _FIXED_IMAGES
    )
    failures = tuple(
        Image(name, _FAILURE_KIND, version, name, _accepts_both(), name) for name, version in _FAILURE_IMAGES
    )
    entries = [] if manifest is None else manifest["images"]
    generated = tuple(_generated_image(e) for e in entries if e["role"] != _OVERSIZED_ROLE)
    return Catalog(fixed=fixed, failures=failures, generated=generated)


def _category(seed: int, index: int) -> str:
    draw = unit_float(seed, index, _CATEGORY_TAG)
    if draw < _FIXED_CUTOFF:
        return _FIXED_KIND
    if draw < _GENERATED_CUTOFF:
        return _GENERATED_KIND
    return _FAILURE_KIND


def _pool(category: str, catalog: Catalog, transport: str, running: str) -> tuple[Image, ...]:
    """The images a category may draw from. A valid image never repeats the version already running: `labflash update`
    recognises a finished install by the version changing, so re-sending it reports a false failure."""
    if category == _FAILURE_KIND:
        return catalog.failures
    if category == _FIXED_KIND:
        return tuple(image for image in catalog.fixed if image.version != running)
    accepted = tuple(image for image in catalog.generated if image.accepts[transport] and image.version != running)
    return accepted or tuple(image for image in catalog.fixed if image.version != running)


def _pick(seed: int, index: int, catalog: Catalog, ble_share: float, failure_cap: int, streak: int,
          running: str) -> Pick:
    transport = "ble" if unit_float(seed, index, _TRANSPORT_TAG) < ble_share else "wifi"
    category = _category(seed, index)
    if category == _FAILURE_KIND and streak >= failure_cap:
        category = _FIXED_KIND
    pool = _pool(category, catalog, transport, running)
    return Pick(image=pool[int(unit_float(seed, index, _IMAGE_TAG) * len(pool))], transport=transport)


def plan(seed: int, cycles: int, catalog: Catalog, ble_share: float = 0.5, failure_cap: int = 2,
         start_app: str = START_APP) -> list[Pick]:
    """The schedule of `cycles` cycles: which image goes over which transport, within the failure cap.

    Every draw depends only on (seed, cycle, tag) and on the failures immediately before the cycle, so a longer
    plan always begins with the shorter one.
    """
    picks: list[Pick] = []
    streak, running = 0, start_app
    for index in range(cycles):
        pick = _pick(seed, index, catalog, ble_share, failure_cap, streak, running)
        streak = streak + 1 if pick.image.kind == _FAILURE_KIND else 0
        if pick.image.kind != _FAILURE_KIND:
            running = pick.image.version          # a failure image rolls back, so the running version is unchanged
        picks.append(pick)
    return picks


def _failure_expectation(state: State, image: Image) -> Expectation:
    if image.failure == _BAD_SIG:
        return Expectation(_REJECTED, state.app, state.slot, True, None, None)
    return Expectation(_ROLLS_BACK, state.app, state.slot, True, image.version, state.slot ^ 1,
                       check_pending=image.failure == "no_confirm")


def expected_after(state: State, image: Image, transport: str) -> Expectation:
    """What the device must look like after one cycle, or ValueError when it cannot be asked for."""
    if not state.confirmed:
        raise ValueError("the model must sit on a confirmed image")
    if image.kind == _FAILURE_KIND:
        return _failure_expectation(state, image)
    if not image.accepts[transport]:
        raise ValueError(f"image {image.name} is not accepted over {transport}")
    return Expectation(_INSTALLS, image.version, state.slot ^ 1, True, None, None)


def next_state(expectation: Expectation) -> State:
    """The state the model carries into the next cycle."""
    return State(expectation.app, expectation.slot, expectation.confirmed)


def plan_summary(picks: list[Pick]) -> dict:
    """The counts a report quotes: cycles, per kind, per transport and per image name."""
    by_kind: dict[str, int] = {}
    by_transport: dict[str, int] = {}
    by_image: dict[str, int] = {}
    for pick in picks:
        by_kind[pick.image.kind] = by_kind.get(pick.image.kind, 0) + 1
        by_transport[pick.transport] = by_transport.get(pick.transport, 0) + 1
        by_image[pick.image.name] = by_image.get(pick.image.name, 0) + 1
    return {"cycles": len(picks), "by_kind": by_kind, "by_transport": by_transport, "by_image": by_image}
