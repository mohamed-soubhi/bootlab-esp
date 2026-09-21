#ifndef APP_BLINK_TIMING_H
#define APP_BLINK_TIMING_H
#include <stdint.h>

/* Half-period of the blink toggle, in milliseconds, for the given variant.
 * v2 blinks at 4 Hz; every other variant that reaches the blink loop
 * (v1, no_confirm, bad_sig) blinks at 1 Hz per PLAN Sec 5.3.
 *
 * Pure function, zero ESP-IDF/FreeRTOS dependency -- deliberately factored
 * out of app_main.c so the blink-rate math is host-testable with plain gcc,
 * without requiring the ESP-IDF toolchain to be installed.
 */
uint32_t app_blink_half_period_ms(int is_4hz_variant);

/* LED color scheme: color carries the STATE, the blink rate stays 1 Hz / 4 Hz.
 *
 *   not yet confirmed (pending verify, or never confirms) -> amber
 *   v1 confirmed                                          -> green
 *   v2 confirmed                                          -> blue
 *   hang                                                  -> red
 *   bad_sig                                               -> magenta
 *
 * Every channel is <= APP_LED_LEVEL (deliberately dim). Pure function, host-testable. */
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

#define APP_COLOR_AMBER   { APP_LED_LEVEL, 6u, 0u }   /* pure R+G reads yellow; less G reads amber */
#define APP_COLOR_GREEN   { 0u, APP_LED_LEVEL, 0u }
#define APP_COLOR_BLUE    { 0u, 0u, APP_LED_LEVEL }
#define APP_COLOR_RED     { APP_LED_LEVEL, 0u, 0u }
#define APP_COLOR_MAGENTA { APP_LED_LEVEL, 0u, APP_LED_LEVEL }

app_rgb_t app_blink_color(app_variant_t variant, int confirmed);

#endif
