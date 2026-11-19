/* SPDX-License-Identifier: GPL-2.0-or-later */
/* flash-probe: a mod too big for ITCM, to prove core 0.7's flash placement. Its 24 KB table can only go to flash
 * (FW_MOD_FLASH); its .data and .bss go to ITCM. It exercises each kind of relocation the split has to get right:
 *   - code in flash calling code in flash, and a table of function pointers (flash -> flash)
 *   - code in flash reading and writing .data / .bss (flash -> RAM)
 *   - an initialised variable holding a pointer into the table (RAM -> flash)
 * Results are in `probe` for a PEEK: magic, the table's sum (worked out at ev_boot), what each function pointer
 * returned, ticks counted, and the pointer's target as read through it. */
#include "dl/mod.h"
#include "m8-headless/fw.h"

#define N 6144                                      /* 24 KB of words */
static const uint32_t table[N] = {
#define R4(i) (i) * 2654435761u, (i + 1) * 2654435761u, (i + 2) * 2654435761u, (i + 3) * 2654435761u
#define R16(i) R4(i), R4(i + 4), R4(i + 8), R4(i + 12)
#define R64(i) R16(i), R16(i + 16), R16(i + 32), R16(i + 48)
#define R256(i) R64(i), R64(i + 64), R64(i + 128), R64(i + 192)
#define R1K(i) R256(i), R256(i + 256), R256(i + 512), R256(i + 768)
    R1K(0), R1K(1024), R1K(2048), R1K(3072), R1K(4096), R1K(5120)
};
static uint32_t one(void) { return 1; }
static uint32_t two(void) { return 2; }
static uint32_t (*const volatile fns[2])(void) = { one, two };   /* flash pointing at flash */
static const uint32_t *volatile where = &table[N - 1];      /* .data pointing at flash */

static volatile struct {
    uint32_t magic, sum, fn_sum, ticks, last, data_flag;
} probe __attribute__((used)) = { 0x50524F42u, 0, 0, 0, 0, 0 };   /* "PROB", in .data */
static volatile uint32_t bss_counter;                       /* .bss */

static void on_boot(void)
{
    uint32_t s = 0;
    const volatile uint32_t *t = table;                     /* read it from flash, not folded */
    for (uint32_t i = 0; i < N; i++) s += t[i];
    probe.sum = s;
    probe.fn_sum = fns[0]() + fns[1]() * 10;                /* 21 */
    probe.last = *where;
    probe.data_flag = 1;
}
static void on_tick(void) { bss_counter++; if (!(bss_counter & 0xFFF)) probe.ticks = bss_counter; }

DL_MOD("flash-probe", "0.1.0", "flash-probe: a mod that only fits in flash",
       DL_ON(EV_BOOT, 50, on_boot), DL_ON(EV_TICK, 50, on_tick));
