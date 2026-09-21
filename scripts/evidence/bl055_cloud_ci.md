# BL-055 evidence — `build.yml` cloud CI (IDF track), 2026-09-21

Implementation: Cloud CI workflow `.github/workflows/build.yml` on GitHub Actions covering:
1. `Forbidden Config & Security Checks`: forbids eFuse commands, hardware secure boot in sdkconfig, committed keys/secrets.
2. `LABID Unit & Fuzz Smoke Tests`: CMake + CTest for LABID Unity unit tests and libFuzzer smoke run (1000 iterations).
3. `Python Host Tool Unit Tests`: Ruff linting, MyPy type checking, and Pytest mocked unit tests (115 passing, coverage ≥ 80%).
4. `ESP-IDF Build & Sign (All Variants)`: Containerized build with `espressif/idf:v6.0.3`, compiling and signing all 5 IDF variants (`v1`, `v2`, `no_confirm`, `hang`, `bad_sig`) with CI test keys, and uploading signed binary artifacts.

## Acceptance Criteria (IDF Track) — PASS

- **AC1: "Green on main for the IDF build"** — **PASS**:
  - GitHub Actions Workflow: `build.yml (Cloud CI)`
  - Run ID: `35644309927` on branch `master` (commit `52a5fc005f52134b516a41a00964b0e81291a351`)
  - Status: All 4 jobs completed with `success`:
    - `Forbidden Config & Security Checks` (ID `106480993673`): **success** (7s)
    - `LABID Unit & Fuzz Smoke Tests` (ID `106480993624`): **success** (23s)
    - `Python Host Tool Unit Tests` (ID `106480993717`): **success** (26s)
    - `ESP-IDF Build & Sign (All Variants)` (ID `106480993266`): **success** (9m45s)

- **AC2: "Signed IDF artifacts uploaded"** — **PASS**:
  - Artifact Name: `idf-firmware-variants`
  - Artifact ID: `10660037565`
  - Size: 3,384,171 bytes (~3.38 MB)
  - Contents uploaded:
    - `esp_idf/build/bootloader/bootloader.bin`
    - `esp_idf/build/partition_table/partition-table.bin`
    - `esp_idf/build/ota_data_initial.bin`
    - `esp_idf/build/bootlab_idf_blink.bin` (v1)
    - `esp_idf/build_v2/bootlab_idf_blink.bin` (v2)
    - `esp_idf/build_no_confirm/bootlab_idf_blink.bin` (no_confirm)
    - `esp_idf/build_hang/bootlab_idf_blink.bin` (hang)
    - `esp_idf/build_bad_sig/bootlab_idf_blink.bin` (bad_sig)

## Verification Output

```
$ gh run view 35644309927
✓ master build.yml (Cloud CI) · 35644309927
Triggered via push about 10 minutes ago

JOBS
✓ ESP-IDF Build & Sign (All Variants) in 9m45s (ID 106480993266)
✓ LABID Unit & Fuzz Smoke Tests in 23s (ID 106480993624)
✓ Forbidden Config & Security Checks in 7s (ID 106480993673)
✓ Python Host Tool Unit Tests in 26s (ID 106480993717)

ARTIFACTS
idf-firmware-variants
```

```
$ gh api repos/mohamed-soubhi/bootlab-esp/actions/runs/35644309927/artifacts
{
  "total_count": 1,
  "artifacts": [
    {
      "id": 10660037565,
      "name": "idf-firmware-variants",
      "size_in_bytes": 3384171,
      "expired": false,
      "workflow_run": {
        "id": 35644309927,
        "head_sha": "52a5fc005f52134b516a41a00964b0e81291a351"
      }
    }
  ]
}
```
