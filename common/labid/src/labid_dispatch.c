/*
 * labid_dispatch.c — LABID request dispatcher (BL-022). Spec: PLAN §7.3.
 * Portable C99, no malloc, no RTOS calls, fixed buffers.
 */
#include "labid_dispatch.h"
#include <string.h>

#define U32_MAX_DIGITS 10u

/* ---------- field list ---------- */
int labid_fields_add(struct labid_fields *f, const char *key, const char *val)
{
    if (!f || !key || !val || f->n >= LABID_MAX_FIELDS) { return -1; }
    size_t l = strlen(val);
    if (l >= LABID_VAL_MAX) { return -1; }
    memcpy(f->val[f->n], val, l + 1u);
    f->key[f->n] = key;
    f->n++;
    return 0;
}

int labid_fields_add_u32(struct labid_fields *f, const char *key, uint32_t val)
{
    char tmp[U32_MAX_DIGITS + 1u];
    size_t i = sizeof tmp - 1u;
    tmp[i] = '\0';
    do {
        tmp[--i] = (char)('0' + (val % 10u));
        val /= 10u;
    } while (val != 0u);
    return labid_fields_add(f, key, &tmp[i]);
}

/* ---------- frame emission ---------- */
static int emit(char *out, size_t outlen, const char *type, const struct labid_fields *f)
{
    const char *keys[LABID_MAX_FIELDS];
    const char *vals[LABID_MAX_FIELDS];
    for (size_t i = 0; i < f->n; i++) {
        keys[i] = f->key[i];
        vals[i] = f->val[i];
    }
    int n = labid_build_frame(out, outlen, type, keys, vals, f->n);
    return (n > 0) ? n : 0;   /* 0 = does not fit; never partially written */
}

static int emit_err(struct labid_ctx *c, const char *code, char *out, size_t outlen)
{
    struct labid_fields f;
    f.n = 0;
    c->rx_err++;
    (void)labid_fields_add(&f, "code", code);
    return emit(out, outlen, "ERR", &f);
}

static const char *err_code(int parser_err)
{
    switch (parser_err) {
    case LABID_ERR_CRC: return "crc";
    case LABID_ERR_LEN: return "len";
    default:            return "syntax";
    }
}

/* ---------- request handling ---------- */
static int type_is(const char *t, int n, const char *want)
{
    size_t wl = strlen(want);
    return (n >= 0) && ((size_t)n == wl) && (memcmp(t, want, wl) == 0);
}

/* Answer a provider-backed query; unavailable data is reported, not ignored. */
static int answer_query(struct labid_ctx *c, labid_provide_fn fn, const char *type,
                        int add_rx_err, char *out, size_t outlen)
{
    struct labid_fields f;
    f.n = 0;
    if (!fn || fn(c->prov->user, &f) < 0) { return emit_err(c, "unknown", out, outlen); }
    if (add_rx_err && labid_fields_add_u32(&f, "rx_err", c->rx_err) < 0) {
        return emit_err(c, "unknown", out, outlen);
    }
    return emit(out, outlen, type, &f);
}

/* Parse a decimal u32 from a frame value; returns 0 on success. */
static int parse_u32(const char *s, int n, uint32_t *v)
{
    uint64_t acc = 0;
    if (n < 1 || (size_t)n > U32_MAX_DIGITS) { return -1; }
    for (int i = 0; i < n; i++) {
        if (s[i] < '0' || s[i] > '9') { return -1; }
        acc = acc * 10u + (uint64_t)(s[i] - '0');
    }
    if (acc > 0xFFFFFFFFu) { return -1; }
    *v = (uint32_t)acc;
    return 0;
}

static int answer_ping(struct labid_ctx *c, char *out, size_t outlen)
{
    const char *s = NULL;
    int n = 0;
    uint32_t v = 0;
    struct labid_fields f;
    f.n = 0;
    if (!labid_frame_get(&c->p, "n", &s, &n) || parse_u32(s, n, &v) < 0) {
        return emit_err(c, "syntax", out, outlen);
    }
    (void)labid_fields_add_u32(&f, "n", v);
    return emit(out, outlen, "PONG", &f);
}

static int handle_frame(struct labid_ctx *c, char *out, size_t outlen)
{
    const char *t = NULL;
    int n = 0;
    struct labid_fields f;
    f.n = 0;
    labid_frame_type(&c->p, &t, &n);
    if (!t) { return emit_err(c, "syntax", out, outlen); }

    if (type_is(t, n, "HELLO")) {
        (void)labid_fields_add_u32(&f, "proto", LABID_PROTO_VERSION);
        return emit(out, outlen, "HELLO", &f);
    }
    if (type_is(t, n, "ID?"))    { return answer_query(c, c->prov->id,    "ID",    0, out, outlen); }
    if (type_is(t, n, "VER?"))   { return answer_query(c, c->prov->ver,   "VER",   0, out, outlen); }
    if (type_is(t, n, "STATE?")) { return answer_query(c, c->prov->state, "STATE", 1, out, outlen); }
    if (type_is(t, n, "PING"))   { return answer_ping(c, out, outlen); }
    return emit_err(c, "unknown", out, outlen);
}

/* ---------- public API ---------- */
void labid_ctx_init(struct labid_ctx *c, const struct labid_provider *prov)
{
    if (!c) { return; }
    labid_parser_init_device(&c->p);
    c->prov = prov;
    c->rx_err = 0;
}

int labid_ctx_feed(struct labid_ctx *c, uint8_t ch, char *out, size_t outlen)
{
    if (!c || !c->prov || !out) { return 0; }
    int rc = labid_feed(&c->p, ch);
    if (rc == LABID_FEED_ERROR) {
        return emit_err(c, err_code(labid_parser_err(&c->p)), out, outlen);
    }
    if (rc != LABID_FEED_FRAME) { return 0; }
    return handle_frame(c, out, outlen);
}

int labid_announce(const struct labid_ctx *c, char *out, size_t outlen)
{
    struct labid_fields f;
    f.n = 0;
    if (!c || !c->prov || !out) { return -1; }
    (void)labid_fields_add_u32(&f, "proto", LABID_PROTO_VERSION);
    if (c->prov->announce && c->prov->announce(c->prov->user, &f) < 0) { return -1; }
    int n = emit(out, outlen, "ANNOUNCE", &f);
    return (n > 0) ? n : -1;
}
