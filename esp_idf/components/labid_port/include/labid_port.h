/*
 * labid_port.h — ESP-IDF glue for the LABID serial identity protocol (BL-022).
 * Spec: PLAN §7.3. Talks over the USB-Serial-JTAG console; only apps speak LABID,
 * the bootloader does not (PLAN §7.3.4).
 */
#ifndef LABID_PORT_H
#define LABID_PORT_H

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* App-owned facts LABID reports. The strings must be static (not copied). */
struct labid_port_app {
    const char *variant;            /* "v1" "v2" "no_confirm" "hang" "bad_sig" */
    const char *blink_hz;           /* configured LED rate, e.g. "1" */
    uint32_t  (*toggle_count)(void);/* LED toggle counter */
};

/*
 * Install the USB-Serial-JTAG driver, start the low-priority RX task and send
 * one ANNOUNCE about one second after start (<= 2 s after reset, PLAN §7.3.2).
 * Call once from app_main().
 */
esp_err_t labid_port_start(const struct labid_port_app *app);

#ifdef __cplusplus
}
#endif

#endif /* LABID_PORT_H */
