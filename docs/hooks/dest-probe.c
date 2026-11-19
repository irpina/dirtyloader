/* SPDX-License-Identifier: GPL-2.0-or-later */
/* test-only: WAVSYNTH claims 20 destinations (15 stock + X15..X19) straight in its RAM vtable, to see what the
   INST. MODS editor, the draw and the modulators do with indices past 15 */
#include "dl/mod.h"
#include "m8-headless/fw.h"
typedef uint32_t (*count_fn)(void *);
typedef const char *(*name_fn)(void *, uint32_t);
uint32_t count_orig, name_orig, probe_count = 20;   /* 15 for the stock comparison */
uint32_t name_calls, name_last, name_max;
uint32_t apply_n, apply_dest, apply_byte, apply_group_data;
static const char *const extra[] = { "X15", "X16", "X17", "X18", "X19", "X20", "X21", "X22" };
static uint32_t my_count(void *e) { (void)e; return probe_count; }
static const char *my_name(void *e, uint32_t d)
{
    name_calls++; name_last = d; if (d > name_max) name_max = d;
    if (d < 15) return ((name_fn)name_orig)(e, d);
    return d - 15 < 8 ? extra[d - 15] : "X??";
}
static void on_boot(void)
{
    volatile uint32_t *vt = (volatile uint32_t *)0x20001CACu;    /* WAVSYNTH */
    count_orig = vt[FW_VT_DEST_COUNT / 4];
    name_orig = vt[FW_VT_DEST_NAME / 4];
    vt[FW_VT_DEST_COUNT / 4] = (uint32_t)my_count | 1;
    vt[FW_VT_DEST_NAME / 4] = (uint32_t)my_name | 1;
}
static int on_mod_apply(int dest, void *modulator, void *target, int engine)
{
    (void)target;
    if (engine != FW_ENGINE_WAV || dest < 15) return 0;
    uint8_t *m = modulator;
    uint8_t *first = *(uint8_t **)(m + FW_MODULATOR_FIRST);
    apply_n++; apply_dest = (uint32_t)dest; apply_byte = m[0x18];
    apply_group_data = *(uint32_t *)(first + 0x2AC);
    return 1;
}
DL_MOD("dest-probe", "0.0.1", "probe", DL_ON(EV_BOOT, 50, on_boot), DL_ON(EV_MOD_APPLY, 50, on_mod_apply));
