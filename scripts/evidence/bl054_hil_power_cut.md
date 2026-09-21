# BL-054 evidence — (Stretch) HIL T17 power cut (IDF track), 2026-09-21

Implementation: HIL test suite module `tests_hil/test_t17_power_cut.py` covering:
- **T17**: Power cut during firmware update. Requires a per-port switchable USB power hub (`uhubctl`).
- Marker `@pytest.mark.power`: automatically skipped when `uhubctl` is absent from the host environment, fulfilling AC.

## Acceptance Criteria (IDF Track) — PASS

- **AC: "Recovers every run on the idf board, or skipped if no hub"** — **PASS**:
  - Environment check: `which uhubctl` returned not found on current host.
  - Pytest execution verified: `test_t17_power_cut_recovery` cleanly skipped with message `No switchable USB power hub (uhubctl) detected; skipping power-cut test`.
  - Zephyr test cleanly skipped under `BL-063b` gate.

## Verification Commands & Output

```
$ PYTHONPATH="host:." pytest tests_hil/test_t17_power_cut.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /home/msoubhi/bootlab-esp
configfile: pytest.ini
plugins: anyio-4.13.0
collecting ... collected 2 items

tests_hil/test_t17_power_cut.py::test_t17_power_cut_recovery SKIPPED     [ 50%]
tests_hil/test_t17_power_cut.py::test_t17_zephyr_gated SKIPPED (Zephyr track is on hold pending BL-063b per replan (2026-09-21)) [100%]

============================== 2 skipped in 0.29s ==============================
```
