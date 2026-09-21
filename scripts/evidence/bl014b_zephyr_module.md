# BL-014b evidence — Packaging: Zephyr module (native_sim), 2026-09-22

Implementation: Zephyr module packaging and host `native_sim` verification for `common/labid`:
- **Dual-System CMake Registration**:
  - `common/labid/CMakeLists.txt` builds both as an ESP-IDF component (`if(ESP_PLATFORM) idf_component_register(...)`) and as a Zephyr module (`else() zephyr_library()`).
  - Added `zephyr_include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)` to export the public API headers (`labid.h`, `labid_dispatch.h`) to consumer applications.
  - Zephyr module definition `common/labid/zephyr/module.yml` points CMake and Kconfig to `common/labid`.
  - Kconfig symbol `CONFIG_LABID` controls compilation of `src/labid.c` and `src/labid_dispatch.c`.
- **Smoke Test Application**:
  - Created `esp_zephyr/test/` with `CMakeLists.txt`, `prj.conf` (`CONFIG_LABID=y`), and `src/main.c`.
  - Exercises:
    1. Frame construction via `labid_build_frame()` and CRC16 check vector calculation.
    2. Request dispatching through `labid_ctx_init()` and `labid_ctx_feed()` with a provider answering `HELLO`, `ID?` (board=zephyr, uid=ACA7042C3B04), and error handling on unknown commands (`BOGUS`).
  - Native simulation execution clean halt via `posix_exit(failures ? 1 : 0)`.
- **Runner Script**:
  - Created `scripts/zephyr_native_test.sh` mirroring `scripts/idf_linux_test.sh`. Builds with `west build -b native_sim` and executes `./build/zephyr/zephyr.exe`.

## Acceptance Criteria — PASS

- **AC1: "Builds for Zephyr native_sim"** — **PASS**:
  - Module cleanly discovered via `EXTRA_ZEPHYR_MODULES`.
  - Both `src/labid.c` and `src/labid_dispatch.c` compiled and linked into `lib..__..__bootlab-esp__common__labid.a`.
  - `zephyr.exe` executed natively under WSL2; all assertions passed with exit code 0.

## Verification Run Output

```
$ ./scripts/zephyr_native_test.sh
-- Application: /home/msoubhi/bootlab-esp/esp_zephyr/test
-- Zephyr version: 4.4.99 (/home/msoubhi/zephyrproject/zephyr)
-- Board: native_sim, qualifiers: native
-- Found toolchain: host (gcc/ld)
...
[64/102] Building C object modules/labid/CMakeFiles/..__..__bootlab-esp__common__labid.dir/src/labid.c.obj
[71/102] Building C object modules/labid/CMakeFiles/..__..__bootlab-esp__common__labid.dir/src/labid_dispatch.c.obj
[76/102] Linking C static library modules/labid/lib..__..__bootlab-esp__common__labid.a
[100/102] Linking C executable zephyr/zephyr.elf
[101/102] Building native simulator runner, and linking final executable
[102/102] Running utility command for native_runner_executable
*** Booting Zephyr OS build v4.4.0-13033-gbe39a96bdb26 ***
n=40
$LAB,VER,bl=1.0.0,app=2.0.0,slot=0*E077
crc=0x29B1
HELLO -> $LAB,HELLO,proto=1*E211
ID?   -> $LAB,ID,board=zephyr,uid=ACA7042C3B04*59BD
BOGUS -> $LAB,ERR,code=unknown*54A6
zephyr-native smoke: all checks passed
```
Exit code: 0
