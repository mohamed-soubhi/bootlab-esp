/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * main.c — Zephyr hello app with MCUboot integration (BL-030).
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/logging/log.h>
#include <zephyr/dfu/mcuboot.h>

LOG_MODULE_REGISTER(bootlab_app, LOG_LEVEL_INF);

int main(void)
{
    /* Give USB CDC a short moment after boot */
    k_msleep(100);

    printk("\n========================================\n");
    printk("  bootlab-esp: Zephyr + MCUboot Hello!  \n");
    printk("  Board: %s\n", CONFIG_BOARD);
    printk("  MCUboot swap-using-move verified      \n");
    printk("========================================\n");

    if (!boot_is_img_confirmed()) {
        printk("[APP] Image unconfirmed. Marking confirmed in slot0...\n");
        int ret = boot_write_img_confirmed();
        if (ret == 0) {
            printk("[APP] Image successfully confirmed in primary slot!\n");
        } else {
            printk("[APP] Error confirming image: %d\n", ret);
        }
    } else {
        printk("[APP] Image already confirmed in primary slot.\n");
    }

    uint32_t count = 0;
    while (1) {
        k_sleep(K_SECONDS(1));
        count++;
        printk("[APP] Zephyr app running on ESP32-S3 (tick %u, uptime: %lld ms)\n",
               count, k_uptime_get());
    }

    return 0;
}
