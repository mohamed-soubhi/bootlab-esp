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

## Not yet tried

- Binary-search the actual trigger: build a variant that's identical to v1 except `blink_hz=4` (isolate
  the blink-rate difference specifically), and one identical to v2 except `blink_hz=1`, to see if the
  bug follows the LED rate or the `app=2.0.0`/`variant` label itself.
- Instrument `uart_irq_rx_enable()`'s return value and re-check it periodically (not just at boot) --
  if something disables RX IRQ later, the return value of a later re-enable call might reveal a
  driver-level rejection.
- Check the ESP32-S3 Zephyr HAL/driver changelog or issue tracker for known USB-Serial-JTAG RX
  interrupt erratum interactions with BLE controller or with build variant/Kconfig differences.

## Board state

Left on the known-good confirmed `build_v1` (esptool, identity verified) after this round of testing.
Session stopped here given the cost of each rebuild+flash+live-BLE-test cycle (~10 minutes, real board
time); the bug is real, reproducible, and now well-characterized, but root cause is still open.
