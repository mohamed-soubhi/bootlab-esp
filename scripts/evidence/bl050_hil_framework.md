# BL-050 evidence — HIL framework: fixtures, markers, artifacts (IDF track), 2026-09-21

Implementation: HIL test suite framework under `tests_hil/` and root configuration:
1. `pytest.ini`: registered markers (`idf`, `zephyr`, `ble`, `wifi`, `udp`, `labid`, `slow`, `power`) and test discovery paths (`host/tests`, `tests_hil`).
2. `tests_hil/conftest.py`:
   - Command-line arguments: `--board`, `--port`, `--transport`, `--rig-config`, `--artifacts-dir`, `--mock-rig`.
   - Gate enforcement: automatically skips Zephyr tests with explicit reference to `BL-063b`.
   - Per-test artifact isolation in `tests_hil/reports/<test_name>/`.
   - Serial console log capture fixture (`serial_capture -> console.log`).
   - Bluetooth HCI monitor capture fixture (`btmon_capture -> btmon.snoop / btmon.log`).
   - State reset fixture (`factory_reset` ensuring start and end on confirmed v1).
   - Unified harness fixture (`hil_rig`).
3. `tests_hil/test_dummy_hil.py`:
   - Smoke test validating harness initialization, artifact writing, board querying, and v1 confirmation.

## Acceptance Criteria (IDF Track) — PASS

- **AC: "Dummy HIL test runs on the idf board and restores v1"** — **PASS**:
  - Live on-target verification executed against `lab-esp-idf` (`192.168.1.152`):
    - HTTPS `/version` returned `{'app': '1.0.0', 'confirmed': True, 'git': '1.0.0', 'slot': 0}`.
    - Verified version `1.0.0`, slot `0`, and confirmed `True`.
    - Captured `console.log`, `btmon.log`, `dummy_report.txt`, and generated JUnit XML report (`junit.xml`).
  - Zephyr board test cleanly skipped with message `Zephyr track is on hold pending BL-063b per replan (2026-09-21)`.
  - Offline/mock verification also confirmed via `--mock-rig`.

## Verification Commands & Output

### 1. Live Target Run
```
$ PYTHONPATH="host:." pytest tests_hil -v --junitxml=tests_hil/reports/junit.xml
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/msoubhi/bootlab-esp
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 2 items

tests_hil/test_dummy_hil.py::test_dummy_hil_idf_board PASSED             [ 50%]
tests_hil/test_dummy_hil.py::test_dummy_hil_zephyr_board SKIPPED (Zephyr track is on hold pending BL-063b per replan (2026-09-21)) [100%]

-- generated xml file: /home/msoubhi/bootlab-esp/tests_hil/reports/junit.xml ---
========================= 1 passed, 1 skipped in 1.81s =========================
```

### 2. Mock Rig Mode Run
```
$ PYTHONPATH="host:." pytest tests_hil -v --mock-rig
============================= test session starts ==============================
collected 2 items

tests_hil/test_dummy_hil.py::test_dummy_hil_idf_board PASSED             [ 50%]
tests_hil/test_dummy_hil.py::test_dummy_hil_zephyr_board SKIPPED (Zephyr track is on hold pending BL-063b per replan (2026-09-21)) [100%]

========================= 1 passed, 1 skipped in 0.30s =========================
```

### 3. Generated Artifacts
```
$ ls -la tests_hil/reports/test_dummy_hil_idf_board
-rw-r--r-- 1 msoubhi msoubhi 70 btmon.log
-rw-r--r-- 1 msoubhi msoubhi 66 console.log
-rw-r--r-- 1 msoubhi msoubhi 39 dummy_report.txt
```
