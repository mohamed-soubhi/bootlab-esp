# BL-003 AC3 — WSL2 host observation (2026-09-20)

This is a **separate, later observation on a different host** than
`bl003_ac3_observation.jsonl` (RPi4, 2026-09-17). It does not overwrite or
contradict that finding. The RPi4's AC3 failure (continuous under-voltage,
`get_throttled=0x50000`, rate independent of attached peripherals —
PSU/rail fault) remains a separate, still-valid historical finding for
that specific hardware.

Work migrated to a WSL2 host (Windows, boards attached via `usbipd attach
--wsl`) after the RPi4 PSU fault was deemed unfixable without new hardware.

## Run 1 — FAIL (root cause identified)

Window: 2026-09-20T02:03:38+02:00 → 02:13:39+02:00 (10 min, 15s sampling)

```
02:03:38  ttyACM0=present ttyACM1=present
... (7 samples clean) ...
02:05:23  ttyACM0=MISSING ttyACM1=MISSING
... (stayed MISSING for remaining ~8m15s) ...
end=02:13:39 disconnect_samples=33
```

`dmesg` at the drop:
```
[59170.506931] vhci_hcd: connection closed
[59170.506963] vhci_hcd: connection closed
[59170.507232] vhci_hcd: stop threads / release socket
[59170.507300] vhci_hcd: disconnect device -> usb 1-1 (ttyACM0)
[59170.507785] vhci_hcd: stop threads / release socket
[59170.507800] vhci_hcd: disconnect device -> usb 1-2 (ttyACM1)
```
Both boards dropped in the same instant via the USB/IP virtual host
controller — a Windows-side `usbipd` bridge disconnect, not two
independent per-board faults, and structurally cannot be a PSU brown-out
(boards are USB-powered from the Windows host in this chain, no RPi4 rail
involved).

Root cause found by the owner: Windows USB selective suspend was still
active under HP's custom power plan (the plan hid the standard GUI
toggle); fixed via `powercfg` at the registry level directly, both AC/DC
verified `0x00000000`.

## Run 2 — PASS (post-fix, full 10 minutes, zero drops)

Window: 2026-09-20T03:11:57+02:00 → 03:21:57+02:00 (10 min, 15s sampling,
41 samples)

```
03:11:57 ttyACM0=present ttyACM1=present
03:12:12 ttyACM0=present ttyACM1=present
... (unbroken through the full window) ...
03:21:42 ttyACM0=present ttyACM1=present
end=03:21:57 disconnect_samples=0
```

`dmesg` for the full window: no `USB disconnect`, no `disconnect device`,
no re-enumeration. The only traffic logged was a burst of
`vhci_hcd: unlink->seqnum ... urb->status -104` at uptime 63148s (~64s
after attach) — coincides exactly with a read-only `esptool chip-id`
query (URB cleanup on a clean serial-session close), not a device-level
disconnect; no `disconnect device` line follows it.

## AC2 — port-swap verification (2026-09-20, same session)

Boards physically swapped between USB ports on the Windows host, then
reattached via `usbipd attach --wsl --busid 6-3` / `--busid 7-4`.

```
/dev/lab-esp-zephyr -> esptool chip-id -> MAC ac:a7:04:2c:3b:04  (correct)
/dev/lab-esp-idf     -> esptool chip-id -> MAC e0:72:a1:aa:23:90  (correct)

udevadm info -q property -n /dev/lab-esp-zephyr | grep ID_SERIAL_SHORT
  ID_SERIAL_SHORT=AC:A7:04:2C:3B:04
udevadm info -q property -n /dev/lab-esp-idf | grep ID_SERIAL_SHORT
  ID_SERIAL_SHORT=E0:72:A1:AA:23:90
```
Symlinks resolved to the correct board by MAC/serial across the physical
port change (the udev rule matches on `ATTRS{serial}`, not port/bus path).

## Conclusion (WSL2 host, this session only)

- AC1: PASS — `/dev/lab-esp-zephyr` and `/dev/lab-esp-idf` exist, correctly mapped.
- AC2: PASS — verified across a real physical port swap, cross-checked via esptool chip-id and udevadm.
- AC3: PASS — 10-minute clean run, 0 drops, after fixing the actual root cause (Windows USB selective suspend).

This applies to the WSL2 host only. See `bl003_ac3_observation.jsonl` for the RPi4's separate, unrelated PSU/rail fault finding.
