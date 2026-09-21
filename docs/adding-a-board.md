# Adding a Board to bootlab-esp

This guide documents the step-by-step procedure for adding, characterizing, provisioning, and validating a new physical ESP32-S3 board in the bootlab-esp rig.

---

## 1. Characterize Hardware & Safety Backup

> [!CAUTION]
> Always take a full 16 MB raw flash backup and eFuse summary **before** writing any firmware to a new board. Store backups exclusively in `backups/` (`chmod 700`).

1. Connect the board via USB and read chip info and MAC address:
   ```bash
   esptool --chip esp32s3 chip-id
   ```
   Note the MAC address (e.g. `e0:72:a1:aa:23:90`), which becomes the USB serial (`E0:72:A1:AA:23:90`) and UID (`E072A1AA2390`).

2. Detect flash and PSRAM parameters:
   ```bash
   esptool --chip esp32s3 flash-id
   ```

3. Read raw 16 MB flash backup and generate SHA-256 checksum:
   ```bash
   mkdir -p backups && chmod 700 backups
   esptool --chip esp32s3 read-flash 0x0 0x1000000 backups/esp_<MAC_UPPER>.bin
   sha256sum backups/esp_<MAC_UPPER>.bin > backups/esp_<MAC_UPPER>.sha256
   chmod 600 backups/esp_<MAC_UPPER>.*
   ```

4. Capture read-only eFuse snapshot:
   ```bash
   espefuse.py summary > backups/efuse_<MAC_UPPER>.txt
   chmod 600 backups/efuse_<MAC_UPPER>.txt
   ```

---

## 2. Configure Rig & Udev Symlink

1. **Udev Rule (`host/udev/`):**
   Add a udev rule matching the board's unique USB serial:
   ```udev
   SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", ATTRS{idProduct}=="1001", ATTRS{serial}=="<MAC_UPPER>", SYMLINK+="lab-esp-<board>", MODE="0666"
   ```
   Reload rules:
   ```bash
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```

2. **Rig Configuration (`host/config/rig.yaml`):**
   Add the new board configuration block under `boards:`:
   ```yaml
   boards:
     <board_key>:
       board_name: lab-esp-<board_key>
       mcu: esp32s3
       hw: esp32s3_devkitc
       usb_serial: "<MAC_UPPER_COLONS>"
       dev_symlink: /dev/lab-esp-<board_key>
       mac: "<MAC_LOWER_COLONS>"
       flash_mb: 16
       flash_mode: quad
       psram_mb: 8
       psram_mode: octal
       rev: v0.2
       secure_boot: off
       flash_encryption: off
       led_gpio: 48
       led_strip: worldsemi_ws2812
   ```

---

## 3. Build & Factory Provision

1. **Build all 5 variants with isolated build dirs (PLAN R15):**
   ```bash
   python3 -m labflash build <board_key>
   ```

2. **Factory flash with pre-write identity verification (BL-042):**
   ```bash
   python3 -m labflash flash <board_key>
   ```

3. **Provision WiFi and OTA bearer tokens into NVS (BL-024 / BL-042):**
   ```bash
   python3 -m labflash provision <board_key> --env-file credentials.env
   ```

---

## 4. Run HIL Acceptance & Diagnostics

1. **Query Board Identity & State:**
   ```bash
   python3 -m labflash identify
   python3 -m labflash info <board_key>
   python3 -m labflash measure <board_key> --expect-hz 1.0
   ```

2. **Execute HIL Test Suite:**
   ```bash
   PYTHONPATH="host:." pytest tests_hil -m "<board_key>" -v
   ```
