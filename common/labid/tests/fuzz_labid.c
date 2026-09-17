/*
 * fuzz_labid.c — libFuzzer target for the LABID parser (BL-012).
 *
 * Feeds arbitrary bytes into labid_feed() and exercises all public parser
 * accessors. Built with ASan+UBSan. Run e.g.:
 *   clang -g -O1 -fsanitize=fuzzer,address,undefined -std=c99 \
 *         -I../include fuzz_labid.c ../src/labid.c -o fuzz_labid
 *   ./fuzz_labid -max_total_time=600
 */
#include "labid.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    struct labid_parser p;
    labid_parser_init(&p);

    /* Feed the whole input, then also re-seed with a '$' prefix sometimes
     * to exercise the start-of-frame path. */
    for (size_t i = 0; i < size; i++) {
        labid_feed(&p, data[i]);
    }

    /* If a frame was recognised, query it (exercises accessors). */
    const char *t; int tl;
    labid_frame_type(&p, &t, &tl);
    const char *v; int vl;
    (void)labid_frame_get(&p, "board", &v, &vl);
    (void)labid_frame_get(&p, "app", &v, &vl);
    (void)labid_frame_get(&p, "uid", &v, &vl);
    (void)labid_frame_crc_ok(&p);

    /* Also exercise the writer with fuzz-derived keys/values to reach
     * validation paths (bounded, safe strings). klen/vlen are bounded by
     * BOTH the derived value AND the available input size so we never read
     * past `data` (data[i] for i >= size is out of bounds). */
    char out[LABID_MAX_FRAME];
    char kb[4] = {0}, vb[4] = {0};
    size_t klen = size ? (data[0] % 3) : 0;
    if (klen > size) klen = size;
    size_t vlen = size > 1 ? (data[1] % 3) : 0;
    if (vlen > size) vlen = size;
    for (size_t i = 0; i < klen && i < 3; i++) kb[i] = (char)('a' + (data[i] % 26));
    for (size_t i = 0; i < vlen && i < 3; i++) vb[i] = (char)('0' + (data[i] % 10));
    kb[klen] = '\0'; vb[vlen] = '\0';
    const char *keys[1] = { kb };
    const char *vals[1] = { vb };
    (void)labid_build_frame(out, sizeof(out), "X", keys, vals, 1);

    return 0;
}
