/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * labid_port_zephyr.c — Zephyr glue for LABID (BL-032). Spec: PLAN §7.3.
 */

#include "labid_port_zephyr.h"

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/logging/log.h>
#include <zephyr/version.h>
#include <stdio.h>
#include <string.h>

#include "labid_dispatch.h"

LOG_MODULE_REGISTER(labid_port, LOG_LEVEL_INF);

#define LABID_THREAD_STACK_SIZE 4096
#define LABID_THREAD_PRIO       K_LOWEST_APPLICATION_THREAD_PRIO
#define LABID_ANNOUNCE_DELAY_MS 1500  /* <= 2 s per PLAN §7.3.2 */
#define LABID_MAC_BYTES         6
#define LABID_RING_BUF_SIZE     512

volatile uint32_t g_irq_count = 0;
volatile uint32_t g_rx_bytes = 0;

static struct labid_ctx s_ctx;
static struct labid_app_info s_app;
static const struct device *s_uart_dev;

RING_BUF_DECLARE(s_rx_ring, LABID_RING_BUF_SIZE);
K_SEM_DEFINE(s_rx_sem, 0, 1);
K_MUTEX_DEFINE(s_tx_mutex);

K_THREAD_STACK_DEFINE(s_labid_stack, LABID_THREAD_STACK_SIZE);
static struct k_thread s_labid_thread_data;

/* Helper: copy src into LABID-legal value: [A-Za-z0-9._:-], others -> '_' */
static int add_clean(struct labid_fields *f, const char *key, const char *src)
{
    char tmp[LABID_VAL_MAX];
    size_t n = 0;
    for (; src && src[n] != '\0' && n < sizeof(tmp) - 1u; n++) {
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
    uint8_t mac[LABID_MAC_BYTES] = {0};
    ssize_t ret = hwinfo_get_device_id(mac, sizeof(mac));
    if (ret <= 0) {
        return -1;
    }
    char hex[2 * LABID_MAC_BYTES + 1];
    for (size_t i = 0; i < LABID_MAC_BYTES; i++) {
        hex[2 * i]     = digits[mac[i] >> 4];
        hex[2 * i + 1] = digits[mac[i] & 0x0F];
    }
    hex[2 * LABID_MAC_BYTES] = '\0';
    return labid_fields_add(f, "uid", hex);
}

static void build_stamp(char *out, size_t outlen)
{
    static const char months[] = "JanFebMarAprMayJunJulAugSepOctNovDec";
    const char *date_str = __DATE__;
    const char *time_str = __TIME__;
    char mon3[4] = { date_str[0], date_str[1], date_str[2], '\0' };
    const char *m = strstr(months, mon3);
    int day = 0, year = 0, hh = 0, mm = 0;
    if (!m || sscanf(date_str + 3, "%d %d", &day, &year) != 2 ||
        sscanf(time_str, "%d:%d", &hh, &mm) != 2) {
        snprintf(out, outlen, "unknown");
        return;
    }
    snprintf(out, outlen, "%04d%02d%02dT%02d%02dZ", year, (int)((m - months) / 3) + 1, day, hh, mm);
}

static const char *get_reset_name(void)
{
    uint32_t cause = 0;
    int ret = hwinfo_get_reset_cause(&cause);
    if (ret != 0) {
        return "other";
    }
    if (cause & RESET_POR) {
        return "por";
    }
    if (cause & RESET_PIN) {
        return "pin";
    }
    if (cause & RESET_SOFTWARE) {
        return "sw";
    }
    if (cause & RESET_WATCHDOG) {
        return "wdt";
    }
    if (cause & RESET_BROWNOUT) {
        return "brownout";
    }
    if (cause & RESET_CPU_LOCKUP) {
        return "panic";
    }
    return "other";
}

/* ---------- Provider Callbacks ---------- */

static int prov_announce(void *user, struct labid_fields *f)
{
    ARG_UNUSED(user);
    return labid_fields_add(f, "board", "zephyr") | add_uid(f)
         | add_clean(f, "app", s_app.version ? s_app.version : "1.0.0");
}

static int prov_id(void *user, struct labid_fields *f)
{
    ARG_UNUSED(user);
    char os[LABID_VAL_MAX];
    snprintf(os, sizeof(os), "zephyr-%s", KERNEL_VERSION_STRING);
    return labid_fields_add(f, "board", "zephyr")
         | labid_fields_add(f, "hw", "esp32s3_devkitc")
         | labid_fields_add(f, "mcu", "esp32s3")
         | add_uid(f)
         | add_clean(f, "os", os)
         | labid_fields_add_u32(f, "flash_kb", 16384);
}

static int prov_ver(void *user, struct labid_fields *f)
{
    ARG_UNUSED(user);
    char build[LABID_VAL_MAX];
    build_stamp(build, sizeof(build));

    return add_clean(f, "bl", "mcuboot")
         | add_clean(f, "app", s_app.version ? s_app.version : "1.0.0")
         | add_clean(f, "git", "db7cfc2")
         | add_clean(f, "build", build)
         | add_clean(f, "variant", s_app.variant ? s_app.variant : "v1")
         | labid_fields_add(f, "slot", "0")
         | labid_fields_add(f, "confirmed", (s_app.is_confirmed && s_app.is_confirmed()) ? "1" : "0");
}

static int prov_state(void *user, struct labid_fields *f)
{
    ARG_UNUSED(user);
    return labid_fields_add_u32(f, "uptime_ms", (uint32_t)k_uptime_get())
         | labid_fields_add(f, "reset", get_reset_name())
         | labid_fields_add(f, "blink_hz", s_app.blink_hz ? s_app.blink_hz : "1")
         | labid_fields_add_u32(f, "toggles", s_app.get_toggle_count ? s_app.get_toggle_count() : 0u);
}

static const struct labid_provider s_prov = {
    .user = NULL,
    .announce = prov_announce,
    .id = prov_id,
    .ver = prov_ver,
    .state = prov_state,
};

/* ---------- Transport & Thread ---------- */

static void send_frame(const char *frame)
{
    k_mutex_lock(&s_tx_mutex, K_FOREVER);
    if (s_uart_dev) {
        size_t len = strlen(frame);
        size_t sent = 0;
        int retries = 0;
        while (sent < len && retries++ < 5000) {
            int ret = uart_fifo_fill(s_uart_dev, (const uint8_t *)frame + sent, (int)(len - sent));
            if (ret > 0) {
                sent += (size_t)ret;
            } else {
                k_busy_wait(50);
            }
        }
    } else {
        printk("%s", frame);
    }
    k_mutex_unlock(&s_tx_mutex);
}

static void uart_irq_cb(const struct device *dev, void *user_data)
{
    ARG_UNUSED(user_data);
    g_irq_count++;
    uart_irq_update(dev);
    while (uart_irq_rx_ready(dev)) {
        uint8_t byte;
        int ret = uart_fifo_read(dev, &byte, 1);
        if (ret > 0) {
            g_rx_bytes++;
            ring_buf_put(&s_rx_ring, &byte, 1);
            k_sem_give(&s_rx_sem);
        } else {
            break;
        }
    }
}

static void labid_thread_entry(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    char out[LABID_MAX_FRAME + 8];
    int64_t announce_at = k_uptime_get() + LABID_ANNOUNCE_DELAY_MS;
    bool announced = false;

    for (;;) {
        /* Wait up to 20ms for an RX interrupt or poll timeout */
        k_sem_take(&s_rx_sem, K_MSEC(20));

        /* BL-064: Check and drain hardware FIFO under irq_lock().
         * On ESP32-S3 USB-Serial-JTAG, SERIAL_OUT_RECV_PKT is edge-triggered.
         * If bytes arrived before interrupts were enabled (e.g. during an MCUboot swap)
         * or if an interrupt edge was missed, polling the FIFO ensures bytes are never
         * trapped, keeping the hardware USB endpoint responsive to subsequent OUT packets. */
        if (s_uart_dev) {
            unsigned int key = irq_lock();
            while (uart_irq_rx_ready(s_uart_dev)) {
                uint8_t byte;
                int ret = uart_fifo_read(s_uart_dev, &byte, 1);
                if (ret > 0) {
                    g_rx_bytes++;
                    ring_buf_put(&s_rx_ring, &byte, 1);
                } else {
                    break;
                }
            }
            irq_unlock(key);
        }

        uint8_t byte;
        while (ring_buf_get(&s_rx_ring, &byte, 1) > 0) {
            int len = labid_ctx_feed(&s_ctx, byte, out, sizeof(out));
            if (len > 0) {
                send_frame(out);
            }
        }

        /* Send ANNOUNCE after initial delay window has elapsed (PLAN §7.3.2) */
        if (!announced && k_uptime_get() >= announce_at) {
            int alen = labid_announce(&s_ctx, out, sizeof(out));
            if (alen > 0) {
                send_frame(out);
            }
            announced = true;
        }
    }
}

int labid_port_init(const struct labid_app_info *app)
{
    if (!app) {
        return -EINVAL;
    }
    s_app = *app;
    labid_ctx_init(&s_ctx, &s_prov);

    const struct device *const uart_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
    if (!device_is_ready(uart_dev)) {
        LOG_ERR("Console device %s is not ready", uart_dev->name);
        return -ENODEV;
    }
    s_uart_dev = uart_dev;

    /* BL-064: Flush any stale pre-boot data in the hardware FIFO (e.g. from MCUboot swap) */
    while (uart_irq_rx_ready(uart_dev)) {
        uint8_t dummy;
        if (uart_fifo_read(uart_dev, &dummy, 1) <= 0) {
            break;
        }
    }

    uart_irq_callback_user_data_set(uart_dev, uart_irq_cb, NULL);
    uart_irq_rx_enable(uart_dev);

    /* Drain again right after interrupt enable in case new bytes arrived during init */
    while (uart_irq_rx_ready(uart_dev)) {
        uint8_t dummy;
        if (uart_fifo_read(uart_dev, &dummy, 1) <= 0) {
            break;
        }
    }

    k_thread_create(&s_labid_thread_data, s_labid_stack,
                    K_THREAD_STACK_SIZEOF(s_labid_stack),
                    labid_thread_entry, NULL, NULL, NULL,
                    LABID_THREAD_PRIO, 0, K_NO_WAIT);
    k_thread_name_set(&s_labid_thread_data, "labid");

    LOG_INF("LABID initialized on console (irq+polled RX, ANNOUNCE in %d ms)", LABID_ANNOUNCE_DELAY_MS);
    return 0;
}
