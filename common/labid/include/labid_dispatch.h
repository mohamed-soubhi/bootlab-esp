/*
 * labid_dispatch.h — LABID request dispatcher (portable C99, no malloc, no RTOS)
 *
 * Spec: PLAN §7.3.2 / §7.3.3 / §7.3.4. Turns a stream of received bytes into
 * response frames. Platform glue (Zephyr / ESP-IDF) supplies field values via
 * provider callbacks and writes the returned frame in a single atomic write.
 *
 * Host requests may omit the CRC ("$LAB,ID?"); device responses always carry it.
 */
#ifndef LABID_DISPATCH_H
#define LABID_DISPATCH_H

#include "labid.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LABID_PROTO_VERSION  1
#define LABID_MAX_FIELDS     12u
#define LABID_VAL_MAX        40u   /* value chars + NUL */

/* Fixed-size key/value list filled by provider callbacks. Keys must be string
 * literals (they are not copied); values are copied. */
struct labid_fields {
    size_t      n;
    const char *key[LABID_MAX_FIELDS];
    char        val[LABID_MAX_FIELDS][LABID_VAL_MAX];
};

/* Append key=value. Returns 0 on success, -1 if full or the value is too long. */
int labid_fields_add(struct labid_fields *f, const char *key, const char *val);
/* Append key=<decimal u32>. Same return values. */
int labid_fields_add_u32(struct labid_fields *f, const char *key, uint32_t val);

/* Each callback fills 'out' and returns 0, or <0 if the data is unavailable. */
typedef int (*labid_provide_fn)(void *user, struct labid_fields *out);

struct labid_provider {
    void            *user;
    labid_provide_fn announce; /* board, uid, app  (dispatcher adds proto) */
    labid_provide_fn id;       /* board, hw, mcu, uid, os, flash_kb */
    labid_provide_fn ver;      /* bl, app, git, build, variant, slot, confirmed */
    labid_provide_fn state;    /* uptime_ms, reset, blink_hz, toggles (dispatcher adds rx_err) */
};

struct labid_ctx {
    struct labid_parser          p;
    const struct labid_provider *prov;
    uint32_t                     rx_err;  /* rejected frames since boot */
};

void labid_ctx_init(struct labid_ctx *c, const struct labid_provider *prov);

/*
 * Feed one received byte. Returns the length of a response frame written into
 * 'out' (to be sent with ONE write), or 0 if there is nothing to send yet.
 * Also returns 0 if the response would not fit in 'outlen'.
 * Lines that do not start with '$' are ignored. Never blocks, never resets.
 */
int labid_ctx_feed(struct labid_ctx *c, uint8_t ch, char *out, size_t outlen);

/* Build the once-per-boot ANNOUNCE frame. Returns its length, or <0 on error. */
int labid_announce(const struct labid_ctx *c, char *out, size_t outlen);

#ifdef __cplusplus
}
#endif

#endif /* LABID_DISPATCH_H */
