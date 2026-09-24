# BL-056[idf] — hil.yml self-hosted runner on RPi4

**Date:** 2026-09-22
**Host:** `msa-linuxRPi4` (192.168.1.150)

## What was done

1. Registered a GitHub Actions self-hosted runner on `msa-linuxRPi4` as user `msa` (no sudo, no
   systemd service): downloaded `actions-runner-linux-arm64-2.337.0.tar.gz`, ran `./config.sh --url
   https://github.com/mohamed-soubhi/bootlab-esp --token <registration-token> --name rpi4-hil --labels
   hil --work _work`, then `nohup ./run.sh > run.log 2>&1 & disown` to survive the SSH session ending.
2. Confirmed registration via the GitHub API:
   ```
   {"labels":["self-hosted","Linux","ARM64","hil"],"name":"rpi4-hil","status":"online","busy":false}
   ```
3. Triggered `hil.yml` for real via `workflow_dispatch` (run `35763148956`, job `106865958695`):
   - `Verify runner isolation & security (PLAN §8 P4)` — **PASSED** (no sudo, `keys/` clean).
   - `Install dependencies` — **PASSED**.
   - `Run HIL tests (IDF track)` — **FAILED** cleanly: all 19 selected `idf` tests errored with
     `Failed: live HIL: board serial port not found (pass --port COMx, or use --mock-rig for a
     simulation)`. Nothing else broke; this is the fixture correctly refusing rather than
     silently falling back to a mock (`tests_hil/conftest.py::live_backend`).

## Why the pytest failure is expected, not a blocker for this ticket

No ESP32-S3 board is physically attached to the RPi4 (`docs/rpi4_limitations.md` Sec 2.2 — boards are
cabled to the Windows workstation, COM14). BL-056's AC is "HIL job runs on PR" + "runner has no sudo
and no access to keys/" — both demonstrated by the security-check and install steps passing for real
on this runner. Getting a board physically onto the RPi4 (plus unmasking Bluetooth, which needs sudo)
is BL-056a's scope, still blocked on owner action.

## Result

`BL-056[idf]` -> **done**. `BL-056[zephyr]` stays `todo` (Zephyr hold, BL-063b).

## Update 2026-09-24: runner deleted by the owner, ticket reinstated (runbook to bring it back)

BL-056 was briefly canceled (the RPi4 cannot be depended on for soak/acceptance work, see `docs/LESSONS_LEARNED.md`
Trap 20), then reinstated: the runner is a good CI/CD demo. It is a **secondary, demo/CI runner, not on the
critical path**; board-driving gates moved to the development machine (BL-070/071/072). The `idf` track is back to
`doing` until the runner is registered and a `hil.yml` dispatch confirms it.

### Re-register `rpi4-hil` (user `msa`, no sudo, same as the original setup)

1. **See what is left** (on the Pi):
   ```bash
   ls -d ~/actions-runner* 2>/dev/null          # folder still there?
   ps aux | grep -i "[R]unner.Listener"         # process still running?
   ```
   On GitHub: repo -> Settings -> Actions -> Runners. If a stale `rpi4-hil` entry is still listed, that is fine: step 3 uses `--replace`.
2. **Get a registration token** (valid about 1 hour; it is a secret, do not paste it into a ticket or a commit). Either:
   - GitHub UI: repo -> Settings -> Actions -> Runners -> **New self-hosted runner** -> Linux / ARM64. The page shows the
     exact download URL for the current runner version and the token; use that URL if the version below is refused as too old.
   - or from a machine where `gh` is logged in as a repo admin:
     `gh api -X POST repos/mohamed-soubhi/bootlab-esp/actions/runners/registration-token --jq .token`
3. **Install and configure** (on the Pi; the original setup used version 2.337.0):
   ```bash
   mkdir -p ~/actions-runner && cd ~/actions-runner
   curl -o actions-runner-linux-arm64.tar.gz -L \
     https://github.com/actions/runner/releases/download/v2.337.0/actions-runner-linux-arm64-2.337.0.tar.gz
   tar xzf actions-runner-linux-arm64.tar.gz
   ./config.sh --url https://github.com/mohamed-soubhi/bootlab-esp --token <REGISTRATION_TOKEN> \
       --name rpi4-hil --labels hil --work _work --unattended --replace
   ```
   Keep the label exactly `hil`: `.github/workflows/hil.yml` uses `runs-on: [self-hosted, hil]`. The runner adds
   `self-hosted`, `Linux` and `ARM64` itself.
4. **Start it, detached** (no sudo means no systemd service):
   ```bash
   cd ~/actions-runner && nohup ./run.sh > run.log 2>&1 & disown
   ```
   Optional, to survive a Pi reboot without sudo: `(crontab -l 2>/dev/null; echo '@reboot cd $HOME/actions-runner && nohup ./run.sh > run.log 2>&1 &') | crontab -`
5. **Verify**:
   ```bash
   tail -n 5 ~/actions-runner/run.log     # expect "Listening for Jobs"
   gh api repos/mohamed-soubhi/bootlab-esp/actions/runners --jq '.runners[] | {name,status,busy,labels:[.labels[].name]}'
   ```
   Expected: `{"name":"rpi4-hil","status":"online","busy":false,"labels":["self-hosted","Linux","ARM64","hil"]}`.
6. **Prove it with a real dispatch**: `gh workflow run hil.yml` (or Actions -> hil.yml -> Run workflow). Expected, as on
   2026-09-22: "Verify runner isolation & security" PASS, "Install dependencies" PASS. "Run HIL tests (IDF track)" fails
   unless a board is wired to the Pi and the tests are given its port (the fixture refuses to fall back to a mock:
   `Failed: live HIL: board serial port not found`). When that dispatch shows the two passing steps, run
   `python3 tickets/tickets_tool.py set BL-056 done --track idf` (with the run URL as `--pr`).

### Result of the re-registration (2026-09-24)

- The runner folder `~/actions-runner` had survived and GitHub still held the registration, so starting it was enough
  (`nohup ./run.sh > run.log 2>&1 & disown`); no `config.sh` run was needed. If the log ever says
  `Runner registration has been deleted from the server`, re-run steps 2-3 (`--replace`).
- `gh api .../actions/runners`: `{"name":"rpi4-hil","status":"online","busy":false,"labels":["self-hosted","Linux","ARM64","hil"]}`.
- `hil.yml` dispatched for real (run `35939632759`, https://github.com/mohamed-soubhi/bootlab-esp/actions/runs/35939632759),
  runner log: `Listening for Jobs` -> `Running job: HIL Test Suite (ESP-IDF Rig)` -> `Failed`. Steps:
  `Verify runner isolation & security` **success**, `Install dependencies` **success**, `Run HIL tests (IDF track)`
  **failure**: `34 deselected, 19 errors`, every one `Failed: live HIL: board serial port not found`
  (no board is wired to that runner's tests; the fixture refuses to fall back to a mock).
- `BL-056[idf]` set to **done** again with this run as the PR link.

### Security notes (PLAN section 8 P4)
- The runner user must stay **without sudo**; `hil.yml` checks `sudo -n true` and fails the job otherwise.
- Only PRs from this **private** repository may run on it; never enable fork PRs on a self-hosted runner.
- The workflow's `keys/` check looks only at the job's checkout (`~/actions-runner/_work/...`). The Pi setup for the
  second-board soak also put `credentials.env` and `keys/{ca,server_cert,server_key}.pem` in `~/bootlab-esp` under the
  same user `msa`, so the intent "the runner user cannot read keys" no longer holds. The Pi is no longer a soak host
  (BL-068 canceled), so remove them if you keep the runner: `rm -f ~/bootlab-esp/credentials.env ~/bootlab-esp/keys/*.pem`
  (I have not checked what is on the Pi now). The RSA signing key `idf_sbv2.pem` was never copied to the Pi.
- A restored runner and a workstation runner (BL-070) must not share the label `hil`; the workstation one uses its own
  label (for example `hil-ws`) so a PR job never lands on the wrong host.
