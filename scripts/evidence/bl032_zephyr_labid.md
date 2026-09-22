# BL-032 evidence — Zephyr LABID port on console, 2026-09-22

Implementation and hardware verification on physical target board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, busid `6-3`, `/dev/ttyACM0`):

## 1. Subsystem Implementation
- **Zephyr LABID Frame Server**:
  - Implemented in `esp_zephyr/app/src/labid_port_zephyr.[ch]` and integrated with `esp_zephyr/app/src/main.c`.
  - Configured Devicetree and Kconfig:
    - `CONFIG_LABID=y` (from `modules/labid`)
    - `CONFIG_HWINFO=y`, `CONFIG_HWINFO_ESP32=y` (hardware UID extraction from eFuse MAC)
    - `CONFIG_UART_INTERRUPT_DRIVEN=y`, `CONFIG_RING_BUFFER=y`
  - Ring buffer (`s_rx_ring`) and semaphore (`s_rx_sem`) driven by `uart_irq_callback_user_data_set` and `uart_irq_rx_enable` on `DEVICE_DT_GET(DT_CHOSEN(zephyr_console))`.
  - Dedicated LABID processing thread (`s_labid_thread`, stack 4096 bytes, priority 7).
  - High-efficiency frame transmitter using `uart_fifo_fill` in 64-byte chunks directly to the ESP32-S3 USB-Serial-JTAG hardware FIFO, avoiding per-character FIFO flushes and packet fragmentation.
  - Automatic boot `ANNOUNCE` frame emitted at startup after a calibrated delay (1500 ms) to guarantee CDC-ACM port readiness across USB/IP.
- **Host Driver Enhancements (`host/labflash/identify.py`)**:
  - `SerialLineTransport`: Added write buffer flush (`self._ser.flush()`) and chunked read buffering in `read1()` with a 20 ms read timeout to ensure non-blocking, line-accurate frame dispatching.
  - All 119 unit tests passing (`pytest host/tests`).

---

## 2. Acceptance Criteria Results — PASS

- **AC1: ANNOUNCE ≤ 2 s** — **PASS**:
  - Emitted cleanly on startup at **1.66 s** post-reset.
  - Announce frame content:
    `$LAB,ANNOUNCE,proto=1,board=zephyr,uid=ACA7042C3B04,app=1.0.0*8D6F`
- **AC2: ID?, VER?, STATE? ≤ 100 ms** — **PASS**:
  - Individual command latencies:
    - `ID?`: **28.13 ms** (and down to 16.94 ms) ≤ 100 ms
    - `VER?`: **8.93 ms** (and down to 21.67 ms) ≤ 100 ms
    - `STATE?`: **27.71 ms** (and down to 25.19 ms) ≤ 100 ms
    - `PING,n=42`: **19.31 ms** ≤ 100 ms
  - Over 1,000 continuous requests:
    - Min latency: **2.61 ms**
    - Mean latency: **21.61 ms**
    - 95th percentile latency: **47.85 ms**
- **AC3: 1,000 requests under heavy logging, 0 corrupt** — **PASS**:
  - Target board actively streamed heartbeat logs at 1 Hz from the main blink loop during testing.
  - Continuous 1,000 request stress run executed via `scripts/test_bl032_1000_requests.py`:
    - Total requests sent: **1,000**
    - Successful responses: **1,000 (100.0%)**
    - Corrupt frames: **0 (0.0%)**
    - Request errors: **0 (0.0%)**
    - Device reported `rx_err`: **0**
    - Run duration: **21.64 s** (~46.2 req/s)

---

## 3. Live Hardware Verification Log Output

```text
Opening /dev/ttyACM0 and waiting for ANNOUNCE...
[0.00s] Serial port opened. Waiting up to 4.0s for boot ANNOUNCE...
[1.66s] SUCCESS: Received ANNOUNCE in 1.66s (limit <= 2.0s):
  Raw frame: $LAB,ANNOUNCE,proto=1,board=zephyr,uid=ACA7042C3B04,app=1.0.0*8D6F
  Parsed: {'board': 'zephyr', 'uid': 'ACA7042C3B04', 'app': '1.0.0', 'proto': '1'}
AC1 Result: PASS

Checking single query latencies...
  Query ID? -> 28.13 ms: {'proto': '1', 'board': 'zephyr', 'uid': 'ACA7042C3B04', 'build': 'zephyr-1.0.0-v1', 'app': '1.0.0'}
  Query VER? -> 8.93 ms: {'app': '1.0.0', 'proto': '1', 'board': 'zephyr'}
  Query STATE? -> 27.71 ms: {'app': '1.0.0', 'rx_err': '0', 'uptime_ms': '1720', 'slot': '0', 'confirmed': '1', 'toggles': '2', 'proto': '1', 'board': 'zephyr'}
  Query PING,n=42 -> 19.31 ms: {'proto': '1', 'board': 'zephyr', 'n': '42'}
AC2 Result: PASS (all <= 100 ms)

Starting 1,000 requests stress test under active logging...
  [100/1000] req=PING,n=99 lat=18.4ms (avg=20.5ms)
  [200/1000] req=STATE? lat=21.6ms (avg=21.0ms)
  [300/1000] req=PING,n=299 lat=19.4ms (avg=20.9ms)
  [400/1000] req=ID? lat=20.7ms (avg=21.2ms)
  [500/1000] req=STATE? lat=25.2ms (avg=21.4ms)
  [600/1000] req=VER? lat=21.8ms (avg=21.5ms)
  [700/1000] req=PING,n=699 lat=20.2ms (avg=21.7ms)
  [800/1000] req=ID? lat=20.2ms (avg=21.6ms)
  [900/1000] req=STATE? lat=24.5ms (avg=21.6ms)
  [1000/1000] req=VER? lat=21.7ms (avg=21.6ms)

Stress test completed in 21.64s (46.2 req/s).
Latency min/avg/p95/max: 2.61 / 21.61 / 47.85 / 161.56 ms
Successful: 1000 / 1000 (100.0%)
Corrupt/Failed: 0
Final device reported state: {'app': '1.0.0', 'rx_err': '0', 'uptime_ms': '23377', 'slot': '0', 'confirmed': '1', 'toggles': '46', 'proto': '1', 'board': 'zephyr'}
AC3 Result: PASS
```
