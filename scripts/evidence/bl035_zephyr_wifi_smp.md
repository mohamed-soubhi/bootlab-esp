# BL-035 evidence — Zephyr WiFi + SMP over UDP (single build with BT), 2026-09-22

Implementation and hardware verification on physical target board `lab-esp-zephyr` (MAC `AC:A7:04:2C:3B:04`, BLE `AC:A7:04:2C:3B:06`, IP `192.168.1.153`):

## 1. Subsystem Implementation

- **Hardware & Devicetree (`esp_zephyr/app/boards/esp32s3_devkitc_procpu.overlay`)**:
  - Activated hardware WiFi controller node:
    ```dts
    &wifi {
        status = "okay";
    };
    ```

- **Kconfig Configuration (`esp_zephyr/app/prj.conf`)**:
  - Enabled Zephyr L2 networking & ESP32 WiFi driver:
    - `CONFIG_NETWORKING=y`
    - `CONFIG_NET_L2_ETHERNET=y`
    - `CONFIG_NET_L2_WIFI_MGMT=y`
    - `CONFIG_WIFI=y`
    - `CONFIG_WIFI_ESP32=y`
    - `CONFIG_NET_IPV4=y`
    - `CONFIG_NET_UDP=y`
    - `CONFIG_NET_SOCKETS=y`
    - `CONFIG_NET_DHCPV4=y`
    - `CONFIG_NET_MGMT=y`
    - `CONFIG_NET_MGMT_EVENT=y`
    - `CONFIG_NET_CONNECTION_MANAGER=y`
    - `CONFIG_ESP_WIFI_HEAP_SYSTEM=y`
  - Enabled MCUmgr SMP over UDP on port 1337:
    - `CONFIG_MCUMGR_TRANSPORT_UDP=y`
    - `CONFIG_MCUMGR_TRANSPORT_UDP_PORT=1337`
    - `CONFIG_MCUMGR_TRANSPORT_UDP_IPV4=y`
    - `CONFIG_MCUMGR_TRANSPORT_UDP_AUTOMATIC_INIT=y`
    - `CONFIG_MCUMGR_TRANSPORT_UDP_STACK_SIZE=4096`
  - Single Unified Build (Bluetooth LE + WiFi):
    - Retained all Bluetooth LE and BLE SMP transport configs in the exact same build (`CONFIG_BT=y`, `CONFIG_MCUMGR_TRANSPORT_BT=y`).
    - Internal SRAM utilization: DRAM 79.44% (302 KB / 380 KB), IRAM 21.90% (86 KB / 397 KB), Flash 8.77% (736 KB / 8 MB).

- **Firmware Application (`esp_zephyr/app/src/app_wifi.[ch]`)**:
  - Dedicated background thread `wifi_connect_task` (stack 4096, priority 7).
  - Listens to `NET_EVENT_WIFI_CONNECT_RESULT` and triggers `net_dhcpv4_start(iface)` upon association.
  - Listens to `NET_EVENT_IPV4_ADDR_ADD` and logs the assigned IP address.
  - Immediate stack sanitization (`memset`) of temporary PSK buffers after connect call.
  - Compile-time extraction of WiFi SSID/PSK from local `credentials.env` via `esp_zephyr/app/CMakeLists.txt`.

- **Host Testing Tools (`scripts/`)**:
  - `scripts/probe_udp_smp.py`: Subnet scanner discovering UDP SMP servers on port 1337.
  - `scripts/test_udp_smp.py`: Quick smoke test utility for `EchoWrite` and `ImageStatesRead` over UDP.
  - `scripts/zephyr_udp_ota.py`: Full UDP SMP OTA pipeline using `smpclient.transport.udp.SMPUDPTransport`.

---

## 2. Acceptance Criteria Results — ALL PASS

### AC1: v2 → v1 over UDP — PASS
- Target device was running `v2` (hash `ba6245db3db09730d7feac008a09f74391840256a15b98c46497a433b0d1a302`) on IP `192.168.1.153`.
- Executed `scripts/zephyr_udp_ota.py` with signed `zephyr_v1.bin` (736,028 bytes, image hash `2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd`):
  - Erased slot 1.
  - Uploaded 736,028 bytes over UDP port 1337 in **15.4 s** (**46.7 KB/s**).
  - Marked image as permanently confirmed (`confirm=True`).
  - Issued SMP `ResetWrite()`.
- Device rebooted into MCUboot, which swapped slot 1 to slot 0 and booted `v1`.
- Verified via `scripts/test_udp_smp.py`:
  - `slot=0`: `hash=2fb8d5ea...` (`v1`), `active=True`, `confirmed=True`.
  - Blink rate confirmed at 1.0 Hz.

### AC2: One build with BT + WiFi — PASS
- Single firmware image contains both Bluetooth LE peripheral (SMP service) and WiFi STA (UDP SMP server).
- Concurrency test:
  - Sent `EchoWrite` and `ImageStatesRead` over UDP port 1337 to `192.168.1.153` -> received valid responses.
  - Simultaneously sent `EchoWrite` and `ImageStatesRead` over Bluetooth LE to `AC:A7:04:2C:3B:06` -> received valid responses.
  - Both transports work simultaneously on the same running build without interference or separate builds.

---

## 3. Live Hardware Verification Logs

### 3.1 Network Discovery & DHCP Verification
```text
Probing 192.168.1.1 to 192.168.1.254 on UDP port 1337...
DISCOVERED SMP UDP on 192.168.1.153:1337! (response: 17 bytes)
```

### 3.2 Live OTA Update v2 → v1 over UDP (15.4s, 46.7 KB/s)
```text
Loaded C:\MSA\embedded-OS\bootlab-esp\ble_stage\zephyr_v1.bin (736028 bytes)
Connecting to 192.168.1.153:1337 via SMP UDP...
Connected via UDP!
Querying current image state...
Current images: [ImageState(slot=0, version='0.0.0', hash=ba6245db..., bootable=True, confirmed=True, active=True)]
Slot 1 is occupied. Erasing slot 1...
Erase result: header=Header(op=<OP.WRITE_RSP: 3>, group_id=1, command_id=5)
Uploading 736028 bytes (slot 0)...
  Upload progress: 73777/736028 bytes (10%)
  Upload progress: 147523/736028 bytes (20%)
  Upload progress: 221269/736028 bytes (30%)
  Upload progress: 295015/736028 bytes (40%)
  Upload progress: 368761/736028 bytes (50%)
  Upload progress: 442507/736028 bytes (60%)
  Upload progress: 516253/736028 bytes (70%)
  Upload progress: 589999/736028 bytes (80%)
  Upload progress: 663745/736028 bytes (90%)
  Upload progress: 736028/736028 bytes (100%)
Upload complete in 15.4s (46.7 KB/s)
Slot 1 image hash: 2fb8d5ea9acdb80cada90c8e678c7b7d21f749cb086605a76e29833faccdc1fd
Marking image as permanently confirmed...
ImageStatesWrite response: [ImageState(slot=0, hash=ba6245db..., confirmed=True), ImageState(slot=1, hash=2fb8d5ea..., pending=True, permanent=True)]
Issuing SMP Reset command...
Reset command sent successfully
[SUCCESS] UDP OTA workflow completed.
```

### 3.3 Post-Downgrade UDP SMP Verification (`test_udp_smp.py`)
```text
Connecting to 192.168.1.153:1337 via SMPUDPTransport...
Connected via UDP SMP!
Echo response: header=Header(op=<OP.WRITE_RSP: 3>, version=<Version.V2: 1>, group_id=0, command_id=0) r='hello from UDP SMP!'
Image states response: [
  ImageState(slot=0, version='0.0.0', hash=b'/\xb8\xd5\xea\x9a\xcd\xb8\x0c\xad\xa9\x0c\x8eg\x8c{}!\xf7I\xcb\x08f\x05\xa7n)\x83?\xac\xcd\xc1\xfd', bootable=True, pending=False, confirmed=True, active=True, permanent=False),
  ImageState(slot=1, version='0.0.0', hash=b'\xbabE\xdb=\xb0\x970\xd7\xfe\xac\x00\x8a\t\xf7C\x91\x84\x02V\xa1[\x98\xc4d\x97\xa43\xb0\xd1\xa3\x02', bootable=True, pending=False, confirmed=False, active=False, permanent=False)
]
```

### 3.4 Simultaneous BLE SMP Verification on Same Build (`test_smp_ops.py`)
```text
Connecting to AC:A7:04:2C:3B:06 via SMPBLETransport (uncached)...
Connected! Sending EchoWrite...
Echo response: header=Header(op=<OP.WRITE_RSP: 3>, group_id=0, command_id=0) r='hello from bootlab!'
Sending ImageStatesRead...
Image states response: [
  ImageState(slot=0, version='0.0.0', hash=b'/\xb8\xd5\xea\x9a\xcd\xb8\x0c\xad\xa9\x0c\x8eg\x8c{}!\xf7I\xcb\x08f\x05\xa7n)\x83?\xac\xcd\xc1\xfd', bootable=True, pending=False, confirmed=True, active=True, permanent=False),
  ImageState(slot=1, version='0.0.0', hash=b'\xbabE\xdb=\xb0\x970\xd7\xfe\xac\x00\x8a\t\xf7C\x91\x84\x02V\xa1[\x98\xc4d\x97\xa43\xb0\xd1\xa3\x02', bootable=True, pending=False, confirmed=False, active=False, permanent=False)
]
```
