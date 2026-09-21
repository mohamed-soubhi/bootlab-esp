/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * main.c — native_sim smoke test for the LABID Zephyr module (BL-014b).
 *
 * Proves the packaged Zephyr module builds AND behaves on native_sim:
 *   1. labid.c: CRC check vector + frame writer (PLAN 7.3.1)
 *   2. labid_dispatch.c: request -> response through a fake provider (PLAN 7.3.2)
 * Exits with status 0 only if every check passes.
 */

#include <zephyr/kernel.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "labid.h"
#include "labid_dispatch.h"

#ifdef CONFIG_ARCH_POSIX
extern void posix_exit(int exit_code);
#endif

static int fake_id(void *user, struct labid_fields *f)
{
    (void)user;
    return labid_fields_add(f, "board", "zephyr") | labid_fields_add(f, "uid", "ACA7042C3B04");
}

static const struct labid_provider PROV = { NULL, NULL, fake_id, NULL, NULL };

/* Feed a whole request; return the response length (0 if none). */
static int request(struct labid_ctx *c, const char *req, char *out, size_t outlen)
{
    int len = 0;
    for (size_t i = 0; i < strlen(req); i++) {
        int n = labid_ctx_feed(c, (uint8_t)req[i], out, outlen);
        if (n > 0) {
            len = n;
        }
    }
    return len;
}

int main(void)
{
    int failures = 0;

    /* 1. writer + CRC */
    const char *keys[] = {"bl", "app", "slot"};
    const char *vals[] = {"1.0.0", "2.0.0", "0"};
    char buf[LABID_MAX_FRAME];
    int n = labid_build_frame(buf, sizeof(buf), "VER", keys, vals, 3);
    printf("n=%d\n", n);
    if (n <= 0) {
#ifdef CONFIG_ARCH_POSIX
        posix_exit(1);
#else
        exit(1);
#endif
    }
    fputs(buf, stdout);
    uint16_t crc = labid_crc16((const uint8_t *)"123456789", 9);
    printf("crc=0x%04X\n", crc);
    if (crc != 0x29B1u) {
        printf("FAIL crc check vector\n");
        failures++;
    }

    /* 2. dispatcher: CRC-less request, provider answer, and an error path */
    struct labid_ctx ctx;
    char out[LABID_MAX_FRAME + 8];
    labid_ctx_init(&ctx, &PROV);

    int len = request(&ctx, "$LAB,HELLO\n", out, sizeof out);
    printf("HELLO -> %s", len > 0 ? out : "(none)\n");
    if (len <= 0 || strstr(out, "$LAB,HELLO,proto=1*") != out) {
        printf("FAIL HELLO\n");
        failures++;
    }

    len = request(&ctx, "$LAB,ID?\n", out, sizeof out);
    printf("ID?   -> %s", len > 0 ? out : "(none)\n");
    if (len <= 0 || strstr(out, "board=zephyr") == NULL || strstr(out, "uid=ACA7042C3B04") == NULL) {
        printf("FAIL ID?\n");
        failures++;
    }

    len = request(&ctx, "$LAB,BOGUS\n", out, sizeof out);
    printf("BOGUS -> %s", len > 0 ? out : "(none)\n");
    if (len <= 0 || strstr(out, "code=unknown") == NULL) {
        printf("FAIL unknown request must answer ERR\n");
        failures++;
    }

    printf(failures ? "%d FAILED\n" : "zephyr-native smoke: all checks passed\n", failures);
#ifdef CONFIG_ARCH_POSIX
    posix_exit(failures ? 1 : 0);
#else
    exit(failures ? 1 : 0);
#endif
    return failures ? 1 : 0;
}
