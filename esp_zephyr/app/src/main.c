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
#include "labid_port_zephyr.h"

LOG_MODULE_REGISTER(bootlab_app, LOG_LEVEL_INF);

#define STRIP_NODE DT_ALIAS(led_strip)
static const struct device *const strip = DEVICE_DT_GET(STRIP_NODE);

#define WDT_NODE DT_ALIAS(watchdog0)
static const struct device *const wdt = DEVICE_DT_GET(WDT_NODE);
static int wdt_channel_id = -1;

static atomic_t s_toggle_count = ATOMIC_INIT(0);
static atomic_t s_confirmed = ATOMIC_INIT(0);

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
    return (bool)atomic_get(&s_confirmed);
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

    if (boot_is_img_confirmed()) {
        atomic_set(&s_confirmed, 1);
        LOG_INF("[APP] Primary slot image already confirmed");
    } else {
        LOG_INF("[APP] Primary slot image unconfirmed (pending self-test)");
    }

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

    for (;;) {
        led_on = !led_on;
        if (led_on) {
            app_rgb_t c = app_blink_color(app_variant_id(), app_is_confirmed());
            set_led(c.r, c.g, c.b);
        } else {
            clear_led();
        }

        atomic_add(&s_toggle_count, 1);
        feed_watchdog();

#if !defined(CONFIG_APP_VARIANT_NO_CONFIRM) && !defined(CONFIG_APP_VARIANT_HANG)
        if (!app_is_confirmed()) {
            int64_t uptime = k_uptime_get();
            uint32_t toggles = app_get_toggle_count();
            if (uptime >= 5000 && toggles >= 5) {
                int ret = boot_write_img_confirmed();
                if (ret == 0) {
                    LOG_INF("[APP] Image successfully confirmed in primary slot!");
                    atomic_set(&s_confirmed, 1);
                } else {
                    LOG_ERR("[APP] Image confirmation failed: %d", ret);
                }
            }
        }
#endif

        log_tick++;
        if (log_tick % (1000 / half_period) == 0) {
            LOG_INF("[APP] Heartbeat: variant=%s, toggles=%u, confirmed=%d, uptime=%lld ms",
                    app_variant_str(), app_get_toggle_count(), (int)app_is_confirmed(), k_uptime_get());
        }

        k_msleep(half_period);
    }

    return 0;
}
