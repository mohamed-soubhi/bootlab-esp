# BL-069 evidence — signed image pool, build phase (2026-09-25)

Scope of this directory: the OFFLINE build phase (AC1, AC3, AC4, AC6 and gates R2/R3/R6/R7). The hardware phase
(gate R1 and AC5, every image installed on both OTA slots over WiFi and BLE) is NOT done yet and is not claimed here.

## Command
```
PYTHONPATH=host python -m labflash gen-images --out esp_idf/build_pool --seed-base bl069-2026-09-25
```
Result: `wrote 13 images + manifest.json`, 16 min 56 s on the WSL workstation. Files here: `manifest.json` (validated by
`poolmanifest.load_manifest`), `plan.txt` (the generator's plan: role, version, pad, blink, RGB, pins, trailer per image),
`sha256sums.txt` (whole-file hashes of the built `.bin` files; the `.bin` files stay gitignored).

## Pool built
| # | role | version | size (B) | trailer | WiFi | BLE |
|---|------|---------|---------:|--------:|------|-----|
| 0 | valid | gen-fcc50b7a | 2,035,712 | 0 | accept | accept |
| 1 | valid | gen-477ee36e | 3,280,896 | 0 | accept | accept |
| 2 | valid | gen-8ddc7a9e | 3,149,824 | 0 | accept | accept |
| 3 | unaligned_trailer | gen-de2752f3 | 1,317,986 | 3,170 | accept | reject |
| 4 | valid | gen-0c23946e | 2,953,216 | 0 | accept | accept |
| 5 | valid | gen-d3ec723f | 3,674,112 | 0 | accept | accept |
| 6 | near_limit | gen-bc23f981 | 4,132,864 | 0 | accept | accept |
| 7 | valid | gen-a7e974e5 | 2,953,216 | 0 | accept | accept |
| 8 | valid | gen-7ced4815 | 1,904,640 | 0 | accept | accept |
| 9 | unaligned_trailer | gen-6b593e13 | 1,841,012 | 1,908 | accept | reject |
| 10 | valid | gen-0f8f7a30 | 1,839,104 | 0 | accept | accept |
| 11 | valid | gen-ed4ae35d | 2,101,248 | 0 | accept | accept |
| 12 | too_big | gen-a8156d35 | 4,263,936 | 0 | reject | reject |

12 non-too_big images, 13 distinct versions, 11 distinct sizes among the 12. Slot limit 4,194,304 B.

## Gates
- **R2/R3 (pad really grows the image; build time):** trial build with a 1,000,000 B pad gave a 2,232,320 B signed image
  (verified), 96 s cold. A 4096 B pad step gave the same size (`pad 2879488` and `2883584` both -> 4,132,864 B): segments are
  64 KiB aligned, so near_limit / too_big target a 64 KiB window (`genvariants.SIZE_WINDOW`), not an exact byte count.
- **R6 (IDF size check on the near-limit image):** g06 (4,132,864 B) passes `check_sizes.py` on the normal 4 MB partition table.
  g12 (4,263,936 B) is refused by `check_sizes.py` on that table, so it is built against a temporary 5 MB table
  (`genvariants.BIG_PARTITIONS`); IDF's error text is on stdout, not stderr (LESSONS Trap 28).
- **AC1 reproducibility:** rebuilding g00 (seed base above) into a different output directory: 2,035,712 B both times,
  first 2,031,616 B byte-identical, 388 bytes differ, all inside the 4096 B signature sector (RSA-PSS salt). Hence the
  manifest's `content_sha256` (everything before the signature sector) is the reproducibility hash; whole-file `sha256`
  changes on every build (six images rebuilt between runs all differ in `sha256`).
- **R7 (fixed variants unchanged):** v1 rebuilt into a separate dir after the firmware change vs the v1 built on 2026-09-21
  (`sha256 5f0dd2af5e7a...`): both 1,249,280 B; 499 bytes differ, all accounted for: build date/time (0x70-0x85 and
  0x224cd-0x224db), ELF sha256 in the app descriptor (0xb0-0xcf), image hash/checksum tail (0x12ffdf-0x130023), the salted
  signature (388 B at 0x13032c), and 3 single-byte immediates at 0x40c60/0x40cc7/0x40cde which are the `__LINE__` arguments of
  the three `ESP_ERROR_CHECK` calls in `app_main.c` (shifted by 41/44/44 because source lines were inserted above them).
  So the fixed variants are NOT literally byte-identical after the edit (date and line numbers), but same size and the same
  code paths; the plan's "byte-identical" wording is corrected accordingly.
- **AC4:** allowlist and per-group reasons in `docs/BL069_IMAGE_POOL.md`; enforced by `pinpolicy.check_pins`, tested in
  `host/tests/test_pinpolicy.py`. **AC6:** the generated defaults contain only whitelisted `CONFIG_APP_GEN_*` keys and no
  LABID/WiFi/BLE/OTA/confirm token (`host/tests/test_imagegen.py`); the firmware changes are all under `#if CONFIG_APP_GEN_POOL`.

## Not done here
- Gate R1 (append 4096 B to v1, install over WiFi, expect boot + `confirmed=1`): needs the board. The 2 trailer images
  (g03, g09) rest on it.
- AC5 hardware installs: `python -m tests_hil.pool_install` (native Windows, R14), one overnight window.

## Update after code review (same day)
An independent code review of the diff found no critical issues and three HIGH ones; the real ones were fixed and the pool
was rebuilt from the final source (`manifest.json`, `plan.txt`, `sha256sums.txt` here are from that rebuild; same versions,
sizes and pins as the table above, `content_sha256` unchanged for the same seed).
- Pin allowlist is now enforced in three places: `imagegen.defaults_text` (`check_pins`), the builder re-reads the pins from
  the built sdkconfig, and the firmware has a compile-time guard (`GEN_PIN_OK` static assert in `app_main.c`, kept in sync with
  `pinpolicy.SAFE_OUTPUT_PINS` by a host test over every GPIO).
- `pool_install`: a reject step passes only if an install over that transport has already passed (a dead link cannot look like a
  refusal); exceptions and unreadable-board errors are recorded failures; `--resume` is tied to the pool's seed base and manifest
  hash and retries failed steps; a bounded top-up pass (`TOPUP_LIMIT` = 12 installs) closes slot-coverage gaps left by a failure.
- Pool images report their real blink rate over LABID (`500 / blink_ms`, `CONFIG_APP_GEN_BLINK_HZ`) so `labflash measure` works.
- `too_big` invariant: the manifest rejects a `too_big` image whose signed data would fit the slot.
Test status at this point: 364 passed (host tests plus the four hardware-free `tests_hil` suites), ruff and mypy clean.
