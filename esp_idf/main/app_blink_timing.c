#include "app_blink_timing.h"

uint32_t app_blink_half_period_ms(int is_4hz_variant)
{
    unsigned hz = is_4hz_variant ? 4u : 1u;
    return 1000u / hz / 2u;
}
