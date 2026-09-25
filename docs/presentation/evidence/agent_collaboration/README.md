# Working with a second, cheaper AI agent (evidence for the presentation)

**Setup.** The lead agent (Claude, in the main repo) delegated bounded, low-risk work to a second agent: `deepseek-v4.1-flash:cloud`
served through Ollama, running as a headless Claude Code session in its own git worktree (`~/bootlab-esp-cheap`, branch `bl069-cheap`).
The lead drove it from the shell with `ollama launch claude --model deepseek-v4.1-flash:cloud --yes -- -p "<short instruction>" --permission-mode acceptEdits
--allowedTools Read Edit Write Bash --disallowedTools "Bash(git:*)" "Bash(rm:*)" ...`; the human owner approved the arrangement and the guardrails.

**The loop (same for every task).**
1. The lead writes the **tests first** (the spec), then a task file `Tnn.md` with the exact API and the do-not-touch list.
2. The agent implements against the tests in the worktree, never editing them, and writes a report `outbox/Tnn.md` with the real command output.
3. The lead **re-runs the tests, ruff and mypy itself, reads the whole diff**, and only then copies the file into the main repo. Nothing the agent wrote reached
   the repo unreviewed; nothing safety- or hardware-critical was delegated.

**Guardrails** (`agent_rules_CLAUDE.local.md`, plus flags on the command line): no git writes, no `rm`/`curl`/`ssh`/`sudo`, no reads of `keys/` or `.local/`,
no hardware, no editing tests, no new dependencies. The model is a cloud model, so nothing sensitive was ever put in a task.

## What was delegated and what the lead did with it
| Task | Deliverable | Spec (tests written first) | Agent result | Lead's review |
|---|---|---|---|---|
| T01 | `host/labflash/imagegen.py` (seeded variant generator) | `host/tests/test_imagegen.py` | 13 tests pass; flagged a real 0.4 % risk (pad spread for arbitrary seed bases) | accepted; risk handled by pinning the seed base |
| T02 | `host/labflash/poolmanifest.py` (manifest + validation) | `host/tests/test_poolmanifest.py` | 18 tests pass | accepted; lead later added `content_sha256` and the too_big invariant |
| T03 | `tests_hil/pool_schedule.py` (both-slot install schedule) | `tests_hil/test_pool_schedule_unit.py` | 14 tests pass | accepted; a LIVE run later exposed a flaw in the spec (see below), lead changed the ordering |
| T04 | `docs/BL069_IMAGE_POOL.md` | pin-doc sync test in `test_pinpolicy.py` | test passes, copied pin reasons verbatim | accepted, one wording fix |
| T05 | LESSONS traps 25-30 | facts supplied in the task | followed the fact list, labelled the trailer claim "not yet confirmed on hardware" | accepted as written |
| T06 | `tests_hil/soak_model.py` (seeded picker + outcome model) | `tests_hil/test_soak_model_unit.py` | 23 tests pass | accepted; lead later added the "never re-send the running version" rule and a `check_pending` flag |
| T07 | `docs/BL067_RANDOM_SOAK.md` (runbook) | none (docs) | 192-line runbook from the code | accepted, then patched by the lead for later runner changes |
| T08 | `tests_hil/compare_boards.py` (board-vs-board report, BL-072) | `tests_hil/test_compare_boards_unit.py` | 8 tests pass, ruff and mypy clean | accepted |

The agent never edited a test, never touched git or keys, and every module it produced passed its tests on first delivery. **What it was NOT trusted with:** the pin
allowlist, signature handling, firmware C code, the hardware runners, anything that talks to a board, and all commits.

## Where the spec was wrong, not the agent (a fair account)
The agent implemented T03 exactly as specified (reverse the order on the second sweep). The live hardware run showed that this repeats the image just installed at
each sweep boundary, and the update CLI reports a false FAIL when the version it sends is already running (LESSONS Trap 33). The lead fixed the schedule and the
soak picker. Delegating to a cheap model did not remove the need for the live run, and the live run found what the tests could not.

## Files here
- `inbox/T01..T08.md`: the instructions given to the agent (spec, API, rules). `outbox/T01..T08.md`: the agent's reports.
- `runs/run_T02..T08.log`: the raw output of each headless run (T01 was run by the owner in the agent's own window; its report is `outbox/T01.md`).
- `agent_rules_CLAUDE.local.md`: the rules file the agent read first.
The code it produced lives in the repo under the paths above; `git log` shows the lead's commits that integrated it.
