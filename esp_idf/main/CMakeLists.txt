idf_component_register(SRCS "app_main.c" "app_blink_timing.c" "app_wifi.c" "app_http_server.c" "app_ble_ota.c"
                        INCLUDE_DIRS "."
                        REQUIRES esp_system labid_port app_update esp_timer nvs_flash esp_wifi esp_event esp_netif esp_https_server esp_http_server esp_https_ota bt espressif__ble_ota
                        EMBED_TXTFILES "../../keys/server_cert.pem"
                                       "../../keys/server_key.pem"
                                       "../../keys/ca.pem")

# BL-069: link a padding blob into generated pool images only (genvariants.py passes -DGEN_PAD_FILE=<dir>/pad.bin;
# the file must be named pad.bin so the symbols are _binary_pad_bin_start/_end). Fixed variants leave it undefined.
if(DEFINED GEN_PAD_FILE)
    target_add_binary_data(${COMPONENT_LIB} "${GEN_PAD_FILE}" BINARY)
endif()
