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

#endif
