/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * labid_port_zephyr.h — Zephyr LABID console port header (BL-032).
 */

#ifndef LABID_PORT_ZEPHYR_H
#define LABID_PORT_ZEPHYR_H

#include <stdint.h>
#include <stdbool.h>

struct labid_app_info {
    const char *variant;
    const char *version;
    const char *blink_hz;
    uint32_t (*get_toggle_count)(void);
    bool (*is_confirmed)(void);
};

extern volatile uint32_t g_irq_count;
extern volatile uint32_t g_rx_bytes;

int labid_port_init(const struct labid_app_info *app);

#endif /* LABID_PORT_ZEPHYR_H */
