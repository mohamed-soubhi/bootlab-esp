/*
 * test_dispatch.c — Unity host tests for the LABID request dispatcher (BL-022).
 * Covers PLAN §7.3.2 messages, §7.3.3 error codes and §7.3.4 rules
 * (CRC-optional requests, drop-until-newline on overflow, rx_err, never reset).
 */
#include "unity.h"
#include "labid_dispatch.h"
#include <string.h>
#include <stdio.h>

static struct labid_ctx g_c;
static char g_out[LABID_MAX_FRAME + 8];

/* ---- fake providers with synthetic values ---- */
static int fake_announce(void *u, struct labid_fields *f)
{
    (void)u;
    return labid_fields_add(f, "board", "idf") | labid_fields_add(f, "uid", "E072A1AA2390")
         | labid_fields_add(f, "app", "1.0.0");
}
static int fake_id(void *u, struct labid_fields *f)
{
    (void)u;
    return labid_fields_add(f, "board", "idf") | labid_fields_add(f, "hw", "esp32s3_devkitc")
         | labid_fields_add(f, "mcu", "esp32s3") | labid_fields_add(f, "uid", "E072A1AA2390")
         | labid_fields_add(f, "os", "idf-v6.0.3") | labid_fields_add_u32(f, "flash_kb", 16384);
}
static int fake_ver(void *u, struct labid_fields *f)
{
    (void)u;
    return labid_fields_add(f, "bl", "v6.0.3") | labid_fields_add(f, "app", "1.0.0")
         | labid_fields_add(f, "git", "1c47b5c") | labid_fields_add(f, "variant", "v1")
         | labid_fields_add(f, "slot", "0") | labid_fields_add(f, "confirmed", "1");
}
static int fake_state(void *u, struct labid_fields *f)
{
    (void)u;
    return labid_fields_add_u32(f, "uptime_ms", 1234) | labid_fields_add(f, "reset", "por")
         | labid_fields_add(f, "blink_hz", "1") | labid_fields_add_u32(f, "toggles", 7);
}
static int fake_fail(void *u, struct labid_fields *f) { (void)u; (void)f; return -1; }

static const struct labid_provider PROV = {
    NULL, fake_announce, fake_id, fake_ver, fake_state
};

void setUp(void) { labid_ctx_init(&g_c, &PROV); memset(g_out, 0, sizeof g_out); }
void tearDown(void) {}

/* Feed a whole string; return the LAST non-zero response length (0 if none)
 * and count how many responses were produced. */
static int feed_str(const char *s, int *nresp)
{
    int last = 0, cnt = 0;
    for (size_t i = 0; i < strlen(s); i++) {
        int n = labid_ctx_feed(&g_c, (uint8_t)s[i], g_out, sizeof g_out);
        if (n > 0) { last = n; cnt++; }
    }
    if (nresp) { *nresp = cnt; }
    return last;
}

/* Build the expected frame with the already-tested writer. */
static void expect_frame(const char *type, const char *const *k, const char *const *v,
                         size_t n, char *dst, size_t dl)
{
    TEST_ASSERT_GREATER_THAN_INT(0, labid_build_frame(dst, dl, type, k, v, n));
}

static void assert_resp(const char *req, const char *type, const char *const *k,
                        const char *const *v, size_t n)
{
    char want[LABID_MAX_FRAME + 8];
    int cnt = 0;
    int len = feed_str(req, &cnt);
    expect_frame(type, k, v, n, want, sizeof want);
    TEST_ASSERT_EQUAL_INT(1, cnt);
    TEST_ASSERT_EQUAL_INT((int)strlen(want), len);
    TEST_ASSERT_EQUAL_STRING_LEN(want, g_out, (size_t)len);
}

/* ---- handshake / identity ---- */
void test_hello_without_crc(void)
{
    const char *k[] = {"proto"}, *v[] = {"1"};
    assert_resp("$LAB,HELLO\n", "HELLO", k, v, 1);
}

void test_id_with_spec_crc(void)
{   /* PLAN 7.3.1 example: $LAB,ID?*F9E6 */
    const char *k[] = {"board","hw","mcu","uid","os","flash_kb"};
    const char *v[] = {"idf","esp32s3_devkitc","esp32s3","E072A1AA2390","idf-v6.0.3","16384"};
    assert_resp("$LAB,ID?*F9E6\n", "ID", k, v, 6);
}

void test_id_without_crc(void)
{
    const char *k[] = {"board","hw","mcu","uid","os","flash_kb"};
    const char *v[] = {"idf","esp32s3_devkitc","esp32s3","E072A1AA2390","idf-v6.0.3","16384"};
    assert_resp("$LAB,ID?\n", "ID", k, v, 6);
}

void test_request_with_crlf_terminal(void)
{
    const char *k[] = {"proto"}, *v[] = {"1"};
    assert_resp("$LAB,HELLO\r\n", "HELLO", k, v, 1);
}

void test_ver(void)
{
    const char *k[] = {"bl","app","git","variant","slot","confirmed"};
    const char *v[] = {"v6.0.3","1.0.0","1c47b5c","v1","0","1"};
    assert_resp("$LAB,VER?\n", "VER", k, v, 6);
}

void test_state_includes_rx_err_zero(void)
{
    const char *k[] = {"uptime_ms","reset","blink_hz","toggles","rx_err"};
    const char *v[] = {"1234","por","1","7","0"};
    assert_resp("$LAB,STATE?\n", "STATE", k, v, 5);
}

void test_ping_echoes_n(void)
{
    const char *k[] = {"n"}, *v[] = {"42"};
    assert_resp("$LAB,PING,n=42\n", "PONG", k, v, 1);
}

/* ---- errors: every one must answer ERR, count rx_err, and never reset ---- */
static void assert_err(const char *req, const char *code)
{
    const char *k[] = {"code"}; const char *v[1]; v[0] = code;
    assert_resp(req, "ERR", k, v, 1);
}

void test_ping_missing_n_is_syntax(void)   { assert_err("$LAB,PING\n", "syntax"); }
void test_ping_non_numeric_n_is_syntax(void){ assert_err("$LAB,PING,n=abc\n", "syntax"); }
void test_unknown_request(void)            { assert_err("$LAB,BOGUS\n", "unknown"); }
void test_bad_crc(void)                    { assert_err("$LAB,ID?*0000\n", "crc"); }
void test_dollar_garbage_is_syntax(void)   { assert_err("$garbage\n", "syntax"); }

void test_overflow_answers_len_once_and_drops_rest_of_line(void)
{
    char big[300];
    int cnt = 0;
    big[0] = '$';
    memset(big + 1, 'A', 250);
    big[251] = '$';                 /* a '$' inside the dropped tail must NOT start a frame */
    memcpy(big + 252, "LAB,ID?\n", 9);
    const char *k[] = {"code"}, *v[] = {"len"};
    char want[LABID_MAX_FRAME + 8];
    int len = feed_str(big, &cnt);
    expect_frame("ERR", k, v, 1, want, sizeof want);
    TEST_ASSERT_EQUAL_INT(1, cnt);   /* one ERR total: the tail produced nothing */
    TEST_ASSERT_EQUAL_STRING_LEN(want, g_out, (size_t)len);
}

void test_recovers_after_overflow(void)
{
    char big[260];
    int cnt = 0;
    big[0] = '$'; memset(big + 1, 'A', 250); big[251] = '\n'; big[252] = 0;
    (void)feed_str(big, &cnt);
    const char *k[] = {"proto"}, *v[] = {"1"};
    assert_resp("$LAB,HELLO\n", "HELLO", k, v, 1);
}

void test_rx_err_counts_rejected_frames(void)
{
    int cnt = 0;
    (void)feed_str("$LAB,ID?*0000\n", &cnt);
    (void)feed_str("$garbage\n", &cnt);
    const char *k[] = {"uptime_ms","reset","blink_hz","toggles","rx_err"};
    const char *v[] = {"1234","por","1","7","2"};
    assert_resp("$LAB,STATE?\n", "STATE", k, v, 5);
}

/* ---- non-frames are ignored ---- */
void test_log_lines_are_ignored(void)
{
    int cnt = 0;
    (void)feed_str("I (5) blink: on $LAB,ID?\n", &cnt);   /* '$' mid-line is not a frame */
    (void)feed_str("\xff\xfe\x01garbage bytes\n", &cnt);
    TEST_ASSERT_EQUAL_INT(0, cnt);
    TEST_ASSERT_EQUAL_UINT32(0, g_c.rx_err);
}

/* ---- announce ---- */
void test_announce_frame(void)
{
    const char *k[] = {"proto","board","uid","app"};
    const char *v[] = {"1","idf","E072A1AA2390","1.0.0"};
    char want[LABID_MAX_FRAME + 8];
    int len = labid_announce(&g_c, g_out, sizeof g_out);
    expect_frame("ANNOUNCE", k, v, 4, want, sizeof want);
    TEST_ASSERT_EQUAL_INT((int)strlen(want), len);
    TEST_ASSERT_EQUAL_STRING_LEN(want, g_out, (size_t)len);
}

/* ---- robustness ---- */
void test_response_too_big_for_buffer_returns_zero(void)
{
    char tiny[8];
    int n = 0;
    const char *s = "$LAB,ID?\n";
    for (size_t i = 0; i < strlen(s); i++) { n = labid_ctx_feed(&g_c, (uint8_t)s[i], tiny, sizeof tiny); }
    TEST_ASSERT_EQUAL_INT(0, n);
}

void test_provider_failure_answers_err_not_silence(void)
{
    static const struct labid_provider bad = { NULL, fake_fail, fake_fail, fake_fail, fake_fail };
    labid_ctx_init(&g_c, &bad);
    assert_err("$LAB,ID?\n", "unknown");
}

void test_fields_add_rejects_overlong_value_and_full_list(void)
{
    struct labid_fields f; f.n = 0;
    char longv[LABID_VAL_MAX + 5];
    memset(longv, 'a', sizeof longv - 1); longv[sizeof longv - 1] = 0;
    TEST_ASSERT_EQUAL_INT(-1, labid_fields_add(&f, "k", longv));
    for (size_t i = 0; i < LABID_MAX_FIELDS; i++) { TEST_ASSERT_EQUAL_INT(0, labid_fields_add(&f, "k", "v")); }
    TEST_ASSERT_EQUAL_INT(-1, labid_fields_add(&f, "k", "v"));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_hello_without_crc);
    RUN_TEST(test_id_with_spec_crc);
    RUN_TEST(test_id_without_crc);
    RUN_TEST(test_request_with_crlf_terminal);
    RUN_TEST(test_ver);
    RUN_TEST(test_state_includes_rx_err_zero);
    RUN_TEST(test_ping_echoes_n);
    RUN_TEST(test_ping_missing_n_is_syntax);
    RUN_TEST(test_ping_non_numeric_n_is_syntax);
    RUN_TEST(test_unknown_request);
    RUN_TEST(test_bad_crc);
    RUN_TEST(test_dollar_garbage_is_syntax);
    RUN_TEST(test_overflow_answers_len_once_and_drops_rest_of_line);
    RUN_TEST(test_recovers_after_overflow);
    RUN_TEST(test_rx_err_counts_rejected_frames);
    RUN_TEST(test_log_lines_are_ignored);
    RUN_TEST(test_announce_frame);
    RUN_TEST(test_response_too_big_for_buffer_returns_zero);
    RUN_TEST(test_provider_failure_answers_err_not_silence);
    RUN_TEST(test_fields_add_rejects_overlong_value_and_full_list);
    return UNITY_END();
}
