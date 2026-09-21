# BL-022 — ESP-IDF glue for the LABID protocol. The portable parser/dispatcher
# live in the shared `labid` component (common/labid); this adds the
# USB-Serial-JTAG transport and the ESP-IDF providers.
idf_component_register(
    SRCS "labid_port.c"
    INCLUDE_DIRS "include"
    REQUIRES labid
    PRIV_REQUIRES esp_driver_usb_serial_jtag esp_app_format esp_bootloader_format
                  app_update esp_system esp_hw_support esp_timer spi_flash
                  esp_partition esp_common
)
