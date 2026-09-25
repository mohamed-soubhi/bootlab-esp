# Cheap-agent worktree rules (BL-069)

You are the delegated implementer. The lead agent (Claude) writes the tests; you make them pass. Work ONLY in
this directory (`/home/msoubhi/bootlab-esp-cheap`, branch `bl069-cheap`).

## Protocol
1. Read `.agent/inbox/`: do the lowest-numbered task file that has no matching `.agent/outbox/Tnn.md`.
2. Implement exactly what the task says, in the files it names. Tests are the spec: never edit a test file.
   If a test looks wrong or impossible, STOP that task and say so in the outbox report; do not "fix" the test.
3. Write `.agent/outbox/Tnn.md`: files changed, the exact pytest/ruff/mypy command output (last lines), any
   deviation or doubt. Then stop and wait; do not start the next task unless told.

## Run commands (from this directory)
    PYTHONPATH=host:. /home/msoubhi/bootlab-esp/.venv/bin/python -m pytest <test file> -q
    /home/msoubhi/bootlab-esp/.venv/bin/ruff check <files>
    /home/msoubhi/bootlab-esp/.venv/bin/mypy host/labflash/<module>.py

## Hard rules (violating any = task rejected)
- NEVER run `git commit`, `git push`, `git add`, `git checkout`, `git stash`, or touch the main repo `/home/msoubhi/bootlab-esp`.
- NEVER read, copy or print anything under `keys/`, `.local/`, `*.pem`, `credentials.env`, `rig*.yaml`.
- NEVER touch hardware: no serial ports, no `idf.py`, no `esptool`, no network calls to boards.
- Do NOT edit: any `test_*.py`, `host/labflash/{pinpolicy,imagefmt,build,update,labid,provision}.py`,
  `esp_idf/**`, `esp_zephyr/**`, `tests_hil/soak.py`, `tests_hil/live_backend.py`, `.github/**`, `tickets/**`.
- No new dependencies. Standard library only. Python >= 3.11, `from __future__ import annotations`.
- Match surrounding style: type hints, short docstrings, no comments that restate code, ruff clean, mypy clean.
- Immutability: frozen dataclasses, build new values instead of mutating.
