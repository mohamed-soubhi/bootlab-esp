/*
 * test_blink_color.c — plain-gcc host test for the LED color scheme.
 *
 *   gcc -Wall -Wextra -I../main -o /tmp/test_blink_color \
 *       test_blink_color.c ../main/app_blink_timing.c && /tmp/test_blink_color
 *
 * The scheme (color carries the state; rate stays 1 Hz / 4 Hz):
 *   not yet confirmed -> amber      v1 confirmed -> green     v2 confirmed -> blue
 *   hang -> red                     bad_sig -> magenta
 */
#include <stdio.h>
#include <string.h>

#include "app_blink_timing.h"

static int failures;

static void expect(const char *name, app_variant_t v, int confirmed, app_rgb_t want)
{
    app_rgb_t got = app_blink_color(v, confirmed);
    int ok = got.r == want.r && got.g == want.g && got.b == want.b;
    if (!ok) {
        failures++;
        printf("FAIL %s: got (%u,%u,%u) want (%u,%u,%u)\n", name, got.r, got.g, got.b,
               want.r, want.g, want.b);
    }
}

int main(void)
{
    const app_rgb_t amber = APP_COLOR_AMBER, green = APP_COLOR_GREEN, blue = APP_COLOR_BLUE;
    const app_rgb_t red = APP_COLOR_RED, magenta = APP_COLOR_MAGENTA;

    expect("v1 pending is amber", APP_VARIANT_V1, 0, amber);
    expect("v1 confirmed is green", APP_VARIANT_V1, 1, green);
    expect("v2 pending is amber", APP_VARIANT_V2, 0, amber);
    expect("v2 confirmed is blue", APP_VARIANT_V2, 1, blue);
    expect("no_confirm is amber while pending", APP_VARIANT_NO_CONFIRM, 0, amber);
    expect("no_confirm stays amber even if flagged confirmed", APP_VARIANT_NO_CONFIRM, 1, amber);
    expect("hang is red regardless of state", APP_VARIANT_HANG, 0, red);
    expect("hang is red when confirmed", APP_VARIANT_HANG, 1, red);
    expect("bad_sig is magenta", APP_VARIANT_BAD_SIG, 1, magenta);
    expect("bad_sig is magenta while pending", APP_VARIANT_BAD_SIG, 0, magenta);

    /* every color is distinct, so a state can be told apart by eye */
    const app_rgb_t all[] = { amber, green, blue, red, magenta };
    for (unsigned i = 0; i < sizeof all / sizeof all[0]; i++) {
        for (unsigned j = i + 1; j < sizeof all / sizeof all[0]; j++) {
            if (memcmp(&all[i], &all[j], sizeof all[i]) == 0) {
                failures++;
                printf("FAIL colors %u and %u are identical\n", i, j);
            }
        }
    }

    /* dim on purpose: no channel above the project's LED level */
    for (unsigned i = 0; i < sizeof all / sizeof all[0]; i++) {
        if (all[i].r > APP_LED_LEVEL || all[i].g > APP_LED_LEVEL || all[i].b > APP_LED_LEVEL) {
            failures++;
            printf("FAIL color %u brighter than APP_LED_LEVEL\n", i);
        }
    }

    /* the rate math is untouched */
    if (app_blink_half_period_ms(0) != 500u || app_blink_half_period_ms(1) != 125u) {
        failures++;
        printf("FAIL half-period regression\n");
    }

    printf(failures ? "%d FAILED\n" : "all color tests passed\n", failures);
    return failures ? 1 : 0;
}
