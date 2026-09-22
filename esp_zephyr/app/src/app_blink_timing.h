/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * app_blink_timing.h — Blink rate math and LED color mapping for Zephyr app.
 */

#ifndef APP_BLINK_TIMING_H
#define APP_BLINK_TIMING_H

#include <stdint.h>
#include <stdbool.h>

#define APP_LED_LEVEL 16u

typedef struct {
    uint8_t r, g, b;
} app_rgb_t;

typedef enum {
    APP_VARIANT_V1,
    APP_VARIANT_V2,
    APP_VARIANT_NO_CONFIRM,
    APP_VARIANT_HANG,
    APP_VARIANT_BAD_SIG,
} app_variant_t;

#define APP_COLOR_AMBER   { APP_LED_LEVEL, 6u, 0u }   /* amber: unconfirmed / pending self-test */
#define APP_COLOR_GREEN   { 0u, APP_LED_LEVEL, 0u }   /* green: v1 confirmed */
#define APP_COLOR_BLUE    { 0u, 0u, APP_LED_LEVEL }   /* blue: v2 confirmed */
#define APP_COLOR_RED     { APP_LED_LEVEL, 0u, 0u }   /* red: hang */
#define APP_COLOR_MAGENTA { APP_LED_LEVEL, 0u, APP_LED_LEVEL } /* magenta: bad_sig */

uint32_t app_blink_half_period_ms(int is_4hz_variant);
app_rgb_t app_blink_color(app_variant_t variant, int confirmed);

#endif /* APP_BLINK_TIMING_H */
