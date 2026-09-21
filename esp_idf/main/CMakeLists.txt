idf_component_register(SRCS "app_main.c" "app_blink_timing.c" "app_wifi.c"
                        INCLUDE_DIRS "."
                        REQUIRES esp_system labid_port app_update esp_timer nvs_flash esp_wifi esp_event esp_netif)
