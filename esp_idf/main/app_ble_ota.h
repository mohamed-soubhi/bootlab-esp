/*
 * app_ble_ota.h — IDF OTA over BLE (BL-027, PLAN 7.2).
 *
 * Transport: espressif/ble_ota (NimBLE). This module supplies what the component
 * leaves to the app: the flash write into the passive OTA slot, signature
 * enforcement (esp_ota_end), and discarding a transfer that is interrupted.
 */
#ifndef APP_BLE_OTA_H
#define APP_BLE_OTA_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Start NimBLE and advertise the BLE OTA service. Call once, after WiFi init. */
esp_err_t app_ble_ota_start(void);

#ifdef __cplusplus
}
#endif

#endif /* APP_BLE_OTA_H */
