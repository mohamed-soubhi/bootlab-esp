/*
 * labid_port.c — ESP-IDF glue for LABID (BL-022). Spec: PLAN §7.3.
 *
 * RX: USB-Serial-JTAG driver read (not stdin) -> labid_ctx_feed() in a
 *     low-priority task, so the RTOS is never blocked (PLAN §7.3.4).
 * TX: each frame goes out in ONE fputs() under the stdout lock, the same path
 *     esp_log uses, so a frame is never interleaved with a log line.
 */
#include "labid_port.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_app_desc.h"
#include "esp_bootloader_desc.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "labid_dispatch.h"

static const char *TAG = "labid_port";

#define LABID_TASK_STACK      4096
#define LABID_TASK_PRIO       2       /* below the app tasks: low priority */
#define LABID_RX_BUF_BYTES    512
#define LABID_TX_BUF_BYTES    512
#define LABID_RX_POLL_MS      20      /* keeps responses well inside 100 ms */
#define LABID_ANNOUNCE_MS     1000    /* <= 2 s after reset */
#define LABID_RX_CHUNK        32
#define LABID_GIT_CHARS       7
#define LABID_MAC_BYTES       6

static struct labid_ctx s_ctx;
static struct labid_port_app s_app;

/* ---------- helpers ---------- */

/* Copy src into a LABID-legal value: [A-Za-z0-9._:-], anything else -> '_'. */
static int add_clean(struct labid_fields *f, const char *key, const char *src)
{
    char tmp[LABID_VAL_MAX];
    size_t n = 0;
    for (; src && src[n] != '\0' && n < sizeof tmp - 1u; n++) {
        char c = src[n];
        int ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
              || c == '.' || c == '_' || c == ':' || c == '-';
        tmp[n] = ok ? c : '_';
    }
    tmp[n] = '\0';
    return labid_fields_add(f, key, n ? tmp : "unknown");
}

static int add_uid(struct labid_fields *f)
{
    static const char digits[] = "0123456789ABCDEF";
    uint8_t mac[LABID_MAC_BYTES];
    char hex[2 * LABID_MAC_BYTES + 1];
    if (esp_efuse_mac_get_default(mac) != ESP_OK) { return -1; }
    for (size_t i = 0; i < LABID_MAC_BYTES; i++) {
        hex[2 * i]     = digits[mac[i] >> 4];
        hex[2 * i + 1] = digits[mac[i] & 0x0F];
    }
    hex[2 * LABID_MAC_BYTES] = '\0';
    return labid_fields_add(f, "uid", hex);
}

/* "Sep 21 2026" + "10:18:23" (compile time) -> "20260921T1018Z". Not UTC: the
 * IDF app descriptor only records local build time. */
static void build_stamp(const esp_app_desc_t *d, char *out, size_t outlen)
{
    static const char months[] = "JanFebMarAprMayJunJulAugSepOctNovDec";
    char mon3[4] = { d->date[0], d->date[1], d->date[2], '\0' };
    const char *m = strstr(months, mon3);
    int day = 0, year = 0, hh = 0, mm = 0;
    if (!m || sscanf(d->date + 3, "%d %d", &day, &year) != 2 ||
        sscanf(d->time, "%d:%d", &hh, &mm) != 2) {
        snprintf(out, outlen, "unknown");
        return;
    }
    snprintf(out, outlen, "%04d%02d%02dT%02d%02dZ", year, (int)((m - months) / 3) + 1, day, hh, mm);
}

static const char *reset_name(esp_reset_reason_t r)
{
    switch (r) {
    case ESP_RST_POWERON:   return "por";
    case ESP_RST_EXT:       return "pin";
    case ESP_RST_SW:        return "sw";
    case ESP_RST_PANIC:     return "panic";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:       return "wdt";
    case ESP_RST_BROWNOUT:  return "brownout";
    default:                return "other";
    }
}

/* ---------- providers ---------- */

static int prov_announce(void *user, struct labid_fields *f)
{
    (void)user;
    return labid_fields_add(f, "board", "idf") | add_uid(f)
         | add_clean(f, "app", esp_app_get_description()->version);
}

static int prov_id(void *user, struct labid_fields *f)
{
    (void)user;
    char os[LABID_VAL_MAX];
    uint32_t flash_bytes = 0;
    if (esp_flash_get_size(NULL, &flash_bytes) != ESP_OK) { return -1; }
    snprintf(os, sizeof os, "idf-%s", esp_get_idf_version());
    return labid_fields_add(f, "board", "idf") | labid_fields_add(f, "hw", "esp32s3_devkitc")
         | labid_fields_add(f, "mcu", "esp32s3") | add_uid(f) | add_clean(f, "os", os)
         | labid_fields_add_u32(f, "flash_kb", flash_bytes / 1024u);
}

/* Factory images have no otadata, so they cannot roll back: report confirmed. */
static bool running_image_confirmed(const esp_partition_t *run)
{
    esp_ota_img_states_t st;
    if (esp_ota_get_state_partition(run, &st) != ESP_OK) { return true; }
    return !(st == ESP_OTA_IMG_NEW || st == ESP_OTA_IMG_PENDING_VERIFY);
}

static int prov_ver(void *user, struct labid_fields *f)
{
    (void)user;
    const esp_app_desc_t *app = esp_app_get_description();
    const esp_bootloader_desc_t *bl = esp_bootloader_get_description();
    const esp_partition_t *run = esp_ota_get_running_partition();
    char git[LABID_GIT_CHARS + 1];
    char build[LABID_VAL_MAX];
    if (!run) { return -1; }
    strncpy(git, app->version, LABID_GIT_CHARS);
    git[LABID_GIT_CHARS] = '\0';
    build_stamp(app, build, sizeof build);
    return add_clean(f, "bl", bl->idf_ver) | add_clean(f, "app", app->version)
         | add_clean(f, "git", git) | add_clean(f, "build", build)
         | add_clean(f, "variant", s_app.variant)
         | labid_fields_add(f, "slot", run->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_1 ? "1" : "0")
         | labid_fields_add(f, "confirmed", running_image_confirmed(run) ? "1" : "0");
}

static int prov_state(void *user, struct labid_fields *f)
{
    (void)user;
    return labid_fields_add_u32(f, "uptime_ms", (uint32_t)(esp_timer_get_time() / 1000))
         | labid_fields_add(f, "reset", reset_name(esp_reset_reason()))
         | labid_fields_add(f, "blink_hz", s_app.blink_hz)
         | labid_fields_add_u32(f, "toggles", s_app.toggle_count ? s_app.toggle_count() : 0u);
}

static const struct labid_provider s_prov = {
    NULL, prov_announce, prov_id, prov_ver, prov_state
};

/* ---------- transport ---------- */

static void send_frame(const char *frame)
{
    flockfile(stdout);
    fputs(frame, stdout);
    fflush(stdout);
    funlockfile(stdout);
}

static void labid_task(void *arg)
{
    (void)arg;
    uint8_t rx[LABID_RX_CHUNK];
    char out[LABID_MAX_FRAME + 8];
    const TickType_t announce_at = xTaskGetTickCount() + pdMS_TO_TICKS(LABID_ANNOUNCE_MS);
    bool announced = false;

    for (;;) {
        int n = usb_serial_jtag_read_bytes(rx, sizeof rx, pdMS_TO_TICKS(LABID_RX_POLL_MS));
        for (int i = 0; i < n; i++) {
            int len = labid_ctx_feed(&s_ctx, rx[i], out, sizeof out);
            if (len > 0) { send_frame(out); }
        }
        if (!announced && (int32_t)(xTaskGetTickCount() - announce_at) >= 0) {
            if (labid_announce(&s_ctx, out, sizeof out) > 0) { send_frame(out); }
            announced = true;
        }
    }
}

esp_err_t labid_port_start(const struct labid_port_app *app)
{
    if (!app || !app->variant || !app->blink_hz) { return ESP_ERR_INVALID_ARG; }
    s_app = *app;
    labid_ctx_init(&s_ctx, &s_prov);

    usb_serial_jtag_driver_config_t cfg = {
        .tx_buffer_size = LABID_TX_BUF_BYTES,
        .rx_buffer_size = LABID_RX_BUF_BYTES,
    };
    esp_err_t err = usb_serial_jtag_driver_install(&cfg);
    if (err != ESP_OK) { return err; }
    /* Logs and frames share one TX path; frames end in a bare '\n' (PLAN §7.3.1). */
    usb_serial_jtag_vfs_set_tx_line_endings(ESP_LINE_ENDINGS_LF);
    usb_serial_jtag_vfs_use_driver();

    if (xTaskCreate(labid_task, "labid", LABID_TASK_STACK, NULL, LABID_TASK_PRIO, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(TAG, "LABID on USB-Serial-JTAG, ANNOUNCE in %d ms", LABID_ANNOUNCE_MS);
    return ESP_OK;
}
