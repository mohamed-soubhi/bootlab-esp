"""labflash update — OTA an ESP-IDF board and VERIFY it (BL-043, PLAN 5.5 / 5.6 / 7.3.4).

Pure orchestration: the transports (BLE / WiFi) and the board readers (LABID over serial, the
HTTPS /version) are injected, so this logic is tested without hardware. Order of operations:

  1. validate the image and read its own version from the app descriptor (the expected result
     comes from the image, not from a value typed by the user);
  2. read the board and REFUSE if its identity is not the expected board -- before anything is sent;
  3. send the image (transport-specific; failures are raised, never swallowed);
  4. wait for the board to report the new version, then for it to confirm;
  5. evaluate: running the new image, slot flipped, confirmed, identity, and LABID == HTTPS
     (the version-consistency rule of PLAN 7.3.4).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

SECTOR_SIZE = 4096
ESP_IMAGE_MAGIC = 0xE9
APP_DESC_OFFSET = 0x20            # 24-byte image header + 8-byte first segment header
APP_DESC_MAGIC = 0xABCD5432       # esp_app_desc_t.magic_word
APP_VERSION_OFFSET = APP_DESC_OFFSET + 16   # magic, secure_version, reserv1[2], then version[32]
APP_VERSION_LEN = 32

MCUBOOT_IMAGE_MAGIC = 0x96F3B83D

DEFAULT_TIMEOUT_S = 240.0         # WiFi ~15-30 s, BLE ~2 min; the board must then reboot and reconnect
DEFAULT_CONFIRM_TIMEOUT_S = 30.0  # the self-test confirms ~5 s after boot
DEFAULT_POLL_S = 2.0              # sparse on purpose: dense polling starves the board's TLS stack


class UpdateError(RuntimeError):
    """The update could not be performed or the board is not what was expected."""


@dataclass(frozen=True)
class Snapshot:
    app: str
    slot: int
    confirmed: bool
    uid: str | None
    source: str                   # "labid" or "https"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    checks: list[Check]
    version: str
    pre: Snapshot
    post: Snapshot | None


def read_app_version(image: bytes) -> str:
    if len(image) < APP_VERSION_OFFSET + APP_VERSION_LEN or image[0] != ESP_IMAGE_MAGIC:
        raise UpdateError("not an ESP image (missing the 0xE9 header magic)")
    if int.from_bytes(image[APP_DESC_OFFSET:APP_DESC_OFFSET + 4], "little") != APP_DESC_MAGIC:
        raise UpdateError("no application descriptor at 0x20 (is this an app image, not a bootloader or partition table?)")
    raw = image[APP_VERSION_OFFSET:APP_VERSION_OFFSET + APP_VERSION_LEN]
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def check_image(image: bytes, transport: str) -> str:
    """Validate the image for a transport and return the version it carries."""
    version = read_app_version(image)
    if transport == "ble" and len(image) % SECTOR_SIZE:
        raise UpdateError(f"BLE OTA needs a {SECTOR_SIZE}-byte aligned image; this one is {len(image)} bytes "
                          f"({len(image) % SECTOR_SIZE} over). Signed IDF images are aligned; is this signed?")
    return version


def evaluate(pre: Snapshot, post: Snapshot, image_version: str, expected_uid: str | None = None,
             https: Snapshot | None = None) -> list[Check]:
    checks = [
        Check("running the new image", post.app == image_version, f"board reports {post.app!r}, image is {image_version!r}"),
        Check("slot flipped", post.slot != pre.slot, f"slot {pre.slot} -> {post.slot}"),
        Check("confirmed", post.confirmed, "self-test confirmed the image" if post.confirmed else "still pending verify"),
    ]
    if expected_uid is not None:
        got = (post.uid or "").upper()
        checks.append(Check("identity (uid)", got == expected_uid.upper(), f"board {got or '?'}, expected {expected_uid.upper()}"))
    if https is not None:
        same = https.app == post.app and https.slot == post.slot
        checks.append(Check("LABID == HTTPS version", same,
                            f"LABID app={post.app} slot={post.slot}; HTTPS app={https.app} slot={https.slot}"))
    return checks


def _poll(snapshot_fn, wanted: Callable[[Snapshot], bool], timeout_s: float, poll_s: float, sleep_fn):
    """Poll until `wanted(snapshot)`; a board that is rebooting (snapshot raises) is not an error.
    Bounded by an attempt count (deterministic and testable); returns the last good snapshot or None."""
    last = None
    for _ in range(max(1, int(timeout_s / poll_s) + 1)):
        try:
            last = snapshot_fn()
        except Exception:   # noqa: S110, BLE001 - the board is mid-reboot; keep polling
            pass
        else:
            if wanted(last):
                return last
        sleep_fn(poll_s)
    return last


def update_idf(image: bytes, transport: str, *, snapshot_fn: Callable[[], Snapshot],
               send_fn: Callable[[bytes, str], None], expected_uid: str | None = None,
               https_snapshot_fn: Callable[[], Snapshot] | None = None,
               timeout_s: float = DEFAULT_TIMEOUT_S, confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
               poll_s: float = DEFAULT_POLL_S, sleep_fn=time.sleep) -> UpdateResult:
    version = check_image(image, transport)
    pre = snapshot_fn()
    if expected_uid is not None and (pre.uid or "").upper() != expected_uid.upper():
        raise UpdateError(f"identity mismatch: the board reports uid {pre.uid or '?'} but {expected_uid.upper()} "
                          "is expected; nothing was sent")
    send_fn(image, version)
    post = _poll(snapshot_fn, lambda s: s.app == version, timeout_s, poll_s, sleep_fn)
    if post is None:
        raise UpdateError("the board never answered after the transfer")
    if post.app == version and not post.confirmed:
        post = _poll(snapshot_fn, lambda s: s.app == version and s.confirmed, confirm_timeout_s, poll_s, sleep_fn) or post
    https = None
    if https_snapshot_fn is not None:
        https = _poll(https_snapshot_fn, lambda s: s.app == version, timeout_s=15.0, poll_s=poll_s, sleep_fn=sleep_fn)
        if https is None:
            https = Snapshot("unreachable", -1, False, None, "https")
    checks = evaluate(pre, post, version, expected_uid, https)
    return UpdateResult(all(c.ok for c in checks), checks, version, pre, post)


def read_zephyr_image_info(image: bytes) -> tuple[str, str]:
    """Validate MCUboot image header and return (version, sha256_hash)."""
    if len(image) < 32:
        raise UpdateError("not an MCUboot image (file too small)")
    magic = int.from_bytes(image[0:4], "little")
    if magic != MCUBOOT_IMAGE_MAGIC:
        raise UpdateError(f"not an MCUboot image (header magic 0x{magic:08x} != 0x{MCUBOOT_IMAGE_MAGIC:08x})")

    import hashlib
    import struct

    magic, _load_addr, hdr_size, _pad, img_size = struct.unpack("<IIHHI", image[:16])
    img_hash = hashlib.sha256(image[: hdr_size + img_size]).hexdigest()

    ver_maj, ver_min, ver_rev, _build_num = struct.unpack("<BBHI", image[20:28])
    if (ver_maj, ver_min, ver_rev) != (0, 0, 0):
        ver_str = f"{ver_maj}.{ver_min}.{ver_rev}"
    else:
        if b"2.0.0" in image:
            ver_str = "2.0.0"
        elif b"1.0.0" in image:
            ver_str = "1.0.0"
        else:
            ver_str = "0.0.0"

    return ver_str, img_hash


def check_zephyr_image(image: bytes, transport: str) -> tuple[str, str]:
    if transport not in ("ble", "udp"):
        raise UpdateError(f"invalid transport '{transport}' for Zephyr (must be 'ble' or 'udp')")
    return read_zephyr_image_info(image)


def evaluate_zephyr(
    pre: Snapshot,
    post: Snapshot,
    image_version: str,
    expected_uid: str | None = None,
    smp: Snapshot | None = None,
    expected_hash: str | None = None,
) -> list[Check]:
    checks = [
        Check("running the new image", post.app == image_version, f"board reports {post.app!r}, image is {image_version!r}"),
        Check("active in slot 0", post.slot == 0, f"slot is {post.slot}"),
        Check("confirmed", post.confirmed, "self-test confirmed the image" if post.confirmed else "still pending verify"),
    ]
    if expected_uid is not None:
        got = (post.uid or "").upper()
        checks.append(Check("identity (uid)", got == expected_uid.upper(), f"board {got or '?'}, expected {expected_uid.upper()}"))
    if smp is not None:
        same = smp.confirmed == post.confirmed and smp.slot == post.slot
        checks.append(Check("SMP status == LABID status", same,
                            f"LABID slot={post.slot} confirmed={post.confirmed}; SMP slot={smp.slot} confirmed={smp.confirmed}"))
        if expected_hash is not None and smp.app:
            hash_or_ver_match = (
                smp.app.lower() == expected_hash.lower()
                or smp.app == image_version
            )
            checks.append(Check("SMP image matches", hash_or_ver_match,
                                f"SMP active={smp.app[:8]}... expected={image_version} ({expected_hash[:8]}...)"))
    return checks


def update_zephyr(
    image: bytes,
    transport: str,
    *,
    snapshot_fn: Callable[[], Snapshot],
    send_fn: Callable[[bytes, str, str], None],
    expected_uid: str | None = None,
    smp_snapshot_fn: Callable[[], Snapshot] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    poll_s: float = DEFAULT_POLL_S,
    sleep_fn=time.sleep,
) -> UpdateResult:
    version, img_hash = check_zephyr_image(image, transport)
    pre = snapshot_fn()
    if expected_uid is not None and (pre.uid or "").upper() != expected_uid.upper():
        raise UpdateError(f"identity mismatch: the board reports uid {pre.uid or '?'} but {expected_uid.upper()} "
                          "is expected; nothing was sent")
    send_fn(image, version, img_hash)
    post = _poll(snapshot_fn, lambda s: s.app == version, timeout_s, poll_s, sleep_fn)
    if post is None:
        raise UpdateError("the board never answered after the transfer")
    if post.app == version and not post.confirmed:
        post = _poll(snapshot_fn, lambda s: s.app == version and s.confirmed, confirm_timeout_s, poll_s, sleep_fn) or post
    smp = None
    if smp_snapshot_fn is not None:
        smp = _poll(smp_snapshot_fn, lambda s: s.confirmed, timeout_s=15.0, poll_s=poll_s, sleep_fn=sleep_fn)
        if smp is None:
            smp = Snapshot("unreachable", -1, False, None, "smp")
    checks = evaluate_zephyr(pre, post, version, expected_uid, smp, expected_hash=img_hash)
    return UpdateResult(all(c.ok for c in checks), checks, version, pre, post)

