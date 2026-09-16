/*
 * test_labid.c — Unity host tests for the LABID library (BL-011).
 * Golden vectors mirror common/labid/test_vectors.json (CRC-16/CCITT-FALSE).
 *
 * Build (see CMakeLists.txt): needs the Unity framework.
 */
#include "unity.h"
#include "labid.h"
#include <string.h>

static struct labid_parser g_p;

static void feed_capture(const char *frame, int *final_rc, int *saw_error)
{
    int rc = LABID_FEED_IGNORED;
    int err = 0;
    labid_parser_init(&g_p);
    size_t n = strlen(frame);
    for (size_t i = 0; i < n; i++) {
        rc = labid_feed(&g_p, (uint8_t)frame[i]);
        if (rc == LABID_FEED_ERROR) { err = 1; }
    }
    *final_rc = rc;
    if (saw_error) { *saw_error = err; }
}

/* ---- CRC check vector ---- */
void test_crc_check_vector(void)
{
    TEST_ASSERT_EQUAL_UINT16(0x29B1u, labid_crc16((const uint8_t*)"123456789", 9));
}

/* ---- valid frames parse + correct CRC + fields ---- */
void test_valid_frames_parse(void)
{
    const char *valid[] = {
        "$LAB,ID,board=zephyr,hw=esp32s3_devkitc,mcu=esp32s3,uid=aca7042c3b04,os=zephyr-4.1.0,flash_kb=16384*0A22\n",
        "$LAB,VER,bl=1.0.0,app=2.0.0,git=9f3c2e1,build=20260916T1030Z,variant=v2,slot=0,confirmed=1*A8C7\n",
        "$LAB,PONG,n=42*D6A8\n",
        "$LAB,ANNOUNCE,proto=1,board=zephyr,uid=aca7042c3b04,app=2.0.0*6271\n",
        "$LAB,ID?,*7DD8\n"
    };
    for (size_t i = 0; i < sizeof(valid)/sizeof(valid[0]); i++) {
        int rc = LABID_FEED_IGNORED;
        feed_capture(valid[i], &rc, NULL);
        TEST_ASSERT_EQUAL_INT(LABID_FEED_FRAME, rc);
        TEST_ASSERT_TRUE(labid_frame_crc_ok(&g_p));
    }
}

void test_parse_fields(void)
{
    int ignored = 0;
    feed_capture(
        "$LAB,ID,board=zephyr,hw=esp32s3_devkitc,mcu=esp32s3,uid=aca7042c3b04,os=zephyr-4.1.0,flash_kb=16384*0A22\n",
        &ignored, NULL);
    const char *t; int tl;
    labid_frame_type(&g_p, &t, &tl);
    TEST_ASSERT_EQUAL_INT(2, tl);
    TEST_ASSERT_EQUAL_INT(0, memcmp(t, "ID", 2));

    const char *v; int vl;
    TEST_ASSERT_TRUE(labid_frame_get(&g_p, "board", &v, &vl));
    TEST_ASSERT_EQUAL_INT(6, vl);
    TEST_ASSERT_EQUAL_INT(0, memcmp(v, "zephyr", 6));
    TEST_ASSERT_TRUE(labid_frame_get(&g_p, "uid", &v, &vl));
    TEST_ASSERT_EQUAL_INT(12, vl);
}

/* ---- writer golden frame ---- */
void test_writer_golden_ver(void)
{
    const char *keys[] = {"bl","app","git","build","variant","slot","confirmed"};
    const char *vals[] = {"1.0.0","2.0.0","9f3c2e1","20260916T1030Z","v2","0","1"};
    char buf[LABID_MAX_FRAME];
    int n = labid_build_frame(buf, sizeof(buf), "VER", keys, vals, 7);
    const char *gold = "$LAB,VER,bl=1.0.0,app=2.0.0,git=9f3c2e1,build=20260916T1030Z,variant=v2,slot=0,confirmed=1*A8C7\n";
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_EQUAL_STRING(gold, buf);
}

/* ---- bad CRC rejected ---- */
void test_bad_crc_rejected(void)
{
    const char *bad[] = {
        "$LAB,VER,bl=1.0.0,app=2.0.0,variant=v2*0000\n",
        "$LAB,PONG,n=42*0000\n"
    };
    for (size_t i = 0; i < sizeof(bad)/sizeof(bad[0]); i++) {
        int rc = LABID_FEED_IGNORED;
        feed_capture(bad[i], &rc, NULL);
        TEST_ASSERT_EQUAL_INT(LABID_FEED_ERROR, rc);
    }
}

/* ---- unknown keys ignored, valid CRC still parses ---- */
void test_unknown_keys_ignored(void)
{
    int rc = LABID_FEED_IGNORED;
    feed_capture("$LAB,ID,board=zephyr,uid=aca7042c3b04,extra=ignore*1632\n", &rc, NULL);
    TEST_ASSERT_EQUAL_INT(LABID_FEED_FRAME, rc);
    TEST_ASSERT_TRUE(labid_frame_crc_ok(&g_p));
    const char *v; int vl;
    /* unknown key: should NOT be returned as a known field, but we just need
     * known one present */
    TEST_ASSERT_TRUE(labid_frame_get(&g_p, "board", &v, &vl));
}

/* ---- too-long frame overflow -> error ---- */
void test_too_long_overflow(void)
{
    /* >200-byte frame (matches test_vectors.json too_long) */
    const char *longframe =
        "$LAB,VER,k0=v0,k1=v1,k2=v2,k3=v3,k4=v4,k5=v5,k6=v6,k7=v7,k8=v8,k9=v9,"
        "k10=v10,k11=v11,k12=v12,k13=v13,k14=v14,k15=v15,k16=v16,k17=v17,k18=v18,k19=v19,"
        "k20=v20,k21=v21,k22=v22,k23=v23,k24=v24,k25=v25,k26=v26,k27=v27,k28=v28,k29=v29,*A5FE\n";
    TEST_ASSERT_TRUE(strlen(longframe) > 200);
    int rc = LABID_FEED_IGNORED;
    int saw_err = 0;
    feed_capture(longframe, &rc, &saw_err);
    TEST_ASSERT_EQUAL_INT(1, saw_err);
}

/* ---- garbage / non-frames ignored ---- */
void test_garbage_ignored(void)
{
    int rc = LABID_FEED_IGNORED;
    feed_capture("normal log line, not a frame\n", &rc, NULL);
    TEST_ASSERT_EQUAL_INT(LABID_FEED_IGNORED, rc);
    feed_capture("\r\n\n", &rc, NULL);
    TEST_ASSERT_EQUAL_INT(LABID_FEED_IGNORED, rc);
}

/* ---- UNIT framework entry point ---- */
void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_crc_check_vector);
    RUN_TEST(test_valid_frames_parse);
    RUN_TEST(test_parse_fields);
    RUN_TEST(test_writer_golden_ver);
    RUN_TEST(test_bad_crc_rejected);
    RUN_TEST(test_unknown_keys_ignored);
    RUN_TEST(test_too_long_overflow);
    RUN_TEST(test_garbage_ignored);
    return UNITY_END();
}
