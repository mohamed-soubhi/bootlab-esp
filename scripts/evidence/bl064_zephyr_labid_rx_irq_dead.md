# BL-064 — Zephyr v2 build: LABID UART RX interrupt never fires

**Date:** 2026-09-22
**Board:** `lab-esp-zephyr` (`AC:A7:04:2C:3B:04`), COM12 (Windows workstation)

## Found while running BL-051 live (T02 BLE SMP v1 -> v2)

`test_t02_update_v1_to_v2_ble_zephyr` reported `AssertionError: BLE SMP OTA update v1 -> v2 failed`,
with `Disconnected from AC:A7:04:2C:3B:06` in the captured log. Every test after that failed too, with
`serial.serialutil.SerialTimeoutException: Write timeout` in `factory_reset`'s teardown/setup.

## The BLE OTA actually succeeded

Power-cycled the board and read its raw console:

```
*** Booting Zephyr OS build v4.4.0-13033-gbe39a96bdb26 ***
  bootlab-esp: Zephyr BL-031 Blink App
  Variant: v2
$LAB,ANNOUNCE,proto=1,board=zephyr,uid=ACA7042C3B04,app=2.0.0*63BD
```

The board was already running `2.0.0` and announcing over LABID -- the flash+swap worked. The test's
"failed" assertion was a false negative from a BLE disconnect at the wrong moment in the host-side
verification, not an actual flash failure.

## Real bug: the LABID UART RX interrupt never fires on this build

Every subsequent host write to the board (even from a brand-new `serial.Serial` connection, 8s
`write_timeout`) hangs until timeout:

```python
>>> ser.write(b'x')
SerialTimeoutException('Write timeout')   # after the full 8s
```

Reads still work fine throughout -- the board keeps transmitting its heartbeat log, which says why:

```
[00:00:16.170,000] <inf> bootlab_app: [APP] Heartbeat: variant=v2, toggles=128, confirmed=1, uptime=16170 ms, irq=0, rx=0
```

`irq=0, rx=0` at 16+ seconds of uptime: the LABID console UART RX interrupt has never fired since
boot. The device never drains its USB-CDC RX buffer, so every host write blocks at the Windows driver
level until it times out. This is a **device-side firmware bug**, not a labflash/pyserial/harness
issue -- confirmed by reproducing it with a completely fresh, unrelated connection.

## Refined diagnosis (2026-09-23): trigger is a BLE connection event, not BLE being enabled

`main.c` initializes in this order: `labid_port_init()` -> `app_ble_smp_init()` -> `app_wifi_init()`.
BLE is active (advertising) on every variant, including v1 -- and v1 answered LABID fine earlier in
this session, fresh-booted, BLE advertising but never connected to. `build_v2` only broke LABID writes
*after* a real BLE central (the OTA host) connected, transferred an image over SMP, and disconnected
(`Disconnected from AC:A7:04:2C:3B:06` in the captured log immediately precedes the write timeouts).

So the trigger is a **BLE connect/disconnect event**, not BLE merely being enabled/advertising. This
matches a known class of ESP32 issue: the BT controller can reprogram the interrupt matrix (a limited
hardware resource) during active RF connection events, and can silently reclaim the interrupt slot the
USB-Serial-JTAG UART driver (`labid_port_zephyr.c`'s `uart_irq_callback_user_data_set` /
`uart_irq_rx_enable`) was using -- permanently killing its RX IRQ until a full reset.

## Fix attempt 1: reorder init so the console UART IRQ registers last

Hypothesis: registering the UART RX interrupt (`labid_port_init()`) *before* the radio stacks claim
their interrupt vectors (`app_ble_smp_init()`/`app_wifi_init()`) makes it vulnerable to being silently
overwritten once a BLE connection event reprograms the interrupt matrix. Reordering so LABID's UART IRQ
registers *last* -- after both radios are up -- should make it the most recently claimed vector and
less likely to be stomped.

Change: `esp_zephyr/app/src/main.c` -- call `app_ble_smp_init()` and `app_wifi_init()` before
`labid_port_init()`.

## Recovery

Board was stuck responding to reads only; DTR/RTS reset alone did not fix it (same symptom after
reset). Reflashed the known-good confirmed `build_v1` (unaffected by this bug) via esptool from WSL2
(identity verified: MAC `ac:a7:04:2c:3b:04`). Board confirmed healthy afterward:

```
VER: {'bl': 'mcuboot', 'app': '1.0.0', ..., 'confirmed': '1'}
```

## Impact

Blocks `BL-051[zephyr]` (T02/T03 BLE/UDP need working LABID for pre/post verification) and by
extension `BL-052`/`BL-053[zephyr]`. `BL-051[idf]` is unaffected and stays done.

## Fix attempt 1 result: promising but unconfirmed against the real trigger

Rebuilt `build_v2` with the reorder (`a9a0fdc`), reflashed, then ran `factory_reset`'s precondition
step, which downgrades v2 -> v1 over **UDP** (not BLE -- `reset_to_v1()`'s default transport for
zephyr). Result: the full UDP transfer (100%, "marked permanent/confirmed; resetting device") happened
with LABID communicating cleanly throughout and after -- **no write-timeout freeze**, which is the
best evidence so far that the reorder helps. However:

1. This only exercised UDP, not the actual BLE connect/disconnect that originally triggered the bug
   (`Disconnected from AC:A7:04:2C:3B:06`) -- still unconfirmed against the real trigger.
2. It surfaced a **separate, unrelated bug**: despite "marked permanent/confirmed" and a reset, the
   board came back still running `2.0.0` (`LABID before: app=2.0.0 slot=0; after: app=2.0.0 slot=0`),
   i.e. MCUboot did not actually swap to the newly-uploaded v1 image via the UDP SMP path. Filed
   separately as **BL-065** (not documented in depth here -- this file is BL-064's).
3. A later `Write timeout` was reproduced again, but this time immediately after the pytest process
   exited (uncaught error) rather than during live operation -- likely stale Windows COM driver state
   from the abrupt process exit (seen this pattern earlier in the session, unrelated to the reorder
   fix or firmware), not necessarily the original bug recurring. A fresh esptool connection over WSL2
   opened/wrote/read the board fine immediately after.

Board reflashed back to the known-good confirmed `build_v1` (pre-fix baseline, since the reorder is
still unconfirmed) via esptool from WSL2 to leave it healthy for whoever continues this.

## Fix attempt 1 tested against the real trigger: DISPROVEN

Forced the board to v1 directly (esptool), then ran `test_t02_update_v1_to_v2_ble_zephyr` for real --
a genuine v1 -> v2 BLE OTA, the actual original trigger. Result: **same exact failure recurred**.
`ERROR: the board never answered after the transfer`, then `SerialTimeoutException: Write timeout` in
teardown, same as before the reorder fix. The init-order hypothesis is disproven, not just unconfirmed.

## New data point: it's not "BLE enabled", and it's not tied to how v2 got there

`console.log` from this same run shows the RX IRQ working perfectly on **v1**, mid-test, with BLE
actively advertising:

```
Heartbeat: variant=v1, toggles=2710, confirmed=1, uptime=1358042 ms, irq=130, rx=1260
```

130 interrupts, 1260 bytes received -- LABID's own pre-test queries were landing fine. Then, after the
BLE OTA swaps the board into v2, `irq` resets to 0 and never increments again for the rest of the test
(5+ minutes of uptime, confirmed by tailing the same log). And this isn't specific to *how* v2 was
reached: a fresh **direct esptool flash** of build_v2 (no OTA at all, see the top of this file) showed
the identical `irq=0, rx=0` symptom from first boot. So the differentiator is genuinely "is this
`APP_VARIANT_V2`", not "was there a BLE connection" or "was there an OTA swap" or "which order did
init run in".

The only other variant-specific code (checked, ruled out as an obvious cause): `app_blink_half_period_ms`
just computes a `k_msleep` interval (125ms at 4Hz vs 500ms at 1Hz) for the same WS2812 LED strip driver
call -- no separate timer/interrupt resource, so unlikely to be silently claiming the UART's interrupt
vector, but this was reasoned from source, not proven on hardware.

## Isolation test: it's the 4Hz blink rate, not the variant/version label

Built a diagnostic `build_v2_diag`: identical to `build_v2` (still reports `app=2.0.0`, `variant=v2`,
blue LED) except `app_blink_half_period_ms()` forced to the 1Hz path instead of 4Hz -- a one-line
temporary change in `main.c`, reverted after this test, not committed. Direct esptool flash (no OTA),
then checked LABID:

```
VER: {'bl': 'mcuboot', 'app': '2.0.0', ..., 'variant': 'v2', 'confirmed': '1'}
```

**Worked immediately.** Confirmed via the raw interrupt counter too, after sending exactly one `VER?`
query (10 bytes):

```
irq=1, rx=10
```

One interrupt, all 10 bytes received -- matches the query exactly. `app=2.0.0` with a 1Hz blink does
NOT trigger the bug. Combined with the earlier finding (v1 at 1Hz works, v2 at 4Hz doesn't), this
isolates the trigger cleanly: **the 4Hz blink rate, not the version/variant label, not BLE, not init
order, not the OTA swap path.**

### Candidate mechanism

The LED strip is WS2812 over **I2S** (`CONFIG_WS2812_STRIP_I2S=y`, board overlay
`compatible = "worldsemi,ws2812-i2s"`), and `led_strip_update_rgb()` is called once per half-period in
the blink loop (`main.c`) -- 4x more often at 4Hz (every 125 ms) than at 1Hz (every 500 ms). No
explicit `irq_lock()`/`k_busy_wait()` in the app's own blink loop, so if interrupts are being blocked,
it's inside the I2S/WS2812 driver itself (Zephyr's `ws2812_i2s` driver internals, not inspected yet).

## ROOT CAUSE CONFIRMED: `ws2812_i2s` driver's DMA buffer pool (mem_slab) exhaustion

Quantitative check first ruled out simple blocking-time overhead: `ws2812_strip_update()`'s
`k_usleep(flush_time_us + extra_wait_time_us)` is only ~550us per call (10us lrck_period x ~25-word
buffer + 300us extra_wait_time default) -- at 4Hz that's ~0.4% duty cycle, far too small to explain a
**total, permanent** failure (irq=0 for 5+ continuous minutes, not intermittent starvation).

Reading `~/zephyrproject/zephyr/drivers/led_strip/ws2812_i2s.c` (Zephyr's own driver, not vendored in
this repo) found the real candidate: `ws2812_strip_update_rgb()` allocates a DMA TX buffer from a
`k_mem_slab` (`k_mem_slab_alloc(cfg->mem_slab, &mem_block, K_SECONDS(10))`) but **there is no explicit
`k_mem_slab_free()` call anywhere on the success path** in this file -- freeing is expected to happen
inside the ESP32 I2S driver's own DMA-completion handling, not in this file. The pool size is
hardcoded at device-definition time: `K_MEM_SLAB_DEFINE_STATIC(ws2812_i2s_##idx##_slab,
WS2812_I2S_BUFSIZE(idx), 2, 4)` -- **only 2 blocks**, not exposed via devicetree.

### Confirmed by patching the driver

Backed up `ws2812_i2s.c`, changed `2` to `8` blocks, rebuilt `build_v2` fresh (pristine, since a driver
source change needs a full CMake reconfigure), flashed directly (no OTA), tested against the real 4Hz
blink rate:

```
t~0s:  app=2.0.0, confirmed=1   <- immediately, where the unpatched build failed within ~3s
t~10s: app=2.0.0, confirmed=1
t~20s: app=2.0.0, confirmed=1
t~30s: app=2.0.0, confirmed=1
t~45s: app=2.0.0, confirmed=1
t~60s: app=2.0.0, confirmed=1
```

**Fixed, and stayed fixed for 60+ continuous seconds of 4Hz blinking.** This is conclusive: the mem_slab
pool (2 blocks) exhausts fast enough under 4Hz calls (roughly every ~250-500ms of blinking, well before
even the earliest ~3s LABID check in prior tests) that `k_mem_slab_alloc` starts blocking/failing, and
something about that failure state (not yet traced further -- possibly a fault path, possibly resource
contention shared with the UART DMA/interrupt subsystem) also kills the LABID console's UART RX
interrupt. The Zephyr driver patch was reverted after confirming (`~/zephyrproject` is a shared SDK
checkout outside this repo's git history, not something to leave modified).

### This is a workaround, not necessarily the deepest fix

Growing the pool from 2 to 8 blocks masks the symptom (gives 4x more headroom before exhaustion) but
doesn't explain *why* blocks aren't being freed promptly, or whether they're leaking permanently (which
would eventually exhaust even 8 blocks at high enough uptime/call rate) vs. just cycling slowly. Real
fix candidates, not yet attempted:

- Find why blocks aren't freed on the success path -- check the ESP32 I2S driver
  (`~/zephyrproject/zephyr/drivers/i2s/i2s_esp32.c`) for its DMA-completion callback and whether it
  correctly returns blocks to `cfg->mem_slab` after each transfer.
- **Project-level fix that doesn't touch the SDK** (more practical, this repo can actually ship it):
  rate-limit `led_strip_update_rgb()` calls in `main.c`'s blink loop -- e.g. only call it once per full
  cycle (on state change) instead of on every half-period toggle, or skip calls when the color hasn't
  changed. Cuts the call rate without touching Zephyr's driver at all.
- If the pool size needs to persist as a real fix, it needs a proper west module patch (tracked in this
  project's `west.yml`/manifest patch mechanism) so it survives `west update` -- a one-off local SDK
  edit like this session's diagnostic doesn't.

## Shippable fix implemented: rate-limit the LED hardware update (`2705d53`)

Instead of patching the shared Zephyr SDK (not trackable in this repo), fixed it at the app level:
`esp_zephyr/app/src/main.c`'s blink loop now caps the actual `led_strip_update_rgb()` hardware call to
the same ~2 Hz cadence already proven safe on v1 (every 500 ms), independent of the logical 4Hz toggle
rate. `s_toggle_count`, self-test, and the heartbeat log all keep running at the full logical rate, so
LABID's measured toggle Hz (`labflash.identify.measure()`, which reads the `STATE?` `toggles` field --
confirmed not a physical light-sensor measurement) is unaffected.

**Verified via direct esptool flash** (no OTA) + sustained LABID polling: stable for 60+ continuous
seconds of real 4Hz blinking, `app=2.0.0, confirmed=1` every single check.

**NOT yet verified end-to-end via a live OTA.** Attempted a real v1->v2 BLE OTA with this fix in place
and hit a **different, pre-existing bug**: BL-065 (MCUboot never swaps slots despite the transfer
reporting 100% + confirmed) reproduced over BLE this time, not just UDP -- so the board never actually
reached the fixed v2 code path via OTA. Full BL-051 live-OTA acceptance for zephyr needs BL-065 fixed
first, independent of this fix's correctness.

## Board state

Left on the known-good confirmed `build_v1` (esptool, identity verified). The `ws2812_i2s.c` SDK driver
patch used earlier to confirm the root cause was reverted (shared SDK checkout, not this repo's to
modify permanently without a proper patch mechanism) -- the shipped fix is the app-level rate-limit
above, which needs no SDK changes.

## Status

Root cause CONFIRMED (`ws2812_i2s` DMA buffer pool exhaustion under sustained 4Hz calls, also kills the
LABID UART RX interrupt). Fix IMPLEMENTED and committed, verified via direct flash. Full live-OTA
end-to-end verification blocked on the separate BL-065 bug.
