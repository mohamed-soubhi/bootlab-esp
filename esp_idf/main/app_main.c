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
#include "app_ble_ota.h"
#include "app_wifi.h"
#include "labid_port.h"
#include "led_strip.h"
#if CONFIG_APP_GEN_POOL
#include "driver/gpio.h"
#endif
#define APP_LED_GPIO CONFIG_APP_LED_GPIO /* UNCONFIRMED, see Kconfig.projbuild */

/* Configured LED rate reported over LABID: v2 blinks at 4 Hz, all others 1 Hz. */
#if CONFIG_APP_GEN_POOL
/* BL-069 pool image: the generator computes the real rate from CONFIG_APP_GEN_BLINK_MS. */
#define APP_BLINK_HZ_STR CONFIG_APP_GEN_BLINK_HZ
#elif CONFIG_APP_VARIANT_V2
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

static app_variant_t app_variant_id(void)
{
#if CONFIG_APP_VARIANT_V1
    return APP_VARIANT_V1;
#elif CONFIG_APP_VARIANT_V2
    return APP_VARIANT_V2;
#elif CONFIG_APP_VARIANT_NO_CONFIRM
    return APP_VARIANT_NO_CONFIRM;
#elif CONFIG_APP_VARIANT_HANG
    return APP_VARIANT_HANG;
#else
    return APP_VARIANT_BAD_SIG;
#endif
}

static void blink_task(void *arg)
{
    led_strip_handle_t strip = (led_strip_handle_t)arg;
    esp_task_wdt_add(NULL);

#if CONFIG_APP_VARIANT_HANG
    /* Solid red so a stuck image is visible before the watchdog resets it. */
    const app_rgb_t stuck = app_blink_color(APP_VARIANT_HANG, 0);
    (void)led_strip_set_pixel(strip, 0, stuck.r, stuck.g, stuck.b);
    (void)led_strip_refresh(strip);
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
#if CONFIG_APP_GEN_POOL
    const TickType_t half_period = pdMS_TO_TICKS(CONFIG_APP_GEN_BLINK_MS);
#elif CONFIG_APP_VARIANT_V2
    const TickType_t half_period = pdMS_TO_TICKS(app_blink_half_period_ms(1));
#else
    const TickType_t half_period = pdMS_TO_TICKS(app_blink_half_period_ms(0));
#endif

    /* "Blink" for this WS2812/addressable RGB LED means toggling between a dim
     * colored pixel and off, at the rate from app_blink_half_period_ms() above.
     * The COLOR carries the state (amber = not yet confirmed, green = v1,
     * blue = v2; see app_blink_color()); it is re-read on every "on" so it
     * turns from amber to its final color when the self-test confirms. */
    bool on = false;
    for (;;) {
        on = !on;
        if (on) {
#if CONFIG_APP_GEN_POOL
            /* Keep the amber "not yet confirmed" cue; the confirmed colour is generated, scaled /8 to stay dim like the fixed variants. */
            const app_rgb_t c = app_is_confirmed() ? (app_rgb_t){ CONFIG_APP_GEN_LED_R / 8, CONFIG_APP_GEN_LED_G / 8, CONFIG_APP_GEN_LED_B / 8 }
                                                   : app_blink_color(app_variant_id(), false);
#else
            const app_rgb_t c = app_blink_color(app_variant_id(), app_is_confirmed());
#endif
            (void)led_strip_set_pixel(strip, 0, c.r, c.g, c.b);
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

#if CONFIG_APP_GEN_POOL
/* BL-069: padding blob linked by CMakeLists.txt (-DGEN_PAD_FILE). Referencing it keeps it in the image. */
extern const uint8_t s_gen_pad_start[] asm("_binary_pad_bin_start");
extern const uint8_t s_gen_pad_end[] asm("_binary_pad_bin_end");

/* Compile-time copy of host/labflash/pinpolicy.py SAFE_OUTPUT_PINS (a host test keeps the two in sync): a pin outside
 * it cannot compile, so a hand-edited defaults file can never drive a strapping, USB, flash or console pin. */
#define GEN_PIN_OK(p) ((p) == 1 || (p) == 2 || ((p) >= 4 && (p) <= 18) || (p) == 21 || (p) == 47)
_Static_assert(GEN_PIN_OK(CONFIG_APP_GEN_PIN_A) && GEN_PIN_OK(CONFIG_APP_GEN_PIN_B),
               "CONFIG_APP_GEN_PIN_A/B must be in pinpolicy.SAFE_OUTPUT_PINS");

/* Toggle two allowlisted spare pins at the LED rate. Not subscribed to the task watchdog; it always yields. */
static void gen_pins_task(void *arg)
{
    (void)arg;
    const gpio_config_t io = {
        .pin_bit_mask = (1ULL << CONFIG_APP_GEN_PIN_A) | (1ULL << CONFIG_APP_GEN_PIN_B),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&io));
    const size_t pad_len = (size_t)(s_gen_pad_end - s_gen_pad_start);
    ESP_LOGI("gen_pool", "pad=%u bytes (configured %d), pins %d/%d", (unsigned)pad_len, CONFIG_APP_GEN_PAD_BYTES,
             CONFIG_APP_GEN_PIN_A, CONFIG_APP_GEN_PIN_B);
    int level = 0;
    for (;;) {
        level = !level;
        gpio_set_level(CONFIG_APP_GEN_PIN_A, level);
        gpio_set_level(CONFIG_APP_GEN_PIN_B, !level);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_APP_GEN_BLINK_MS));
    }
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
#if CONFIG_APP_GEN_POOL
    xTaskCreate(gen_pins_task, "gen_pins", 3072, NULL, 2, NULL);
#endif

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

    /* BL-027: BLE OTA service (NimBLE, coexists with WiFi; PLAN 7.2). Optional: if BLE
     * cannot start the board must still boot -- a fatal check here caused a boot loop
     * that also took the WiFi OTA recovery path down. */
    const esp_err_t ble_err = app_ble_ota_start();
    if (ble_err != ESP_OK) {
        ESP_LOGE("app_main", "BLE OTA unavailable (%s); WiFi OTA is unaffected", esp_err_to_name(ble_err));
    }
#endif
}
