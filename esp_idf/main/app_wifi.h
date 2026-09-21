#pragma once

#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Initialize NVS, read WiFi credentials & bearer token from namespace "lab",
 * and connect to the AP if provisioned.
 * Non-blocking: event-driven via the default ESP event loop.
 */
esp_err_t app_wifi_init(void);

/* Check if WiFi is currently connected with a valid IP. */
bool app_wifi_is_connected(void);

/* Get current IP address string (e.g. "192.168.1.100").
 * Returns ESP_OK on success, or ESP_ERR_INVALID_STATE if not connected. */
esp_err_t app_wifi_get_ip_str(char *buf, size_t maxlen);

/* Get the bearer token read from NVS.
 * Returns pointer to token string, or NULL if unprovisioned. */
const char *app_wifi_get_token(void);

#ifdef __cplusplus
}
#endif
