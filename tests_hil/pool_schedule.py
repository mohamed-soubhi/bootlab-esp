"""BL-069 AC5: the install schedule a pool run follows — transport blocks, sweeps and predicted slots.

Pure data: every step names the image, the sweep and the slot the device should land on, so a run can be resumed,
compared against its results and audited without a board.
"""
from __future__ import annotations

from dataclasses import dataclass

_TRANSPORTS: tuple[str, ...] = ("wifi", "ble")
_OVERSIZED_ROLE = "too_big"
_SLOTS = (0, 1)


@dataclass(frozen=True)
class Step:
    """One planned install: what to send, when, and the slot the device should end up on."""

    sweep: int
    transport: str
    image_index: int
    file: str
    expect_accept: bool
    skip: bool
    skip_reason: str
    expected_version: str | None
    expected_slot: int | None

    @property
    def key(self) -> str:
        """Stable identity of the step, so a resume can name the ones already done."""
        return f"{self.transport}:{self.sweep}:{self.image_index}"


def _accepts(entry: dict, transport: str) -> bool:
    return bool(entry["expected"][transport]["accept"])


def _skippable(entry: dict, transport: str) -> bool:
    return not _accepts(entry, transport) and entry["role"] != _OVERSIZED_ROLE


def _step(
    transport: str,
    sweep: int,
    entry: dict,
    *,
    expect_accept: bool = False,
    skip: bool = False,
    skip_reason: str = "",
    expected_version: str | None = None,
    expected_slot: int | None = None,
) -> Step:
    return Step(
        sweep=sweep,
        transport=transport,
        image_index=entry["index"],
        file=entry["file"],
        expect_accept=expect_accept,
        skip=skip,
        skip_reason=skip_reason,
        expected_version=expected_version,
        expected_slot=expected_slot,
    )


def plan_sweeps(
    manifest: dict,
    transports: tuple[str, ...] = _TRANSPORTS,
    sweeps: int = 2,
    start_slot: int = 0,
) -> list[Step]:
    """The full schedule: every step of transport 1, then transport 2, sweeps within each transport.

    Sweep 1 follows manifest order; every later sweep reverses the previous sweep's accepted images, so each
    accepted image lands on the opposite slot in the next sweep. The predicted slot is carried across all steps,
    flipped by an accepted install and left alone by a reject or a skip.
    """
    images = manifest["images"]
    steps: list[Step] = []
    slot = start_slot
    for transport in transports:
        accepted = [e for e in images if _accepts(e, transport)]
        skipped = [e for e in images if _skippable(e, transport)]
        oversized = [e for e in images if e["role"] == _OVERSIZED_ROLE]
        accepted_ids = {e["index"] for e in accepted}
        planned_ids = accepted_ids | {e["index"] for e in skipped}
        for sweep in range(1, sweeps + 1):
            if sweep == 1:
                ordered = [e for e in images if e["index"] in planned_ids]
            else:
                ordered = (accepted if sweep % 2 else list(reversed(accepted))) + skipped
            for entry in ordered:
                if entry["index"] in accepted_ids:
                    slot ^= 1
                    steps.append(
                        _step(
                            transport,
                            sweep,
                            entry,
                            expect_accept=True,
                            expected_version=entry["version"],
                            expected_slot=slot,
                        )
                    )
                else:
                    steps.append(
                        _step(
                            transport,
                            sweep,
                            entry,
                            skip=True,
                            skip_reason=entry["expected"][transport]["reason"],
                        )
                    )
            if sweep == 1:
                for entry in oversized:
                    steps.append(_step(transport, sweep, entry, expected_slot=slot))
    return steps


def remaining(steps: list[Step], done_keys: set[str]) -> list[Step]:
    """The steps a resumed run still has to do, in schedule order."""
    return [s for s in steps if s.key not in done_keys]


def classify(step: Step, result: dict | None) -> str:
    """The verdict for a step: pass, fail, expected_reject or skipped."""
    if step.skip:
        return "skipped"
    if result is None:
        return "fail"
    if not step.expect_accept:
        return "expected_reject" if not result.get("accepted") else "fail"
    landed = (
        result.get("accepted")
        and result.get("confirmed")
        and result.get("version") == step.expected_version
        and result.get("slot") == step.expected_slot
    )
    return "pass" if landed else "fail"


def _entry_at(images: list[dict], index: int) -> dict | None:
    for entry in images:
        if entry["index"] == index:
            return entry
    return None


def coverage_gaps(manifest: dict, results: list[dict]) -> list[tuple[str, str, int]]:
    """The (version, transport, slot) triples an accepted image never landed on for a confirmed run.

    A result counts toward coverage only when it classifies as a pass: accepted, confirmed, and reporting the
    version the manifest expects for that image. Both slots must be seen for every accepted image.
    """
    images = manifest["images"]
    covered: set[tuple[str, str, int]] = set()
    for result in results:
        entry = _entry_at(images, result["image_index"])
        if entry is None or not _accepts(entry, result["transport"]):
            continue
        if not (result.get("accepted") and result.get("confirmed")):
            continue
        if result.get("version") != entry["version"] or result.get("slot") not in _SLOTS:
            continue
        covered.add((entry["version"], result["transport"], result["slot"]))
    gaps = [
        (entry["version"], transport, slot)
        for entry in images
        for transport in entry["expected"]
        if _accepts(entry, transport)
        for slot in _SLOTS
        if (entry["version"], transport, slot) not in covered
    ]
    return sorted(gaps)
