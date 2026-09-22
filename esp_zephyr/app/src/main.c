/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * main.c — Zephyr blink app + toggles + 5 variants + watchdog (BL-031).
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/logging/log.h>
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/drivers/led_strip.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/sys/atomic.h>
#include "app_blink_timing.h"
#include "app_self_test.h"
#include "labid_port_zephyr.h"
#include "app_ble_smp.h"
#include "app_wifi.h"

LOG_MODULE_REGISTER(bootlab_app, LOG_LEVEL_INF);

#define STRIP_NODE DT_ALIAS(led_strip)
static const struct device *const strip = DEVICE_DT_GET(STRIP_NODE);

#define WDT_NODE DT_ALIAS(watchdog0)
static const struct device *const wdt = DEVICE_DT_GET(WDT_NODE);
static int wdt_channel_id = -1;

static atomic_t s_toggle_count = ATOMIC_INIT(0);
static struct app_self_test s_self_test;

const char *app_variant_str(void)
{
#if defined(CONFIG_APP_VARIANT_V1)
    return "v1";
#elif defined(CONFIG_APP_VARIANT_V2)
    return "v2";
#elif defined(CONFIG_APP_VARIANT_NO_CONFIRM)
    return "no_confirm";
#elif defined(CONFIG_APP_VARIANT_HANG)
    return "hang";
#elif defined(CONFIG_APP_VARIANT_BAD_SIG)
    return "bad_sig";
#else
    return "v1";
#endif
}

const char *app_get_variant_str(void)
{
    return app_variant_str();
}

app_variant_t app_variant_id(void)
{
#if defined(CONFIG_APP_VARIANT_V1)
    return APP_VARIANT_V1;
#elif defined(CONFIG_APP_VARIANT_V2)
    return APP_VARIANT_V2;
#elif defined(CONFIG_APP_VARIANT_NO_CONFIRM)
    return APP_VARIANT_NO_CONFIRM;
#elif defined(CONFIG_APP_VARIANT_HANG)
    return APP_VARIANT_HANG;
#else
    return APP_VARIANT_BAD_SIG;
#endif
}

uint32_t app_get_toggle_count(void)
{
    return (uint32_t)atomic_get(&s_toggle_count);
}

bool app_is_confirmed(void)
{
    return app_self_test_is_confirmed(&s_self_test);
}

static void set_led(uint8_t r, uint8_t g, uint8_t b)
{
    if (!device_is_ready(strip)) {
        return;
    }
    struct led_rgb pixel = { .r = r, .g = g, .b = b };
    (void)led_strip_update_rgb(strip, &pixel, 1);
}

static void clear_led(void)
{
    set_led(0, 0, 0);
}

static int init_watchdog(void)
{
    if (!device_is_ready(wdt)) {
        LOG_WRN("Watchdog device %s not ready", wdt ? wdt->name : "NULL");
        return -ENODEV;
    }
    struct wdt_timeout_cfg wdt_config = {
        .flags = WDT_FLAG_RESET_SOC,
        .window.min = 0U,
        .window.max = 5000U, /* 5000 ms (< 10s per BL-031 AC3) */
        .callback = NULL,
    };
    wdt_channel_id = wdt_install_timeout(wdt, &wdt_config);
    if (wdt_channel_id < 0) {
        LOG_ERR("Watchdog install error: %d", wdt_channel_id);
        return wdt_channel_id;
    }
    int err = wdt_setup(wdt, 0);
    if (err < 0) {
        LOG_ERR("Watchdog setup error: %d", err);
        return err;
    }
    LOG_INF("Hardware Watchdog armed (timeout: 5000 ms)");
    return 0;
}

static void feed_watchdog(void)
{
    if (wdt_channel_id >= 0 && device_is_ready(wdt)) {
        wdt_feed(wdt, wdt_channel_id);
    }
}

int main(void)
{
    k_msleep(100);

    printk("\n========================================\n");
    printk("  bootlab-esp: Zephyr BL-031 Blink App  \n");
    printk("  Board:   %s\n", CONFIG_BOARD);
    printk("  Variant: %s\n", app_variant_str());
    printk("========================================\n");

    if (device_is_ready(strip)) {
        LOG_INF("WS2812 LED strip ready on GPIO48");
    } else {
        LOG_WRN("WS2812 LED strip not ready");
    }

    bool can_confirm = (app_variant_id() != APP_VARIANT_NO_CONFIRM && app_variant_id() != APP_VARIANT_HANG);
    app_self_test_init(&s_self_test, can_confirm, boot_write_img_confirmed);
    LOG_INF("[APP] Self-test state machine initialized (can_confirm=%d, target_uptime=%u ms, target_toggles=%u)",
            (int)can_confirm, APP_SELF_TEST_MIN_UPTIME_MS, APP_SELF_TEST_MIN_TOGGLES);

    int wdt_rc = init_watchdog();
    if (wdt_rc != 0) {
        LOG_WRN("Proceeding without hardware watchdog (%d)", wdt_rc);
    }

    struct labid_app_info info = {
        .variant = app_variant_str(),
        .version = (app_variant_id() == APP_VARIANT_V2) ? "2.0.0" : "1.0.0",
        .blink_hz = (app_variant_id() == APP_VARIANT_V2) ? "4" : "1",
        .get_toggle_count = app_get_toggle_count,
        .is_confirmed = app_is_confirmed,
    };
    int labid_rc = labid_port_init(&info);
    if (labid_rc != 0) {
        LOG_WRN("Failed to initialize LABID port: %d", labid_rc);
    }

    int ble_rc = app_ble_smp_init();
    if (ble_rc != 0) {
        LOG_WRN("Failed to initialize BLE SMP: %d", ble_rc);
    }

    int wifi_rc = app_wifi_init();
    if (wifi_rc != 0) {
        LOG_WRN("Failed to initialize WiFi: %d", wifi_rc);
    }

#if defined(CONFIG_APP_VARIANT_HANG)
    LOG_WRN("[APP] HANG variant active — showing solid red, blocking to trigger watchdog reset...");
    app_rgb_t stuck = app_blink_color(APP_VARIANT_HANG, 0);
    set_led(stuck.r, stuck.g, stuck.b);
    for (;;) {
        /* Busy wait without feeding watchdog. Watchdog will panic and reset within 5s. */
        k_busy_wait(100000);
    }
#endif

    uint32_t half_period = app_blink_half_period_ms(
#if defined(CONFIG_APP_VARIANT_V2)
        1
#else
        0
#endif
    );

    LOG_INF("Blink loop starting (half-period: %u ms)", half_period);

    bool led_on = false;
    uint32_t log_tick = 0;
    int64_t last_led_hw_update = 0;

    for (;;) {
        led_on = !led_on;

        /* BL-064: rate-limit the actual LED strip hardware update independently of the logical
         * toggle rate. Zephyr's ws2812_i2s driver's DMA buffer pool (2 blocks, not exposed via
         * devicetree) exhausts under sustained call rates, and that exhaustion state was found to
         * also kill the LABID console's UART RX interrupt (see
         * scripts/evidence/bl064_zephyr_labid_rx_irq_dead.md). A 500 ms (~2 Hz) cadence was not
         * enough under real concurrent BLE+WiFi radio load (both active right after an OTA
         * reboot); 1000 ms exactly matches v1's cadence, proven safe under that same load
         * throughout this project's live testing. s_toggle_count/self-test/heartbeat below keep
         * running at the full logical rate, so LABID's measured toggle Hz (STATE? toggles, see
         * labflash.identify.measure()) is unaffected. */
        int64_t now_ms = k_uptime_get();
        if (now_ms - last_led_hw_update >= 1000) {
            last_led_hw_update = now_ms;
            if (led_on) {
                app_rgb_t c = app_blink_color(app_variant_id(), app_is_confirmed());
                set_led(c.r, c.g, c.b);
            } else {
                clear_led();
            }
        }

        atomic_add(&s_toggle_count, 1);
        feed_watchdog();

        bool newly_confirmed = app_self_test_update(&s_self_test, (uint32_t)k_uptime_get(), app_get_toggle_count());
        if (newly_confirmed) {
            static bool s_logged_confirm = false;
            if (!s_logged_confirm) {
                s_logged_confirm = true;
                LOG_INF("[APP] Self-test PASSED: Image successfully confirmed via MCUboot! (uptime=%lld ms, toggles=%u)",
                        k_uptime_get(), app_get_toggle_count());
            }
        } else if (app_self_test_get_status(&s_self_test) == APP_SELF_TEST_FAILED) {
            static bool s_logged_fail = false;
            if (!s_logged_fail) {
                s_logged_fail = true;
                LOG_ERR("[APP] Self-test FAILED: boot_write_img_confirmed returned %d", s_self_test.last_error);
            }
        }

        log_tick++;
        if (log_tick % (1000 / half_period) == 0) {
            LOG_INF("[APP] Heartbeat: variant=%s, toggles=%u, confirmed=%d, uptime=%lld ms, irq=%u, rx=%u",
                    app_variant_str(), app_get_toggle_count(), (int)app_is_confirmed(), k_uptime_get(),
                    g_irq_count, g_rx_bytes);
        }

        k_msleep(half_period);
    }

    return 0;
}
