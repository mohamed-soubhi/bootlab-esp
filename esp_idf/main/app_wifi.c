/*
 * app_wifi.c — WiFi connection & NVS credentials module (BL-024).
 *
 * Reads WiFi credentials (ssid, psk) and bearer token from NVS namespace "lab".
 * Connects in STA mode if provisioned; remains dormant if unprovisioned.
 *
 * NEVER logs or prints credentials (AC2).
 */
#include "app_wifi.h"

#include <string.h>

#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "app_wifi";

static bool s_connected = false;
static char s_ip_str[16] = {0};
static char s_token[64] = {0};

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_connected = false;
        s_ip_str[0] = '\0';
        ESP_LOGW(TAG, "WiFi disconnected, reconnecting...");
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)data;
        esp_ip4addr_ntoa(&event->ip_info.ip, s_ip_str, sizeof(s_ip_str));
        s_connected = true;
        ESP_LOGI(TAG, "WiFi connected: IP=%s", s_ip_str);
    }
}

esp_err_t app_wifi_init(void)
{
    /* 1. Initialize NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS flash init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    /* 2. Check namespace "lab" */
    nvs_handle_t nvs;
    ret = nvs_open("lab", NVS_READONLY, &nvs);
    if (ret != ESP_OK) {
        ESP_LOGI(TAG, "WiFi unprovisioned: NVS namespace 'lab' not found");
        return ESP_OK;
    }

    /* 3. Read SSID */
    char ssid[33] = {0};
    size_t ssid_len = sizeof(ssid);
    ret = nvs_get_str(nvs, "ssid", ssid, &ssid_len);
    if (ret != ESP_OK || ssid_len == 0 || ssid[0] == '\0') {
        ESP_LOGI(TAG, "WiFi unprovisioned: no 'ssid' in NVS");
        nvs_close(nvs);
        return ESP_OK;
    }

    /* 4. Read PSK (optional, empty for open networks) */
    char psk[65] = {0};
    size_t psk_len = sizeof(psk);
    nvs_get_str(nvs, "psk", psk, &psk_len);

    /* 5. Read bearer token (for BL-025 / BL-026 HTTP OTA) */
    size_t token_len = sizeof(s_token);
    nvs_get_str(nvs, "token", s_token, &token_len);
    nvs_close(nvs);

    /* 6. Initialize TCP/IP and WiFi stack */
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_cfg = {0};
    strlcpy((char *)wifi_cfg.sta.ssid, ssid, sizeof(wifi_cfg.sta.ssid));
    strlcpy((char *)wifi_cfg.sta.password, psk, sizeof(wifi_cfg.sta.password));
    if (strlen(psk) > 0) {
        wifi_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    } else {
        wifi_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "WiFi STA initialized, connecting...");

    /* Wipe sensitive credentials from stack */
    memset(psk, 0, sizeof(psk));
    memset(&wifi_cfg, 0, sizeof(wifi_cfg));
    return ESP_OK;
}

bool app_wifi_is_connected(void)
{
    return s_connected;
}

esp_err_t app_wifi_get_ip_str(char *buf, size_t maxlen)
{
    if (!s_connected || s_ip_str[0] == '\0') {
        return ESP_ERR_INVALID_STATE;
    }
    strlcpy(buf, s_ip_str, maxlen);
    return ESP_OK;
}

const char *app_wifi_get_token(void)
{
    return s_token[0] != '\0' ? s_token : NULL;
}
