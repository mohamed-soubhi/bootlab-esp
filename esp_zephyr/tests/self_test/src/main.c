/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * main.c — Twister unit tests for Zephyr self-test and confirmation (BL-033).
 */

#include <zephyr/ztest.h>
#include "app_self_test.h"

static int s_mock_confirm_call_count = 0;
static int s_mock_confirm_return_val = 0;

static int mock_confirm_fn(void)
{
    s_mock_confirm_call_count++;
    return s_mock_confirm_return_val;
}

static void *self_test_setup(void)
{
    return NULL;
}

static void self_test_before(void *fixture)
{
    ARG_UNUSED(fixture);
    s_mock_confirm_call_count = 0;
    s_mock_confirm_return_val = 0;
}

ZTEST_SUITE(self_test_suite, NULL, self_test_setup, self_test_before, NULL, NULL);

ZTEST(self_test_suite, test_init_state)
{
    struct app_self_test st;

    /* Initial state with confirmation enabled */
    app_self_test_init(&st, true, mock_confirm_fn);
    zassert_false(app_self_test_is_confirmed(&st), "Initial state should be unconfirmed");
    zassert_equal(app_self_test_get_status(&st), APP_SELF_TEST_PENDING, "Initial status should be PENDING");

    /* Initial state with confirmation disabled (e.g. no_confirm) */
    app_self_test_init(&st, false, mock_confirm_fn);
    zassert_false(app_self_test_is_confirmed(&st), "Disabled state should be unconfirmed");
    zassert_equal(app_self_test_get_status(&st), APP_SELF_TEST_DISABLED, "Status should be DISABLED");
}

ZTEST(self_test_suite, test_uptime_threshold)
{
    struct app_self_test st;
    app_self_test_init(&st, true, mock_confirm_fn);

    /* Uptime < 5000 ms, even with sufficient toggles (10), must NOT confirm */
    bool ok = app_self_test_update(&st, 4999, 10);
    zassert_false(ok, "Update should return false when uptime < 5000 ms");
    zassert_false(app_self_test_is_confirmed(&st), "Should not be confirmed before 5 s");
    zassert_equal(s_mock_confirm_call_count, 0, "confirm_fn should not have been called");
}

ZTEST(self_test_suite, test_toggles_threshold)
{
    struct app_self_test st;
    app_self_test_init(&st, true, mock_confirm_fn);

    /* Uptime >= 5000 ms, but toggles < 5, must NOT confirm */
    bool ok = app_self_test_update(&st, 5000, 4);
    zassert_false(ok, "Update should return false when toggles < 5");
    zassert_false(app_self_test_is_confirmed(&st), "Should not be confirmed with toggles < 5");
    zassert_equal(s_mock_confirm_call_count, 0, "confirm_fn should not have been called");
}

ZTEST(self_test_suite, test_success_confirm)
{
    struct app_self_test st;
    app_self_test_init(&st, true, mock_confirm_fn);

    /* Boundary condition: exactly 5000 ms and exactly 5 toggles -> CONFIRMED */
    bool ok = app_self_test_update(&st, 5000, 5);
    zassert_true(ok, "Update should return true when criteria met");
    zassert_true(app_self_test_is_confirmed(&st), "Should be confirmed");
    zassert_equal(app_self_test_get_status(&st), APP_SELF_TEST_CONFIRMED, "Status should be CONFIRMED");
    zassert_equal(s_mock_confirm_call_count, 1, "confirm_fn should be called exactly once");

    /* Further updates should not re-invoke confirm_fn */
    ok = app_self_test_update(&st, 6000, 7);
    zassert_true(ok, "Subsequent update should return true");
    zassert_equal(s_mock_confirm_call_count, 1, "confirm_fn should not be re-called after confirmation");
}

ZTEST(self_test_suite, test_no_confirm_variant)
{
    struct app_self_test st;
    app_self_test_init(&st, false, mock_confirm_fn);

    /* High uptime and high toggles, but can_confirm is false -> never confirms */
    bool ok = app_self_test_update(&st, 10000, 50);
    zassert_false(ok, "Update should return false for no_confirm variant");
    zassert_false(app_self_test_is_confirmed(&st), "no_confirm must stay unconfirmed");
    zassert_equal(app_self_test_get_status(&st), APP_SELF_TEST_DISABLED, "Status should remain DISABLED");
    zassert_equal(s_mock_confirm_call_count, 0, "confirm_fn must never be called for no_confirm");
}

ZTEST(self_test_suite, test_confirm_fn_error)
{
    struct app_self_test st;
    app_self_test_init(&st, true, mock_confirm_fn);
    s_mock_confirm_return_val = -5; /* Simulate boot_write_img_confirmed error (e.g. -EIO) */

    bool ok = app_self_test_update(&st, 5500, 8);
    zassert_false(ok, "Update should return false when confirm_fn returns error");
    zassert_false(app_self_test_is_confirmed(&st), "Should not be confirmed when confirm_fn fails");
    zassert_equal(app_self_test_get_status(&st), APP_SELF_TEST_FAILED, "Status should be FAILED");
    zassert_equal(st.last_error, -5, "last_error should record return code");
    zassert_equal(s_mock_confirm_call_count, 1, "confirm_fn was invoked");
}
