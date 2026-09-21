idf_component_register(SRCS "app_main.c" "app_blink_timing.c" "app_wifi.c" "app_http_server.c" "app_ble_ota.c"
                        INCLUDE_DIRS "."
                        REQUIRES esp_system labid_port app_update esp_timer nvs_flash esp_wifi esp_event esp_netif esp_https_server esp_http_server esp_https_ota bt espressif__ble_ota
                        EMBED_TXTFILES "../../keys/server_cert.pem"
                                       "../../keys/server_key.pem"
                                       "../../keys/ca.pem")


