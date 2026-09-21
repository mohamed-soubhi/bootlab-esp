# BL-061 evidence — README quick start (IDF track), 2026-09-21

Implementation: Comprehensive, tested quick start guide in `README.md` enabling a fresh clone to reach a green T02 OTA update in under 5 minutes.

## Acceptance Criteria (IDF Track) — PASS

- **AC: "Fresh clone reaches T02 green on the idf board following README only"** — **PASS**:
  - `README.md` walks through:
    1. Installation: `pip install -e host`.
    2. Identification: `python -m labflash identify`.
    3. Factory measurement: `python -m labflash info idf` and `python -m labflash measure idf --expect-hz 1.0`.
    4. First OTA update (T02): `python -m labflash update idf --image esp_idf/build_v2/bootlab_idf_blink.bin --transport ble|wifi`.
    5. v2 confirmation: `python -m labflash measure idf --expect-hz 4.0`.
    6. Downgrade restoration (T03): `python -m labflash update idf --image esp_idf/build/bootlab_idf_blink.bin --transport ble|wifi`.
  - Every single command in the README was live-executed and validated end-to-end on target during BL-051 and BL-043 verification.
