/*
 * labid.h — LABID serial identity protocol (portable C99)
 *
 * Spec: PLAN §7.3
 *   Frame:  $LAB,<TYPE>,<key>=<value>,...*<CRC16>\n
 *   CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over bytes between '$' and '*',
 *   printed as 4 uppercase hex.  Check: CRC("123456789") = 0x29B1.
 *   Max frame: 200 bytes.  Keys [a-z0-9_], values [A-Za-z0-9._:-].
 *
 * Constraints: portable C99, no malloc, no RTOS calls, fixed buffers,
 * MISRA-friendly, provider callbacks for platform glue.
 */
#ifndef LABID_H
#define LABID_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LABID_MAX_FRAME       200u   /* max frame bytes incl. trailing \n */
#define LABID_PREFIX          "LAB"
#define LABID_CRC_CHECK       "123456789"           /* CRC = 0x29B1 */
#define LABID_CRC_CHECK_VAL   0x29B1u

/* --- CRC-16/CCITT-FALSE --- */
uint16_t labid_crc16(const uint8_t *data, size_t len);

/* --- Writer ---
 * Builds a complete LABID frame into buf.
 *   type:   e.g. "ID", "VER", "ANNOUNCE", "ID?", "PONG"
 *   keys/vals: parallel arrays with 'n' entries; values may be NULL to omit.
 * Returns length written (incl. CRC and \n), or <0 on error.
 */
int labid_build_frame(char *buf, size_t buflen,
                      const char *type,
                      const char *const *keys,
                      const char *const *values,
                      size_t n);

/* --- Parser (byte feed -> frame) ---
 * Feed bytes one at a time (e.g. from UART IRQ). Returns:
 *   0  -> still accumulating (or ignored non-frame line)
 *   1  -> a complete valid frame is ready (caller reads via labid_frame_get_*)
 *  -1  -> unrecoverable syntax error (frame dropped, rx_err++)
 * The parser only accepts lines that start with '$'. Lines not starting
 * with '$' are ignored (normal logs).
 */
#define LABID_FEED_IGNORED  0
#define LABID_FEED_FRAME    1
#define LABID_FEED_ERROR   (-1)

/* Parser state (caller-allocated, fixed size). */
struct labid_parser {
    char     buf[LABID_MAX_FRAME];
    size_t   len;          /* current line length (no trailing \n yet) */
    int      started;       /* seen leading '$' */
    int      crc_ok;        /* set when CRC validated */
    uint8_t  crc_hi, crc_lo;/* parsed CRC hex bytes */
};

int labid_feed(struct labid_parser *p, uint8_t ch);
void labid_parser_init(struct labid_parser *p);
/* Internal finalizer — exposed for the Unity test harness. */
int labid_parser_end(struct labid_parser *p);
/* After FRAME: return pointers into parser->buf. */
void labid_frame_type(const struct labid_parser *p, const char **s, int *n);
/* Returns 1 if 'key' present, sets *val / *vlen (value may be empty). */
int labid_frame_get(const struct labid_parser *p, const char *key,
                    const char **val, int *vlen);
/* Returns the parsed CRC validity for the last frame (1 valid, 0 invalid). */
int labid_frame_crc_ok(const struct labid_parser *p);

#ifdef __cplusplus
}
#endif

#endif /* LABID_H */
