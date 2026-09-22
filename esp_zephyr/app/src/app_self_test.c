/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * app_self_test.c — Zephyr self-test and MCUboot confirmation state machine (BL-033).
 */

#include "app_self_test.h"

void app_self_test_init(struct app_self_test *st, bool can_confirm, app_confirm_fn_t confirm_fn)
{
    if (!st) {
        return;
    }
    st->can_confirm = can_confirm;
    st->status = can_confirm ? APP_SELF_TEST_PENDING : APP_SELF_TEST_DISABLED;
    st->min_uptime_ms = APP_SELF_TEST_MIN_UPTIME_MS;
    st->min_toggles = APP_SELF_TEST_MIN_TOGGLES;
    st->confirm_fn = confirm_fn;
    st->last_error = 0;
}

bool app_self_test_update(struct app_self_test *st, uint32_t uptime_ms, uint32_t toggles)
{
    if (!st) {
        return false;
    }
    if (st->status == APP_SELF_TEST_CONFIRMED) {
        return true;
    }
    if (!st->can_confirm || st->status == APP_SELF_TEST_DISABLED) {
        return false;
    }

    /* Self-test criteria per PLAN §5.2:
     * 1. RTOS ticking for >= 5 s (5000 ms)
     * 2. LED toggled >= 5 times */
    if (uptime_ms >= st->min_uptime_ms && toggles >= st->min_toggles) {
        if (st->confirm_fn) {
            int ret = st->confirm_fn();
            if (ret == 0) {
                st->status = APP_SELF_TEST_CONFIRMED;
                st->last_error = 0;
                return true;
            } else {
                st->status = APP_SELF_TEST_FAILED;
                st->last_error = ret;
                return false;
            }
        } else {
            /* If no confirm function provided, consider passed */
            st->status = APP_SELF_TEST_CONFIRMED;
            return true;
        }
    }

    return false;
}

bool app_self_test_is_confirmed(const struct app_self_test *st)
{
    if (!st) {
        return false;
    }
    return (st->status == APP_SELF_TEST_CONFIRMED);
}

enum app_self_test_status app_self_test_get_status(const struct app_self_test *st)
{
    if (!st) {
        return APP_SELF_TEST_DISABLED;
    }
    return st->status;
}
