# bootlab-esp — Independent Audit Log

---

## Audit: 2026-09-17T01:29:20+02:00
**Commit audited:** `0318eaf` (`0318eafeea01165a4584011bb81901bd7f93b614`)
**Auditor:** independent audit pass (Claude, Sonnet 5), role: verify only, no fixes applied
**Session host:** WSL2 `HP-MS` — NOT the project's RPi4 (`msa-linuxRPi4`). No `vcgencmd`, no `~/tools/esp-idf`, no `~/zephyr-ws` on this machine. All hardware/power/toolchain-execution checks are CANNOT VERIFY from this session.

### Executive Summary

- **Tickets:** `tickets_tool.py check` PASS (schema valid), but **BL-004 is falsely marked "done"** — `docs/recovery.md` does not exist, failing its own AC. BL-003/BL-007 currently correctly "blocked" (matches reality). BL-002 "done" is **UNVERIFIABLE from here** and its evidence file shows zero acknowledgment of the intermittent Zephyr esptool failure/pause described in the project's own incident history — a gap between what's on disk and what's claimed to have happened.
- **Git hygiene:** PASS. No secrets in history (`keys/`, `backups/`, `*.pem` never committed, confirmed via full-history scan). `git fsck --full` clean (1 benign dangling blob). `.gitignore` history shows only additions, never removals. **BUT**: three unexplained, untracked, uncommitted artifacts exist at repo root — `bootloader/mcuboot/`, `tools/edtt/`, `tools/net-tools/` (each with its own nested `.git`, timestamps from today), and a stray `package.json` — none of which appear in PLAN §3's repo layout. Their presence, with `west.yml`'s `self.path: "."`, is structurally identical to the exact topdir-recursion bug that was supposedly already fixed. Origin unexplained.
- **LABID code (BL-010/011/012/013):** Library is solid. 26/26 Unity tests PASS, `-Wall -Wextra -Werror` clean, CRC vector correct, C tests genuinely load `test_vectors.json` at build time (not hand-duplicated), Python `labid.py` passes the same shared vectors. **Real branch coverage (taken-at-least-once) = 91.57%**, which does clear the 90% bar — but this is a *different number* than the previously reported 90.4%, confirming the metric-substitution problem was real. **BL-012 fuzz harness crashes on the very first run** (heap-buffer-overflow, out-of-bounds read of the fuzzer's own input buffer in `fuzz_labid.c:41`, not in `labid.c` itself) — correctly still "todo", but this needs fixing before anyone marks it done.
- **ESP-IDF toolchain:** UNKNOWN — cannot verify from this host. Evidence file (`IDF_BUILD_PROOF.md`) is internally coherent (v6.0.3, real binary size, exit 0) but not independently re-executable here.
- **Zephyr toolchain:** UNKNOWN — cannot verify from this host, and no in-repo trace of the "pause" decision or the unresolved intermittent esptool failure. Treat BL-002's Zephyr half as unconfirmed until re-run on the actual RPi4.
- **Hardware/power state:** CANNOT VERIFY — wrong machine, no `vcgencmd`, no `lsusb`, no boards connected.

### Ticket-by-ticket table

| Ticket | Claimed | Verified | Evidence | Discrepancy |
|---|---|---|---|---|
| BL-001 | done | PASS (with note) | `.gitignore` covers keys/backups/pem; `versions.env` lists all deps; tree matches PLAN §3 | Extra untracked `bootloader/`, `tools/`, `package.json` at root, not in PLAN §3 tree — clutter, not a missing-AC failure |
| BL-002 | done | **CANNOT VERIFY** (wrong host) / suspicious | `IDF_BUILD_PROOF.md`, `ZEPHYR_HELLO_BUILD_PROOF.md` | Zephyr evidence shows one clean run only; no mention anywhere in repo of the intermittent bad-esptool-form re-failure or owner's "pause Zephyr" decision — either omitted or genuinely resolved, can't tell from repo alone |
| BL-003 | blocked | PASS | no boards on this host either | reason ("boards not on USB") still accurate |
| BL-004 | done | **FAIL** | `docs/recovery.md` does not exist (`find docs -type f` → empty) | AC "docs/recovery.md has the restore command" not met; 2 backups + sha256 do exist and verify correctly |
| BL-005 | blocked | PASS | `rig.yaml`: `led_gpio: unknown`, `psram_mode: unknown` | correctly still unknown, matches block reason |
| BL-006 | done | PASS | 2 keys present in `keys/`; `gen_keys.sh` logic correctly skips existing files; `git status keys/` empty | perms show 777 not 700/600 — filesystem artifact (WSL DrvFs doesn't preserve POSIX bits on `/mnt/c`), not a script bug; script itself does `chmod 700`/`600` |
| BL-007 | blocked | PASS | matches known-incident narrative, correctly reopened from prior false-done | — |
| BL-010 | done | PASS | `gcc -std=c99 -Wall -Wextra -Werror` → exit 0; CRC('123456789')=0x29B1 confirmed | — |
| BL-011 | done | PASS (real numbers differ from claim) | 26/26 Unity tests PASS; line 99.26%; branches executed 100.00%, **taken-at-least-once 91.57%** | Previously reported "90.4%" matches neither metric found here — number itself doesn't reconcile, though real taken-branch coverage (91.57%) does clear 90% |
| BL-012 | todo | correctly todo, but harness buggy | libFuzzer+ASan/UBSan build clean; **crashed within seconds**: heap-buffer-overflow in `fuzz_labid.c:41` (harness reads `data[i]` past `size`), not in `labid.c` | Not a labid.c bug — fuzz harness itself needs a bounds fix before this ticket can honestly close |
| BL-013 | done | PASS / partial | `python3 host/labflash/labid.py` → "RESULT: ALL PASS" against same `test_vectors.json` | mypy not installed on this host — "mypy clean" CANNOT VERIFY |
| BL-014 | todo | PASS | `common/labid/zephyr/module.yml`, `idf_component.yml` both absent | correctly not yet built |

### Detailed findings

**A. Ticket integrity**
```
$ python3 tickets/tickets_tool.py check
OK: 47 tickets, 7 epics, no dependency errors
```

**B. Git hygiene**
```
$ git log --all --source --oneline -- keys/ backups/ '*.pem' '*.key'
(empty)
$ git ls-files | grep -E '\.pem|^keys/|^backups/'
(no output, exit 1)
$ git fsck --full
dangling blob dd91d609eca3e440259ee816ae7f78670c1ad2fc
$ git status --short --ignored
 M .gitignore ... (27 mode-only changes, 644→755, WSL/DrvFs artifact, no content diff)
?? bootloader/
?? package.json
?? tools/
!! .mypy_cache/ .venv/ backups/ build/ common/labid/tests/build/ common/labid/tests/unity/ host/labflash/__pycache__/ keys/
```
`.gitignore` history shows only additive diffs across all commits — no entry ever removed.

Backup checksum verification:
```
$ sha256sum backups/esp_ACA7042C3B04.bin backups/esp_E072A1AA2390.bin
cbc2594c...136e1  esp_ACA7042C3B04.bin   (matches recorded .sha256)
d73b6dd5...6fb15  esp_E072A1AA2390.bin   (matches recorded .sha256)
```

**C. Code / test verification**
```
$ ./test_labid
26 Tests 0 Failures 0 Ignored
OK
$ gcov -b -f labid.c.gcda
Lines executed:99.26% of 136
Branches executed:100.00% of 166
Taken at least once:91.57% of 166
```
`gen_test_vectors_h.py` genuinely reads `test_vectors.json` and emits a header at build time — vectors are not hand-copied into C literals.
```
$ python3 host/labflash/labid.py
CRC check vector OK
vectors: 5 valid, 2 bad_crc, 1 unknown, 1 too_long, 4 garbage
RESULT: ALL PASS
```
Fuzz target (BL-012):
```
$ clang -fsanitize=fuzzer,address,undefined -g -O1 -I../include fuzz_labid.c ../src/labid.c -o fuzz
(clean build)
$ ./fuzz -max_total_time=80 corpus/
SUMMARY: AddressSanitizer: heap-buffer-overflow fuzz_labid.c:41:70 in LLVMFuzzerTestOneInput
```
Root cause: `fuzz_labid.c:39-41` computes `klen = data[0] % 3` (0–2) independent of `size`, then reads `data[i]` for `i < klen` — if `size==1`, `data[1]` is read out of bounds. Bug is in the test harness, not `labid.c`.

**D. Toolchain reality check** — CANNOT VERIFY from this host. Evidence files read instead:
- `IDF_BUILD_PROOF.md`: claims v6.0.3, `hello_world.bin` 0x23890 bytes, exit 0 — internally coherent, not re-run here.
- `ZEPHYR_HELLO_BUILD_PROOF.md`: claims rc=0, root cause = PATH shadowing (system esptool 4.7.0 vs venv 5.4.0), single clean run recorded. No mention anywhere in repo of a subsequent re-failure or a decision to pause the Zephyr path.
- `scripts/check_env.sh` correctly built to `exit 1` on any missing/mismatched tool (real `fail()` calls) — logic reviewed, not executed.

**E. Configuration accuracy**
`host/config/rig.yaml`: `led_strip: worldsemi_ws2812` on both boards — typo confirmed fixed (was `worldseni_ws2812`). `led_gpio: unknown` and `psram_mode: unknown` on both boards — correctly still unresolved pending a flashed test.

**F. Hardware state** — CANNOT VERIFY. No `lsusb`, no `vcgencmd` on this machine. No board connected.

**G. PLAN.md drift check**
PLAN §3's repo tree does **not** include `bootloader/`, `tools/`, or `package.json` — untracked, no git history, timestamps from today. `west.yml`'s `self.path: "."` means running `west init -l .` in this repo reproduces the exact previously-fixed topdir bug.

### Recommended corrections

1. Revert BL-004 to `blocked`/`doing` until `docs/recovery.md` exists with the actual restore command.
2. Add a note to BL-002's evidence trail (or a new ticket) recording the intermittent esptool bad-invocation failure and any pause decision; re-run the Zephyr `hello_world` build on the real RPi4 again before trusting it's durably fixed.
3. Fix `fuzz_labid.c:39-43` bounds bug (`klen`/`vlen` must not exceed `size`) before BL-012 can be picked up and closed.
4. Re-report BL-011 coverage using "Taken at least once" (91.57%), not the old 90.4% figure, anywhere it's quoted.
5. Investigate and either commit-and-gitignore-properly or delete `bootloader/`, `tools/`, `package.json` — none belong per PLAN §3, none are in git.
6. Re-verify BL-006 key permissions (700/600) on the actual RPi4 filesystem — this WSL/DrvFs mount cannot show real POSIX bits.

### Open questions

- Every board-connected, power-state, and live-toolchain-execution check is unresolved from this session — needs re-run on the actual Pi.
- Origin of `bootloader/`, `tools/`, `package.json` unknown — need owner confirmation: intentional or accidental clutter.
- Whether the Zephyr PATH-shadowing fix is durable across runs — unconfirmed here.
- mypy not installed on this host — BL-013's "mypy clean" AC unconfirmed either way.

---

## AC3 Observation — 10-minute brown-out window
**Timestamp:** 2026-09-19 (measured window 22:01:27 → 22:11:10, host `msa-linuxRPi4`)
**Duration:** 602.3 s wall / 582.2 s to final sample — 30 samples @ 20 s interval
**Observer:** agent session on the project RPi4 (real host: `vcgencmd`, `journalctl`, boards present)
**Source data:** `scripts/evidence/bl003_ac3_observation.jsonl` (raw per-sample JSONL, committed alongside this entry)

### Result: FAIL

Raw data:
```
uv_start: 224, uv_end: 231   ->  7 NEW under-voltage events
usb_resets: 0 -> 0           ->  0 new resets
temp range: 38.4-42.8 C
throttled: 0x50000 (every sample, all 30)
```

Event timestamps: 22:02, 22:03, 22:04, 22:05, 22:06, 22:09, 22:11
Progression (monotonic UV counter within window):
```
t+40s -> 225, t+160s -> 227, t+261s -> 228, t+321s -> 229, t+502s -> 230, t+582s -> 231
```
Rate: ~1 event / 85 s, sustained across the full window.

### AC3 wording note (recorded so it is not re-litigated)
AC3 = "no brown-out resets over 10 min".
- Literal reading (device resets): **0 resets -> would pass narrowly**
- Intent reading (power-rail integrity): **7 UV events -> fails clearly**
**Recorded as FAIL.** The AC exists to prove power integrity, not merely the
absence of a reset. A rail that dips ~7x per 10 min is not a clean rail.

### Data caveat
`uv_start = 224` here vs `231` observed at an earlier 21:32 check — the absolute
counter appears to have *decreased*, which is impossible for a monotonic counter.
Cause: journal rotation (152.8 MB of journals; `journalctl -b` output is being
vacuumed). Absolute totals are therefore NOT comparable across long spans.
The in-window counter is monotonic and reliable — which is all the measurement used.

### Conclusion
Power fault persists, load-independent (see the earlier 0/1/2-board experiment:
rate unchanged with 0, 1, or 2 boards attached). ~1/min under-voltage dips.
No clean power -> no flash. Burn recommendation stands: perform the bootloader
burn on WSL2 (stable power), not on this rig.

**BL-003 status: unchanged** (left exactly as recorded; this entry is evidence only).
