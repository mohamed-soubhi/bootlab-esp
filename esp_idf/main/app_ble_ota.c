/*
 * app_ble_ota.c — IDF OTA over BLE (BL-027, PLAN 7.2).
 *
 * espressif/ble_ota (NimBLE) delivers the image as 4096-byte sectors to
 * on_sector(). This module writes them to the passive OTA slot and only
 * activates that slot after esp_ota_end() has verified the image, including the
 * RSA signature (CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT) -- the same trust as
 * the WiFi OTA. A partial, corrupt or badly signed image can therefore never
 * become bootable. A BLE disconnect discards a half-received image at once.
 */
#include "app_ble_ota.h"

#include <stdbool.h>
#include <string.h>

#include "ble_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "host/ble_gap.h"

static const char *TAG = "app_ble_ota";

#define RESTART_DELAY_US (1000 * 1000)   /* lets the last sector's ACK go out first */

static struct {
    esp_ota_handle_t handle;
    const esp_partition_t *part;
    uint32_t written;
    bool active;
} s_ota;

static struct ble_gap_event_listener s_gap_listener;
static esp_timer_handle_t s_restart_timer;

/* espressif/ble_ota links against an app-owned lock, taken around its STOP-command
 * state reset (nimble_ota.c). It must exist before the first STOP or the board
 * would fault on xSemaphoreTake(NULL). The name and linkage are fixed by the component. */
SemaphoreHandle_t notify_sem;

static void ota_reset(void)
{
    memset(&s_ota, 0, sizeof s_ota);
}

static void ota_abort(const char *why)
{
    if (s_ota.active) {
        ESP_LOGW(TAG, "BLE OTA aborted (%s) after %u bytes; partial image discarded",
                 why, (unsigned)s_ota.written);
        esp_ota_abort(s_ota.handle);
    }
    ota_reset();
}

static bool ota_begin(uint32_t fw_len)
{
    s_ota.part = esp_ota_get_next_update_partition(NULL);
    if (s_ota.part == NULL || fw_len == 0 || fw_len > s_ota.part->size) {
        ESP_LOGE(TAG, "BLE OTA rejected: fw_len=%u, slot size=%u", (unsigned)fw_len,
                 s_ota.part ? (unsigned)s_ota.part->size : 0u);
        ota_reset();
        return false;
    }
    /* Sequential writes: erase as we go, so begin returns at once. */
    esp_err_t err = esp_ota_begin(s_ota.part, OTA_WITH_SEQUENTIAL_WRITES, &s_ota.handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_begin failed: %s", esp_err_to_name(err));
        ota_reset();
        return false;
    }
    s_ota.active = true;
    s_ota.written = 0;
    ESP_LOGI(TAG, "BLE OTA started: %u bytes into %s @0x%x", (unsigned)fw_len,
             s_ota.part->label, (unsigned)s_ota.part->address);
    return true;
}

static void restart_cb(void *arg)
{
    (void)arg;
    esp_restart();
}

static void ota_finish(void)
{
    /* Verifies the image checksum and the RSA signature. */
    esp_err_t err = esp_ota_end(s_ota.handle);
    s_ota.active = false;   /* the handle is consumed either way */
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "BLE OTA image failed verification: %s", esp_err_to_name(err));
        ota_reset();
        return;
    }
    err = esp_ota_set_boot_partition(s_ota.part);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_set_boot_partition failed: %s", esp_err_to_name(err));
        ota_reset();
        return;
    }
    ESP_LOGI(TAG, "BLE OTA verification successful! Rebooting in 1s...");
    ota_reset();
    (void)esp_timer_start_once(s_restart_timer, RESTART_DELAY_US);
}

/* Called by ble_ota once per received sector (<= 4096 bytes), in the NimBLE host task. */
static void on_sector(uint8_t *buf, uint32_t len)
{
    const uint32_t fw_len = esp_ble_ota_get_fw_length();

    if (!s_ota.active && !ota_begin(fw_len)) {
        return;
    }
    esp_err_t err = esp_ota_write(s_ota.handle, buf, len);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_ota_write failed: %s", esp_err_to_name(err));
        ota_abort("flash write failed");
        return;
    }
    s_ota.written += len;
    if (s_ota.written >= fw_len) {
        ota_finish();
    }
}

static int gap_listener_cb(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    if (event->type == BLE_GAP_EVENT_DISCONNECT) {
        ota_abort("BLE disconnected");
    }
    return 0;
}

esp_err_t app_ble_ota_start(void)
{
    notify_sem = xSemaphoreCreateMutex();
    if (notify_sem == NULL) {
        return ESP_ERR_NO_MEM;
    }
    const esp_timer_create_args_t timer_args = { .callback = restart_cb, .name = "ble_ota_restart" };
    esp_err_t err = esp_timer_create(&timer_args, &s_restart_timer);
    if (err != ESP_OK) {
        return err;
    }
    (void)esp_ble_ota_recv_fw_data_callback(on_sector);
    err = esp_ble_ota_host_init();
    if (err != ESP_OK) {
        return err;
    }
    int rc = ble_gap_event_listener_register(&s_gap_listener, gap_listener_cb, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "disconnect listener registration failed: rc=%d", rc);
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "BLE OTA service up (GATT service 0x8018)");
    return ESP_OK;
}
