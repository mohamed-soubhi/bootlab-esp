#include "app_blink_timing.h"

uint32_t app_blink_half_period_ms(int is_4hz_variant)
{
    unsigned hz = is_4hz_variant ? 4u : 1u;
    return 1000u / hz / 2u;
}

app_rgb_t app_blink_color(app_variant_t variant, int confirmed)
{
    const app_rgb_t amber = APP_COLOR_AMBER;
    const app_rgb_t green = APP_COLOR_GREEN;
    const app_rgb_t blue = APP_COLOR_BLUE;
    const app_rgb_t red = APP_COLOR_RED;
    const app_rgb_t magenta = APP_COLOR_MAGENTA;

    /* Variants that are never healthy have a fixed color; the rest show
     * amber until the self-test confirms them, then their own color. */
    switch (variant) {
    case APP_VARIANT_HANG:        return red;
    case APP_VARIANT_BAD_SIG:     return magenta;
    case APP_VARIANT_NO_CONFIRM:  return amber;   /* by design never confirms */
    case APP_VARIANT_V2:          return confirmed ? blue : amber;
    case APP_VARIANT_V1:
    default:                      return confirmed ? green : amber;
    }
}
