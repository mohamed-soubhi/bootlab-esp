/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * app_self_test.h — Zephyr self-test and MCUboot confirmation state machine (BL-033).
 */

#ifndef APP_SELF_TEST_H_
#define APP_SELF_TEST_H_

#include <stdint.h>
#include <stdbool.h>

#define APP_SELF_TEST_MIN_UPTIME_MS  5000U
#define APP_SELF_TEST_MIN_TOGGLES    5U

typedef int (*app_confirm_fn_t)(void);

enum app_self_test_status {
    APP_SELF_TEST_PENDING = 0,
    APP_SELF_TEST_CONFIRMED = 1,
    APP_SELF_TEST_DISABLED = 2,  /* no_confirm / hang */
    APP_SELF_TEST_FAILED = 3,    /* confirm_fn returned error */
};

struct app_self_test {
    bool can_confirm;
    enum app_self_test_status status;
    uint32_t min_uptime_ms;
    uint32_t min_toggles;
    app_confirm_fn_t confirm_fn;
    int last_error;
};

void app_self_test_init(struct app_self_test *st, bool can_confirm, app_confirm_fn_t confirm_fn);
bool app_self_test_update(struct app_self_test *st, uint32_t uptime_ms, uint32_t toggles);
bool app_self_test_is_confirmed(const struct app_self_test *st);
enum app_self_test_status app_self_test_get_status(const struct app_self_test *st);

#endif /* APP_SELF_TEST_H_ */
