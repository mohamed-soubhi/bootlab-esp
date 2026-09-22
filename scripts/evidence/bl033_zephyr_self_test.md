# BL-033 evidence — Zephyr self-test + confirm + twister tests, 2026-09-22

Implementation and hardware verification on physical target board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, busid `6-3`, `/dev/ttyACM0`):

## 1. Subsystem Implementation
- **Zephyr Self-Test State Machine (`esp_zephyr/app/src/app_self_test.[ch]`)**:
  - Implements the self-test specification defined in `PLAN.md` §5.2:
    - Minimum RTOS uptime threshold: $\ge 5000\text{ ms}$ (`APP_SELF_TEST_MIN_UPTIME_MS = 5000U`).
    - Minimum LED toggles threshold: $\ge 5\text{ toggles}$ (`APP_SELF_TEST_MIN_TOGGLES = 5U`).
    - Gated by application variant: confirmable (`v1`, `v2`) vs unconfirmable (`no_confirm`, `hang`).
    - Calls `boot_write_img_confirmed()` via pluggable function pointer upon threshold satisfaction.
    - Idempotent: once confirmed, maintains `status = APP_SELF_TEST_CONFIRMED` without redundant flash write calls.
    - Error propagation: captures any flash driver error code in `last_error` and transitions to `APP_SELF_TEST_FAILED`.
  - Integrated into `esp_zephyr/app/src/main.c`:
    - Application starts in `APP_SELF_TEST_PENDING` (`confirmed=0`), with WS2812 LED indicating Amber during the trial period.
    - Uptime and toggle count checked cyclically in the main blink loop.
    - On self-test pass, `boot_write_img_confirmed()` is executed, `app_is_confirmed()` transitions to `true`, and LED transitions to Green (1 Hz) or Blue (4 Hz).
    - LABID `prov_ver` reports live confirmation status via `confirmed=0` / `confirmed=1`.

- **Twister Unit Test Suite (`esp_zephyr/tests/self_test/`)**:
  - Configured test runner environment for Zephyr `native_sim` (`testcase.yaml`/`tests.yaml`, `CMakeLists.txt`, `prj.conf` with `CONFIG_ZTEST=y`).
  - Implemented 6 test cases in `esp_zephyr/tests/self_test/src/main.c` with mocked MCUboot confirmation API:
    1. `test_init_state`: Verifies initial unconfirmed state and status transitions.
    2. `test_uptime_threshold`: Verifies confirmation is rejected when uptime < 5000 ms even if toggles >= 5.
    3. `test_toggles_threshold`: Verifies confirmation is rejected when toggles < 5 even if uptime >= 5000 ms.
    4. `test_success_confirm`: Verifies exact boundary pass at 5000 ms and 5 toggles, exactly 1 call to `boot_write_img_confirmed()`.
    5. `test_no_confirm_variant`: Verifies that `no_confirm` variant remains unconfirmed indefinitely.
    6. `test_confirm_fn_error`: Verifies error handling when bootloader confirmation returns failure.
  - Automated test runner script `scripts/run_zephyr_twister.sh` with sanitized environment (excluding slow 9P mounts).

---

## 2. Acceptance Criteria Results — PASS

- **AC1: twister passes** — **PASS**:
  - Ran `scripts/run_zephyr_twister.sh` (`twister -T esp_zephyr/tests/self_test -p native_sim`).
  - **1 of 1 executed test configurations passed (100.00%)**.
  - **6 of 6 executed test cases passed (100.00%)**.
  - 0 failed, 0 errored, 0 warnings.
- **AC2: confirmed=1 on board after 5 s** — **PASS**:
  - Flashed signed `v1` image to physical Zephyr board (`AC:A7:04:2C:3B:04`).
  - Executed `scripts/zephyr_confirm_check.py`:
    - At uptime **1629 ms** (< 4.0 s):
      - Query `$LAB,VER?` returned `confirmed=0`
      - Query `$LAB,STATE?` returned `toggles=4`
      - Early unconfirmed check: **PASS**
    - Board continuously polled until uptime $\ge 5500\text{ ms}$:
      - At uptime **5586 ms**:
        - Query `$LAB,VER?` returned `confirmed=1`
        - Query `$LAB,STATE?` returned `toggles=11`
      - Post-5s confirmed check: **PASS**

---

## 3. Verification Logs

### 3.1 Twister native_sim Test Execution
```text
=== Running Zephyr Twister Tests (native_sim) ===
INFO    - Using Ninja..
INFO    - Zephyr version: v4.4.0-13033-gbe39a96bdb26
INFO    - Using 'host/gnu' toolchain variant.
INFO    - Building initial testsuite list...
INFO    - Built testsuite list in 0.03 seconds
INFO    - Writing JSON report /home/msoubhi/bootlab-esp/twister-out/testplan.json
INFO    - JOBS: 12
INFO    - Adding tasks to the queue...
INFO    - Added initial list of jobs to queue
INFO    - 1/1 native_sim/native         bootlab.self_test                                  PASSED (native 0.033s <host/gnu>)

INFO    - 1 test scenarios (1 configurations) selected, 0 configurations filtered (0 by static filter, 0 at runtime).
INFO    - 1 of 1 executed test configurations passed (100.00%), 0 built (not run), 0 failed, 0 errored, with no warnings in 65.42 seconds.
INFO    - 6 of 6 executed test cases passed (100.00%) on 1 out of total 1704 platforms (0.06%).
INFO    - 1 test configurations executed on platforms, 0 test configurations were only built.
INFO    - Saving reports...
INFO    - Writing JSON report /home/msoubhi/bootlab-esp/twister-out/twister.json
INFO    - Writing xunit report /home/msoubhi/bootlab-esp/twister-out/twister.xml...
INFO    - Writing xunit report /home/msoubhi/bootlab-esp/twister-out/twister_report.xml...
INFO    - Run completed
```

### 3.2 Live Hardware Verification (`scripts/zephyr_confirm_check.py`)
```text
=== BL-033 Confirmation Check on /dev/ttyACM0 ===
Port opened. Waiting up to 4.0s for boot ANNOUNCE...
[1.73s] SUCCESS: Received ANNOUNCE: {'proto': '1', 'board': 'zephyr', 'uid': 'ACA7042C3B04', 'app': '1.0.0'}
Early STATE?: {'uptime_ms': '1629', 'reset': 'other', 'blink_hz': '1', 'toggles': '4', 'rx_err': '0'}
Current uptime=1629 ms, toggles=4
Early VER?: {'bl': 'mcuboot', 'app': '1.0.0', 'git': 'db7cfc2', 'build': '20260922T0808Z', 'variant': 'v1', 'slot': '0', 'confirmed': '0'}
Early check (uptime < 4s -> confirmed == '0'): PASS (confirmed=0)
Waiting until uptime >= 5500 ms...
  [Waiting] uptime=2073 ms, toggles=4
  [Waiting] uptime=2489 ms, toggles=5
  [Waiting] uptime=2927 ms, toggles=6
  [Waiting] uptime=3348 ms, toggles=7
  [Waiting] uptime=3777 ms, toggles=8
  [Waiting] uptime=4197 ms, toggles=9
  [Waiting] uptime=4671 ms, toggles=10
  [Waiting] uptime=5104 ms, toggles=10
  [Waiting] uptime=5523 ms, toggles=11
Post-5s VER?: {'bl': 'mcuboot', 'app': '1.0.0', 'git': 'db7cfc2', 'build': '20260922T0808Z', 'variant': 'v1', 'slot': '0', 'confirmed': '1'}
Post-5s STATE?: {'uptime_ms': '5586', 'reset': 'other', 'blink_hz': '1', 'toggles': '11', 'rx_err': '0'}
Post-5s check (uptime >= 5.5s -> confirmed == '1'): PASS

ALL ACs PASSED for BL-033 hardware verification!
```
