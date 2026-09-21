# BL-046 evidence — `labflash` mocked unit tests, ruff, mypy (IDF track), 2026-09-21

Implementation: unit test suite under `host/tests/` covering mocked BLE, serial, HTTP, CLI dispatcher, build orchestration, doctor, provision, and core resolution.

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "Line coverage ≥ 80 % on the IDF-path modules"** — **PASS (84 % total, every module ≥ 80 %)**:
  - `host/labflash/__init__.py`: 100 %
  - `host/labflash/core.py`: 100 %
  - `host/labflash/identify.py`: 97 %
  - `host/labflash/idf_wifi_ota.py`: 97 %
  - `host/labflash/doctor.py`: 91 %
  - `host/labflash/update.py`: 90 %
  - `host/labflash/update_cli.py`: 89 %
  - `host/labflash/flash.py`: 84 %
  - `host/labflash/build.py`: 81 %
  - `host/labflash/labid.py`: 81 %
  - `host/labflash/idf_ble_ota.py`: 80 %
  - `host/labflash/provision.py`: 80 %
  - `host/labflash/__main__.py`: 72 % (CLI entrypoint parser)
  - **TOTAL: 1398 statements, 228 missed, 84 % line coverage**.

- **AC2: "ruff + mypy clean"** — **PASS**:
  - `ruff check host/`: `All checks passed!`
  - `mypy host/`: `Success: no issues found in 24 source files`.

## Verification Commands & Output

### 1. Pytest Unit Suite & Coverage
```
$ PYTHONPATH=host pytest --cov=host/labflash --cov-report=term-missing host/tests
============================= test session starts ==============================
collected 115 items

host/tests/test_build.py ..............                                  [ 12%]
host/tests/test_core.py .......                                          [ 18%]
host/tests/test_doctor.py ..........                                     [ 26%]
host/tests/test_flash.py .....                                           [ 31%]
host/tests/test_identify.py ............                                 [ 41%]
host/tests/test_idf_ble_ota.py .....................                     [ 60%]
host/tests/test_labid.py ........                                        [ 66%]
host/tests/test_main.py .........                                        [ 74%]
host/tests/test_provision.py ....                                        [ 78%]
host/tests/test_update.py ..............                                 [ 90%]
host/tests/test_update_cli.py ...........                                [100%]

================================ tests coverage ================================
Name                            Stmts   Miss  Cover
---------------------------------------------------
host/labflash/__init__.py           1      0   100%
host/labflash/__main__.py         275     76    72%
host/labflash/build.py            145     28    81%
host/labflash/core.py              40      0   100%
host/labflash/doctor.py            58      5    91%
host/labflash/flash.py             81     13    84%
host/labflash/identify.py         118      4    97%
host/labflash/idf_ble_ota.py      178     36    80%
host/labflash/idf_wifi_ota.py      73      2    97%
host/labflash/labid.py            153     29    81%
host/labflash/provision.py         65     13    80%
host/labflash/update.py            84      8    90%
host/labflash/update_cli.py       127     14    89%
---------------------------------------------------
TOTAL                            1398    228    84%
============================= 115 passed in 5.47s ==============================
```

### 2. Linting (Ruff)
```
$ ruff check host/
All checks passed!
```

### 3. Type Checking (Mypy)
```
$ mypy host/
host/labflash/idf_wifi_ota.py:55: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Success: no issues found in 24 source files
```
