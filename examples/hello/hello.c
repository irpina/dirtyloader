/* SPDX-License-Identifier: GPL-2.0-or-later */
/* hello: the starter mod. Copy this folder, rename the id, and build:
 *
 *     python -m dirtyloader.cc build examples/hello              (every target, into build/mods/<target>/)
 *     python -m dirtyloader.unit add build/mods/m8-headless/hello.m8x
 *     python -m dirtyloader.unit restart
 *
 * What it shows (docs/WRITING-MODS.md walks through it):
 *   - a mod header: id, version, title, and the events it handles (DL_MOD, DL_ON)
 *   - ev_boot: getting core's API once, and adding a page and a setting
 *   - ev_tick: counting, on the UI thread (it runs thousands of times a second: keep it tiny)
 *   - ev_play / ev_stop: the sequencer, without changing what it does (return 0)
 *   - a page of its own: text rows drawn every frame, keys it keeps (return 1) or leaves to core (return 0)
 *   - a setting in the Mod Menu / the MOD LOADER's OPTIONS, kept on the card in /dirtyloader/settings.txt
 * It builds for every target from the same source: "m8-headless/fw.h" is each firmware's own header. */
#include "dl/mod.h"
#include "m8-headless/fw.h"
#include "dl/core.h"

#ifdef M8_MODEL01
static volatile uint32_t ticks;
static void on_tick(void) { ticks++; }

DL_MOD("hello", "0.1.0", "Hello",
       DL_INFO("dirtyloader", "The starter mod in tick-only mode on Model:01."),
       DL_ON(EV_TICK, 50, on_tick));
#else

static const struct dl_core *core;                  /* core's API; 0 under a core without one */
static uint32_t ticks, plays, stops, count;         /* .bss: core zeroes it before ev_boot */

/* a setting: one byte between min and max; names[] are what the Mod Menu shows. Keep it const: core finds which
   mod a setting belongs to by where it lives */
static uint8_t word = 0;
static const char *const words[] = { "HELLO", "HI", "HEY" };
static const struct dl_setting word_setting = { "HELLO WORD", &word, 0, 2, words, 0 };

/* text helpers: the page is the firmware's 40 x 24 character grid; columns 34 and on are the firmware's own */
static char *put(char *o, const char *s) { while (*s) *o++ = *s++; return o; }
static char *num(char *o, uint32_t v)
{
    char t[10];
    int n = 0;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v && n < 10);
    while (n) *o++ = t[--n];
    return o;
}
static void row(int r, const char *label, uint32_t v)
{
    char b[34], *o = put(b, " ");
    o = put(o, label);
    while (o < b + 16) *o++ = ' ';
    o = num(o, v);
    while (o < b + 33) *o++ = ' ';                  /* pad: what was there last frame goes */
    *o = 0;
    fw_text(fw_grid, 0, r, b);
}

static void draw(void)                              /* every frame while the page shows */
{
    char b[34], *o = put(b, " ");
    o = put(put(o, words[word < 3 ? word : 0]), ", M8!");
    while (o < b + 33) *o++ = ' ';
    *o = 0;
    fw_text(fw_grid, 0, 5, b);
    row(7, "SECONDS UP", fw_millis / 1000);
    row(8, "TICKS / 1000", ticks / 1000);
    row(9, "PLAYS", plays);
    row(10, "STOPS", stops);
    row(11, "COUNT", count);
    fw_text(fw_grid, 0, 20, " UP / DOWN  COUNT");
    fw_text(fw_grid, 0, 21, " OPT        BACK");
}

static int key(int action)                          /* FW_KEY_* chords; 1: ours, 0: core's (OPT closes the page) */
{
    if (action == FW_KEY_UP) { count++; return 1; }
    if (action == FW_KEY_DOWN) { if (count) count--; return 1; }
    return 0;
}

static const struct dl_page page = { "hello", "HELLO", 0, draw, key };

static void on_boot(void)
{
    core = dl_core();
    if (!core) return;                              /* an older core: run without the API */
    core->page_add(&page);
    if (core->version >= 0x500) core->setting_add(&word_setting);
}

static void on_tick(void) { ticks++; }
static int on_play(void *seq, int mode) { plays++; return 0; }   /* nonzero would refuse to play */
static int on_stop(void) { stops++; return 0; }

/* id (unique, also the .m8x's file name), version, title, then each event: DL_ON(event, order, handler). Lower
   order runs first; 50 is the usual. */
DL_MOD("hello", "0.1.0", "Hello",
       DL_INFO("dirtyloader", "The starter mod: a page with a counter, a setting, and the boot, tick, play and stop "
                              "events. Copy it to start your own (docs/WRITING-MODS.md)."),
       DL_ON(EV_BOOT, 50, on_boot),
       DL_ON(EV_TICK, 50, on_tick),
       DL_ON(EV_PLAY, 50, on_play),
       DL_ON(EV_STOP, 50, on_stop));

#endif
