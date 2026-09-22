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

## Not yet found

Root cause in the source. Suspect: BLE+WiFi coexistence init (BL-035, `app_ble_smp.c`/`app_wifi.c`)
either fails to register the console UART RX IRQ on this build, or claims/disables it after
`labid_port`'s own init runs (`labid_port: LABID initialized on console (irq RX, ANNOUNCE in 1500 ms)`
does print at boot -- so registration is *attempted* -- but the IRQ apparently never actually fires
once BLE is running).

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
