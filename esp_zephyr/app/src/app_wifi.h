/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * app_wifi.h — Zephyr WiFi STA management + DHCPv4 (BL-035).
 */

#ifndef APP_WIFI_H_
#define APP_WIFI_H_

#include <stdbool.h>

/**
 * @brief Initialize WiFi STA mode and start connection to configured AP.
 *
 * Registers network management event handlers for WiFi connection status
 * and DHCPv4 IPv4 address assignment.
 *
 * @return 0 on success, negative errno on failure.
 */
int app_wifi_init(void);

/**
 * @brief Check if WiFi is currently connected and has an assigned IPv4 address.
 *
 * @return true if connected with valid IP, false otherwise.
 */
bool app_wifi_is_connected(void);

/**
 * @brief Get the assigned IPv4 address as a string.
 *
 * @return IPv4 string (e.g. "192.168.1.152"), or "0.0.0.0" if not acquired.
 */
const char *app_wifi_get_ip_str(void);

#endif /* APP_WIFI_H_ */
