/*
 * app_http_server.c — ESP-IDF HTTPS control server (/version, /ota) (BL-025).
 *
 * Implements:
 *   GET  /version -> JSON {app, git, slot, confirmed} (matches LABID VER)
 *   POST /ota     -> Bearer token auth -> 202 Accepted {status: "accepted"}
 *                    Wrong/missing token -> 401 Unauthorized
 *
 * Spec: PLAN §7.2.
 */
#include "app_http_server.h"

#include <stdio.h>
#include <string.h>
#include "esp_app_desc.h"
#include "esp_https_server.h"
#include "esp_log.h"
#include "esp_ota_ops.h"

#include "app_wifi.h"

static const char *TAG = "app_https";

/* Embedded TLS certificates and keys from keys/ directory */
extern const unsigned char server_cert_pem_start[] asm("_binary_server_cert_pem_start");
extern const unsigned char server_cert_pem_end[]   asm("_binary_server_cert_pem_end");

extern const unsigned char server_key_pem_start[]  asm("_binary_server_key_pem_start");
extern const unsigned char server_key_pem_end[]    asm("_binary_server_key_pem_end");

extern const unsigned char ca_pem_start[]          asm("_binary_ca_pem_start");
extern const unsigned char ca_pem_end[]            asm("_binary_ca_pem_end");

/* App confirmed state from app_main.c (BL-023 health task) */
extern bool app_is_confirmed(void);

static httpd_handle_t s_server = NULL;

const char *app_get_ca_cert_pem(size_t *len)
{
    if (len) {
        *len = (size_t)(ca_pem_end - ca_pem_start);
    }
    return (const char *)ca_pem_start;
}

static bool check_bearer_token(httpd_req_t *req)
{
    const char *expected_token = app_wifi_get_token();
    if (!expected_token || expected_token[0] == '\0') {
        ESP_LOGW(TAG, "Auth failed: no token provisioned in NVS");
        return false;
    }

    char auth_hdr[128] = {0};
    if (httpd_req_get_hdr_value_str(req, "Authorization", auth_hdr, sizeof(auth_hdr)) != ESP_OK) {
        ESP_LOGW(TAG, "Auth failed: missing Authorization header");
        return false;
    }

    const char bearer_prefix[] = "Bearer ";
    size_t prefix_len = sizeof(bearer_prefix) - 1;
    if (strncmp(auth_hdr, bearer_prefix, prefix_len) != 0) {
        ESP_LOGW(TAG, "Auth failed: Authorization header is not Bearer");
        return false;
    }

    const char *token = auth_hdr + prefix_len;
    while (*token == ' ') {
        token++;
    }

    if (strcmp(token, expected_token) != 0) {
        ESP_LOGW(TAG, "Auth failed: token mismatch");
        return false;
    }

    return true;
}

static esp_err_t send_unauthorized(httpd_req_t *req)
{
    httpd_resp_set_status(req, "401 Unauthorized");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "WWW-Authenticate", "Bearer");
    return httpd_resp_send(req, "{\"error\":\"unauthorized\"}", HTTPD_RESP_USE_STRLEN);
}

/* Extract a string field from simple JSON: {"key": "value"} */
static bool extract_json_str(const char *json, const char *key, char *out, size_t maxlen)
{
    char search[40];
    snprintf(search, sizeof(search), "\"%s\"", key);
    const char *p = strstr(json, search);
    if (!p) {
        return false;
    }
    p += strlen(search);
    while (*p == ' ' || *p == ':' || *p == '\t' || *p == '\r' || *p == '\n') {
        p++;
    }
    if (*p != '"') {
        return false;
    }
    p++; /* skip opening quote */
    size_t i = 0;
    while (*p && *p != '"' && i < maxlen - 1) {
        if (*p == '\\' && *(p + 1)) {
            p++; /* skip escape character */
        }
        out[i++] = *p++;
    }
    out[i] = '\0';
    return (*p == '"');
}

/*
 * GET /version — Returns JSON {app, git, slot, confirmed}.
 * Matches LABID VER.app and running image state.
 */
static esp_err_t version_get_handler(httpd_req_t *req)
{
    const esp_app_desc_t *app = esp_app_get_description();
    const esp_partition_t *run = esp_ota_get_running_partition();

    char git[8] = {0};
    strncpy(git, app->version, 7);
    git[7] = '\0';

    int slot = (run && run->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_1) ? 1 : 0;

    bool confirmed = app_is_confirmed();
    if (run) {
        esp_ota_img_states_t ota_state;
        if (esp_ota_get_state_partition(run, &ota_state) == ESP_OK) {
            if (ota_state == ESP_OTA_IMG_NEW || ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
                confirmed = false;
            }
        }
    }

    char resp[160];
    int len = snprintf(resp, sizeof(resp),
                       "{\"app\":\"%s\",\"git\":\"%s\",\"slot\":%d,\"confirmed\":%s}",
                       app->version, git, slot, confirmed ? "true" : "false");

    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, resp, len);
}

#include "esp_https_ota.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static bool s_ota_in_progress = false;

static void ota_task(void *pvParameter)
{
    char *url = (char *)pvParameter;
    ESP_LOGI(TAG, "Starting OTA pull from %s", url);

    esp_http_client_config_t http_config = {
        .url = url,
        .cert_pem = (const char *)ca_pem_start,
        .timeout_ms = 15000,
        .keep_alive_enable = true,
        .skip_cert_common_name_check = true,
    };
    esp_https_ota_config_t ota_config = {
        .http_config = &http_config,
    };

    esp_err_t ret = esp_https_ota(&ota_config);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "OTA pull and verification successful! Rebooting in 1s...");
        free(url);
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    } else {
        ESP_LOGE(TAG, "OTA failed: %s (0x%x)", esp_err_to_name(ret), ret);
        free(url);
        s_ota_in_progress = false;
        vTaskDelete(NULL);
    }
}

/*
 * POST /ota — Protected endpoint. Requires Authorization: Bearer <token>.
 * Body: {"url": "...", "version": "..."}
 * Returns: 202 Accepted on success, 401 Unauthorized on bad token.
 */
static esp_err_t ota_post_handler(httpd_req_t *req)
{
    if (!check_bearer_token(req)) {
        return send_unauthorized(req);
    }

    if (s_ota_in_progress) {
        httpd_resp_set_status(req, "409 Conflict");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_send(req, "{\"error\":\"ota in progress\"}", HTTPD_RESP_USE_STRLEN);
    }

    int total_len = req->content_len;
    if (total_len <= 0 || total_len > 1024) {
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_send(req, "{\"error\":\"invalid content length\"}", HTTPD_RESP_USE_STRLEN);
    }

    char buf[1025] = {0};
    int cur_len = 0;
    while (cur_len < total_len) {
        int received = httpd_req_recv(req, buf + cur_len, total_len - cur_len);
        if (received <= 0) {
            if (received == HTTPD_SOCK_ERR_TIMEOUT) {
                continue;
            }
            httpd_resp_send_500(req);
            return ESP_FAIL;
        }
        cur_len += received;
    }
    buf[total_len] = '\0';

    char url[256] = {0};
    char version[32] = {0};
    if (!extract_json_str(buf, "url", url, sizeof(url)) ||
        !extract_json_str(buf, "version", version, sizeof(version))) {
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_send(req, "{\"error\":\"missing url or version\"}", HTTPD_RESP_USE_STRLEN);
    }

    char *url_copy = strdup(url);
    if (!url_copy) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    s_ota_in_progress = true;
    BaseType_t task_ret = xTaskCreate(ota_task, "ota_task", 10240, url_copy, 5, NULL);
    if (task_ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create OTA task");
        free(url_copy);
        s_ota_in_progress = false;
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "OTA requested: url=%s, version=%s, task created", url, version);

    httpd_resp_set_status(req, "202 Accepted");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, "{\"status\":\"accepted\"}", HTTPD_RESP_USE_STRLEN);
}

static const httpd_uri_t uri_version = {
    .uri      = "/version",
    .method   = HTTP_GET,
    .handler  = version_get_handler,
    .user_ctx = NULL
};

static const httpd_uri_t uri_ota = {
    .uri      = "/ota",
    .method   = HTTP_POST,
    .handler  = ota_post_handler,
    .user_ctx = NULL
};

esp_err_t app_http_server_start(void)
{
    if (s_server != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    httpd_ssl_config_t conf = HTTPD_SSL_CONFIG_DEFAULT();
    conf.servercert = server_cert_pem_start;
    conf.servercert_len = (size_t)(server_cert_pem_end - server_cert_pem_start);
    conf.prvtkey_pem = server_key_pem_start;
    conf.prvtkey_len = (size_t)(server_key_pem_end - server_key_pem_start);
    conf.port_secure = 443;
    conf.httpd.stack_size = 10240;

    esp_err_t ret = httpd_ssl_start(&s_server, &conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTPS server: %s", esp_err_to_name(ret));
        return ret;
    }

    httpd_register_uri_handler(s_server, &uri_version);
    httpd_register_uri_handler(s_server, &uri_ota);
    ESP_LOGI(TAG, "HTTPS control server started on port %u", conf.port_secure);
    return ESP_OK;
}

esp_err_t app_http_server_stop(void)
{
    if (s_server == NULL) {
        return ESP_OK;
    }

    httpd_ssl_stop(s_server);
    s_server = NULL;
    ESP_LOGI(TAG, "HTTPS control server stopped");
    return ESP_OK;
}

bool app_http_server_is_running(void)
{
    return s_server != NULL;
}
