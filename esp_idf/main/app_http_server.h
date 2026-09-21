/*
 * app_http_server.h — ESP-IDF HTTPS control server (/version, /ota) (BL-025).
 * Spec: PLAN §7.2.
 */
#pragma once

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Start the HTTPS control server on port 443 with /version and /ota endpoints.
 * Returns ESP_OK on success, ESP_ERR_INVALID_STATE if already running.
 */
esp_err_t app_http_server_start(void);

/*
 * Stop the HTTPS control server.
 * Returns ESP_OK on success.
 */
esp_err_t app_http_server_stop(void);

/*
 * Check if the HTTPS control server is currently running.
 */
bool app_http_server_is_running(void);

#ifdef __cplusplus
}
#endif
