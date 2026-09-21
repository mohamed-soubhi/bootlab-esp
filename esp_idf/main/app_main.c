/* esp_idf/main/app_main.c — BL-020: blink app, toggles counter, 5 build
 * variants, task watchdog panic-on-hang.
 *
 * Variant behavior (PLAN Sec 5.3):
 *   v1         -> 1 Hz blink, confirms
 *   v2         -> 4 Hz blink, confirms
 *   no_confirm -> blinks, never confirms
 *   hang       -> blocks all tasks after boot -> watchdog reset within 10s
 *   bad_sig    -> runtime behavior identical to v1; "bad_sig" is a
 *                 signing-time property (BL-021), not an app-level branch
 *
 * "Confirms" / "never confirms" (v1/v2 vs no_confirm) is BL-023's scope
 * (self-test + esp_ota mark-valid after 5s) -- not implemented here.
 * This ticket is blink + toggles + variant identity + watchdog only.
 *
 * LABID integration points (for BL-022, not wired to a transport here):
 *   app_get_toggle_count() and app_get_variant() are the accessors the
 *   labid_port component will read from when answering STATE?/VER?.
 */
#include <stdatomic.h>
#include <stdbool.h>

#include "app_blink_timing.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "app_wifi.h"
#include "labid_port.h"
#include "led_strip.h"
#define APP_LED_GPIO CONFIG_APP_LED_GPIO /* UNCONFIRMED, see Kconfig.projbuild */

/* Configured LED rate reported over LABID: v2 blinks at 4 Hz, all others 1 Hz. */
#if CONFIG_APP_VARIANT_V2
#define APP_BLINK_HZ_STR "4"
#else
#define APP_BLINK_HZ_STR "1"
#endif

static atomic_uint_least32_t s_toggle_count = 0;
static atomic_bool s_confirmed = false;

uint32_t app_get_toggle_count(void)
{
    return atomic_load(&s_toggle_count);
}

bool app_is_confirmed(void)
{
    return atomic_load(&s_confirmed);
}

const char *app_get_variant(void)
{
#if CONFIG_APP_VARIANT_V1
    return "v1";
#elif CONFIG_APP_VARIANT_V2
    return "v2";
#elif CONFIG_APP_VARIANT_NO_CONFIRM
    return "no_confirm";
#elif CONFIG_APP_VARIANT_HANG
    return "hang";
#elif CONFIG_APP_VARIANT_BAD_SIG
    return "bad_sig";
#else
#error "no APP_VARIANT_* selected -- run idf.py menuconfig"
#endif
}

static void blink_task(void *arg)
{
    led_strip_handle_t strip = (led_strip_handle_t)arg;
    esp_task_wdt_add(NULL);

#if CONFIG_APP_VARIANT_HANG
    /* Deliberately never feed the watchdog or yield: CONFIG_ESP_TASK_WDT_PANIC
     * plus CONFIG_ESP_TASK_WDT_TIMEOUT_S=5 (sdkconfig.defaults) must reset the
     * chip well within the 10s AC. */
    for (;;) {
        /* busy loop -- no vTaskDelay, no esp_task_wdt_reset() */
    }
#endif

    /* Kconfig choice macros for unselected options aren't defined as 0 --
     * they're simply undeclared, so CONFIG_APP_VARIANT_V2 can only be used
     * inside a preprocessor conditional, not passed as a runtime value. */
#if CONFIG_APP_VARIANT_V2
    const TickType_t half_period = pdMS_TO_TICKS(app_blink_half_period_ms(1));
#else
    const TickType_t half_period = pdMS_TO_TICKS(app_blink_half_period_ms(0));
#endif

    /* "Blink" for this WS2812/addressable RGB LED means toggling between a
     * fixed dim-white pixel (R=G=B=16 out of 255 -- deliberately dim, not a
     * default/arbitrary value) and off, at the rate from
     * app_blink_half_period_ms() above. */
    bool on = false;
    for (;;) {
        on = !on;
        if (on) {
            (void)led_strip_set_pixel(strip, 0, 16, 16, 16);
            (void)led_strip_refresh(strip);
        } else {
            (void)led_strip_clear(strip);
        }
        atomic_fetch_add(&s_toggle_count, 1);
        esp_task_wdt_reset();
        vTaskDelay(half_period);
    }
}

#if !CONFIG_APP_VARIANT_NO_CONFIRM && !CONFIG_APP_VARIANT_HANG
static void health_task(void *arg)
{
    (void)arg;
    /* Self-test per PLAN Sec 5.2:
     * - RTOS ticking for >= 5 s
     * - LED toggled >= 5 times */
    const TickType_t check_interval = pdMS_TO_TICKS(500);
    for (;;) {
        vTaskDelay(check_interval);
        uint32_t uptime_ms = (uint32_t)(esp_timer_get_time() / 1000);
        uint32_t toggles = app_get_toggle_count();
        if (uptime_ms >= 5000 && toggles >= 5) {
            esp_err_t err = esp_ota_mark_app_valid_cancel_rollback();
            (void)err;
            atomic_store(&s_confirmed, true);
            break;
        }
    }
    vTaskDelete(NULL);
}
#endif

void app_main(void)
{
    led_strip_config_t strip_config = {
        .strip_gpio_num = APP_LED_GPIO,
        .max_leds = 1,
    };
    led_strip_rmt_config_t rmt_config = {
        .resolution_hz = 10 * 1000 * 1000,
    };
    led_strip_handle_t strip;
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config, &rmt_config, &strip));
    led_strip_clear(strip);

    xTaskCreate(blink_task, "blink", 4096, strip, 5, NULL);

#if !CONFIG_APP_VARIANT_NO_CONFIRM && !CONFIG_APP_VARIANT_HANG
    xTaskCreate(health_task, "health", 3072, NULL, 3, NULL);
#endif

    /* BL-022 / BL-023: answer LABID requests over USB-Serial-JTAG (PLAN 7.3). */
    const struct labid_port_app labid_app = {
        .variant = app_get_variant(),
        .blink_hz = APP_BLINK_HZ_STR,
        .toggle_count = app_get_toggle_count,
        .is_confirmed = app_is_confirmed,
    };
    ESP_ERROR_CHECK(labid_port_start(&labid_app));

#if !CONFIG_APP_VARIANT_HANG
    /* BL-024: initialize NVS & WiFi in station mode if provisioned (PLAN 5.2 / 7.2) */
    ESP_ERROR_CHECK(app_wifi_init());
#endif
}
