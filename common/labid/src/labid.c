/*
 * labid.c — LABID serial identity protocol: CRC-16, writer, parser.
 * Portable C99. No malloc, no RTOS calls, fixed buffers.
 */
#include "labid.h"
#include <string.h>
#include <ctype.h>

/* ---------- CRC-16/CCITT-FALSE ---------- */
uint16_t labid_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFu;
    while (len--) {
        crc ^= (*data++ << 8);
        for (int b = 0; b < 8; b++) {
            if (crc & 0x8000u) {
                crc = (uint16_t)((crc << 1) ^ 0x1021u);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

/* ---------- internal helpers ---------- */
static int hexval(char c)
{
    if (c >= '0' && c <= '9') { return c - '0'; }
    if (c >= 'A' && c <= 'F') { return c - 'A' + 10; }
    if (c >= 'a' && c <= 'f') { return c - 'a' + 10; }
    return -1;
}

static int valid_type_key(const char *s, int len, int is_key)
{
    /* keys: [a-z0-9_]; values: [A-Za-z0-9._:-]; type: same as key */
    for (int i = 0; i < len; i++) {
        char c = s[i];
        if (is_key) {
            int ok = (c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_';
            if (!ok) { return 0; }
        } else {
            int ok = (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')
                  || c=='.'||c=='_'||c==':'||c=='-';
            if (!ok) { return 0; }
        }
    }
    return 1;
}

/* ---------- Writer ---------- */
int labid_build_frame(char *buf, size_t buflen,
                      const char *type,
                      const char *const *keys,
                      const char *const *values,
                      size_t n)
{
    size_t pos = 0;

    if (!buf || !type || (n && (!keys || !values))) { return -1; }

    /* We must build the payload, CRC it, then write header+payload+crc+\n.
     * To stay within buflen and produce the CRC over the payload between
     * '$' and '*', assemble into a temp then verify length.
     */
    char payload[LABID_MAX_FRAME];
    size_t plen = 0;
    /* payload: "LAB,<type>,<k>=<v>,..." */
    const char *parts[] = { "LAB,", type, NULL };
    for (int i=0; i<2; i++) {
        size_t l = strlen(parts[i]);
        if (plen + l + 1 > sizeof(payload)) { return -1; }
        memcpy(payload+plen, parts[i], l); plen += l;
    }
    for (size_t i=0; i<n; i++) {
        const char *k = keys[i] ? keys[i] : "";
        const char *v = values[i] ? values[i] : "";
        size_t kl = strlen(k), vl = strlen(v);
        if (plen + 1 + kl + 1 + vl > sizeof(payload)) { return -1; }
        if (!valid_type_key(k,(int)kl,1)) { return -1; }
        payload[plen++] = ',';
        memcpy(payload+plen, k, kl); plen += kl;
        payload[plen++] = '=';
        if (!valid_type_key(v,(int)vl,0)) { return -1; }
        memcpy(payload+plen, v, vl); plen += vl;
    }

    uint16_t crc = labid_crc16((const uint8_t*)payload, plen);

    /* final frame: '$' + payload + '*' + 4-hex-crc + '\n' (+NUL) */
    size_t need = 1 + plen + 1 + 4 + 2; /* $ ... *XXXX\n\0 */
    if (need > buflen || need > LABID_MAX_FRAME + 2u) { return -1; }

    pos = 0;
    buf[pos++] = '$';
    memcpy(buf+pos, payload, plen); pos += plen;
    buf[pos++] = '*';
    static const char hex[] = "0123456789ABCDEF";
    buf[pos++] = hex[(crc>>12)&0xF];
    buf[pos++] = hex[(crc>>8)&0xF];
    buf[pos++] = hex[(crc>>4)&0xF];
    buf[pos++] = hex[crc&0xF];
    buf[pos++] = '\n';
    buf[pos] = '\0';
    return (int)pos;
}

/* ---------- Parser ---------- */
static void hex_to_bytes(const char *s, uint8_t *hi, uint8_t *lo)
{
    *hi = (uint8_t)((hexval(s[0])<<4)|hexval(s[1]));
    *lo = (uint8_t)((hexval(s[2])<<4)|hexval(s[3]));
}

int labid_feed(struct labid_parser *p, uint8_t ch)
{
    if (!p) { return LABID_FEED_ERROR; }

    /* not started: only a '$' at line start matters */
    if (!p->started) {
        if (ch == '\n') {
            p->started = 0; p->len = 0; p->skip = 0;
            return LABID_FEED_IGNORED;
        }
        if (p->skip) { return LABID_FEED_IGNORED; }   /* device mode: dropping this line */
        if (ch == '$') {
            p->started = 1;
            p->buf[0] = (char)ch;   /* store '$' so payload starts at buf[1] */
            p->len = 1;
            p->crc_ok = 0;
            p->err = LABID_ERR_NONE;
        } else if (p->accept_nocrc) {
            p->skip = 1;            /* line does not start with '$': a log line */
        }
        return LABID_FEED_IGNORED;
    }

    /* building the line */
    if (ch == '\n') {
        /* end of frame: must have '*XXXX' at end after start; validate CRC */
        int done = labid_parser_end(p);
        p->started = 0;
        return done;
    }
    if (p->len >= sizeof(p->buf) - 1u) {
        /* overflow -> drop until \n */
        p->started = 0; p->len = 0;
        p->err = LABID_ERR_LEN;
        if (p->accept_nocrc) { p->skip = 1; }
        return LABID_FEED_ERROR;
    }
    p->buf[p->len++] = (char)ch;
    return LABID_FEED_IGNORED;
}

/* Internal: finalize a frame at the terminal '\n'. Validates structure + CRC.
 * Returns LABID_FEED_FRAME on a valid complete frame, LABID_FEED_ERROR on bad CRC/
 * syntax, LABID_FEED_IGNORED for a line that isn't a frame (no '*' CRC).
 */
int labid_parser_end(struct labid_parser *p)
{
    /* device mode: tolerate a terminal that sends "\r\n" */
    if (p->accept_nocrc && p->len > 0 && p->buf[p->len - 1] == '\r') { p->len--; }
    /* frame == $ <payload> * <4hex> */
    if (p->len < 3) { p->len = 0; return LABID_FEED_IGNORED; }
    /* find last '*' */
    int star = -1;
    for (size_t i = 1; i < p->len; i++) { if (p->buf[i]=='*') star = (int)i; }
    if (star < 0) {
        if (p->accept_nocrc) {
            /* host request without CRC (PLAN 7.3.1): accept "$LAB,..." as a frame;
             * crc_ok stays 0 (a wrong CRC is an error, an absent one is not) */
            if (p->len >= 5 && memcmp(&p->buf[1], "LAB,", 4) == 0) { return LABID_FEED_FRAME; }
            p->len = 0; p->err = LABID_ERR_SYNTAX;
            return LABID_FEED_ERROR;
        }
        /* not a LABID frame (no CRC); treat as ignored log line */
        p->len = 0;
        return LABID_FEED_IGNORED;
    }
    /* need at least 4 hex chars after '*', and 'LAB,' prefix check */
    if ((int)p->len - star - 1 < 4) { p->len = 0; p->err = LABID_ERR_SYNTAX; return LABID_FEED_ERROR; }
    /* CRC chars */
    const char *cr = &p->buf[star+1];
    for (int i=0;i<4;i++) if (hexval(cr[i])<0) { p->len=0; p->err = LABID_ERR_SYNTAX; return LABID_FEED_ERROR; }
    hex_to_bytes(cr, &p->crc_hi, &p->crc_lo);
    uint16_t crc = (uint16_t)(p->crc_hi<<8 | p->crc_lo);
    /* payload = buf[1..star-1] */
    uint16_t calc = labid_crc16((const uint8_t*)&p->buf[1], (size_t)(star-1));
    p->crc_ok = (calc == crc) ? 1 : 0;
    if (!p->crc_ok) { p->len = 0; p->err = LABID_ERR_CRC; return LABID_FEED_ERROR; }
    /* success: keep frame in p->buf; payload spans buf[1..star-1],
     * buf[0] is the leading '$'. Trim the trailing CRC (leave at buffer end). */
    p->len = (size_t)star;   /* index of '*' — payload is buf[1..star-1] */
    return LABID_FEED_FRAME;
}

void labid_frame_type(const struct labid_parser *p, const char **s, int *n)
{
    /* frame = '$' + "LAB,<type>,..." ; type begins at buf[1+4] */
    *s = NULL; *n = 0;
    if (!p || p->len < 5) return;
    if (memcmp(&p->buf[1], "LAB,", 4) != 0) return;   /* buf[0]='$' */
    size_t i = 1 + 4;
    while (i < p->len && p->buf[i] != ',') i++;
    *s = &p->buf[5]; *n = (int)(i - 5);
}

int labid_frame_get(const struct labid_parser *p, const char *key,
                    const char **val, int *vlen)
{
    if (!p || !key) return 0;
    size_t kl = strlen(key);
    if (!kl) return 0;
    /* frame = '$' + "LAB,type,<k=v>,..." ; payload starts at buf[1] */
    size_t n = p->len;
    if (n < 1 || p->buf[0] != '$') return 0;
    if (n < 5 || memcmp(&p->buf[1], "LAB,", 4) != 0) return 0;
    size_t pos = 1 + 4;
    /* skip type */
    while (pos < n && p->buf[pos] != ',') pos++;
    if (pos < n) pos++;   /* skip ',' */
    else return 0;
    while (pos < n) {
        size_t eq = pos;
        while (eq < n && p->buf[eq] != '=') eq++;
        if (eq >= n) return 0;
        size_t k_start = pos, k_len = eq - pos;
        pos = eq + 1;
        size_t v_start = pos;
        while (pos < n && p->buf[pos] != ',') pos++;
        size_t v_len = pos - v_start;
        if (pos < n) pos++;   /* skip ',' */
        if (k_len == kl && memcmp(&p->buf[k_start], key, kl) == 0) {
            *val = &p->buf[v_start]; *vlen = (int)v_len;
            return 1;
        }
    }
    return 0;
}

int labid_frame_crc_ok(const struct labid_parser *p)
{
    return p ? p->crc_ok : 0;
}

void labid_parser_init(struct labid_parser *p)
{
    if (!p) return;
    p->len = 0; p->started = 0; p->crc_ok = 0;
    p->crc_hi = p->crc_lo = 0;
    p->accept_nocrc = 0; p->skip = 0; p->err = LABID_ERR_NONE;
}

void labid_parser_init_device(struct labid_parser *p)
{
    if (!p) return;
    labid_parser_init(p);
    p->accept_nocrc = 1;
}

int labid_parser_err(const struct labid_parser *p)
{
    return p ? p->err : LABID_ERR_NONE;
}
