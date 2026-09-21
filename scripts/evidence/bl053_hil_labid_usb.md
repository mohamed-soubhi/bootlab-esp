# BL-053 evidence — HIL T10–T15 LABID + identity + USB (IDF track), 2026-09-21

Implementation: HIL test suite module `tests_hil/test_t10_t15_labid_usb.py` covering:
- **T10**: `identify` mapping verification (UID matches `rig.yaml`).
- **T11**: Mandatory `ID` fields valid (`board`, `mcu`, `hw`, `uid`, `os`, `flash_kb`), UID verified stable across repeated queries.
- **T12**: Version consistency: LABID reported `app` and `slot` equals the HTTPS `/version` response (`app=1.0.0, slot=0`).
- **T13**: LABID protocol robustness: invalid CRC, oversized payload (>200 bytes), and garbage non-frame data are handled safely without crash or reboot.
- **T14**: Query stress: consecutive back-to-back requests during active operation produce 0 corrupt responses.
- **T15**: Port resolution bounded by ≤ 5.0 s.

## Acceptance Criteria (IDF Track) — PASS

- **AC: "All green on the idf board"** — **PASS**:
  - Live on-target verification executed against `lab-esp-idf` (`E0:72:A1:AA:23:90`, `COM14`, `192.168.1.152`):
    - `test_t10_identify_mapping`: **PASS** (mapped to `E072A1AA2390`).
    - `test_t11_id_fields_and_uid_stability`: **PASS** (UID `E072A1AA2390`, HW `esp32s3_devkitc`, MCU `esp32s3` stable across queries).
    - `test_t12_version_consistency`: **PASS** (HTTPS `app=1.0.0, slot=0` == LABID `app=1.0.0, slot=0`).
    - `test_t13_labid_robustness_framing`: **PASS** (Bad CRC returns `ERROR`, oversized frame returns `ERROR`, garbage rejected, device remains online).
    - `test_t14_labid_query_stress`: **PASS** (20/20 requests successful, 0 corrupt).
    - `test_t15_port_resolution_speed`: **PASS** (Port resolved well under 5.0 s).
  - Zephyr board test cleanly skipped with message `Zephyr track is on hold pending BL-063b per replan (2026-09-21)`.

## Verification Commands & Output

### 1. Live Target Run
```
$ PYTHONPATH="host:." pytest tests_hil/test_t10_t15_labid_usb.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/msoubhi/bootlab-esp
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 7 items

tests_hil/test_t10_t15_labid_usb.py::test_t10_identify_mapping PASSED    [ 14%]
tests_hil/test_t10_t15_labid_usb.py::test_t11_id_fields_and_uid_stability PASSED [ 28%]
tests_hil/test_t10_t15_labid_usb.py::test_t12_version_consistency PASSED [ 42%]
tests_hil/test_t10_t15_labid_usb.py::test_t13_labid_robustness_framing PASSED [ 57%]
tests_hil/test_t10_t15_labid_usb.py::test_t14_labid_query_stress PASSED  [ 71%]
tests_hil/test_t10_t15_labid_usb.py::test_t15_port_resolution_speed PASSED [ 85%]
tests_hil/test_t10_t15_labid_usb.py::test_t10_t15_zephyr_gated SKIPPED   [100%]

======================== 6 passed, 1 skipped in 41.08s =========================
```

### 2. Mock Rig Mode Run
```
$ PYTHONPATH="host:." pytest tests_hil/test_t10_t15_labid_usb.py -v --mock-rig
============================= test session starts ==============================
collected 7 items

tests_hil/test_t10_t15_labid_usb.py::test_t10_identify_mapping PASSED    [ 14%]
tests_hil/test_t10_t15_labid_usb.py::test_t11_id_fields_and_uid_stability PASSED [ 28%]
tests_hil/test_t10_t15_labid_usb.py::test_t12_version_consistency PASSED [ 42%]
tests_hil/test_t10_t15_labid_usb.py::test_t13_labid_robustness_framing PASSED [ 57%]
tests_hil/test_t10_t15_labid_usb.py::test_t14_labid_query_stress PASSED  [ 71%]
tests_hil/test_t10_t15_labid_usb.py::test_t15_port_resolution_speed PASSED [ 85%]
tests_hil/test_t10_t15_labid_usb.py::test_t10_t15_zephyr_gated SKIPPED   [100%]

========================= 6 passed, 1 skipped in 1.52s =========================
```
