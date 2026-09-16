# BL-002 — ESP-IDF build proof (esp32s3)

Date: 2026-09-16

Command:
  cd ~/tools/esp-idf/examples/get-started/hello_world
  . ~/tools/esp-idf/export.sh && idf.py set-target esp32s3 && idf.py build

Verified:
- ESP-IDF v6.0.3 (git describe --tags confirms)
- xtensa-esp32s3 toolchain installed via ./install.sh esp32s3
- idf.py --version -> "ESP-IDF v6.0.3"
- hello_world.bin built (0x23890 bytes, 86% free in app partition)

Result: BUILD SUCCESS (exit 0). No flashing performed.

Key build tail:
  hello_world.bin binary size 0x23890 bytes. Smallest app partition is 0x100000 bytes.
  0xdc770 bytes (86%) free.
  Project build complete. To flash, run: idf.py flash
