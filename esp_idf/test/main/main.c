/* main.c — host (linux target) smoke test for the LABID IDF component.
 * Builds and runs on the RPi4. Prints the CRC check vector and a built
 * frame to prove the linked component behaves as specified. */
#include "labid.h"
#include <stdio.h>

int main(void)
{
    const char *keys[] = {"bl", "app", "slot"};
    const char *vals[] = {"1.0.0", "2.0.0", "0"};
    char buf[LABID_MAX_FRAME];
    int n = labid_build_frame(buf, sizeof(buf), "VER", keys, vals, 3);
    printf("n=%d\n", n);
    if (n <= 0)
        return 1;
    fputs(buf, stdout);
    printf("\n");
    /* CRC check vector from PLAN §7.3.1 */
    uint16_t crc = labid_crc16((const uint8_t *)"123456789", 9);
    printf("crc=0x%04X\n", crc);
    return (crc == 0x29B1u) ? 0 : 2;
}
