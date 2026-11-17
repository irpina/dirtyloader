/* SPDX-License-Identifier: GPL-2.0-or-later */
/* core-selftest: counts every event core raises, for checking a core build on hardware. The counters are in
 * `selftest_counts` (.bss); read them with python -m dirtyloader.unit and the mod's load address (status.txt),
 * as tools/selftest.py does. It changes nothing: every handler returns 0. */
#include "dl/mod.h"

struct { uint32_t boot, tick, draw, key, view, tempo, render_in, render_out, song_load, song_save, serial,
                  last_key, last_view, note, note_args[4], play, stop; } selftest_counts;

static void on_boot(void) { selftest_counts.boot++; }
static void on_tick(void) { selftest_counts.tick++; }
static void on_draw(void *ui) { selftest_counts.draw++; }
static int on_key(void *ui, int action) { selftest_counts.key++; selftest_counts.last_key = (uint32_t)action; return 0; }
static int on_view(void *ui, int view) { selftest_counts.view++; selftest_counts.last_view = (uint32_t)view; return 0; }
static int on_tempo(float bpm) { selftest_counts.tempo++; return 0; }
static void on_render_in(void) { selftest_counts.render_in++; }
static void on_render_out(void) { selftest_counts.render_out++; }
static void on_song_load(void *songs, const char *path) { selftest_counts.song_load++; }
static void on_song_save(void *songs, const char *path) { selftest_counts.song_save++; }
static int on_serial(void *m8c) { selftest_counts.serial++; return 0; }
static int on_note(void *player, int instrument, int a2, int a3)
{
    selftest_counts.note++;
    selftest_counts.note_args[0] = (uint32_t)player;
    selftest_counts.note_args[1] = (uint32_t)instrument;
    selftest_counts.note_args[2] = (uint32_t)a2;
    selftest_counts.note_args[3] = (uint32_t)a3;
    return 0;
}

static int on_play(void *seq, int mode) { selftest_counts.play++; return 0; }
static int on_stop(void) { selftest_counts.stop++; return 0; }

DL_MOD("core-selftest", "0.1.0", "Core self-test",
       DL_ON(EV_BOOT, 90, on_boot), DL_ON(EV_TICK, 90, on_tick), DL_ON(EV_DRAW, 90, on_draw),
       DL_ON(EV_KEY, 90, on_key), DL_ON(EV_VIEW, 90, on_view), DL_ON(EV_TEMPO, 90, on_tempo),
       DL_ON(EV_RENDER_IN, 90, on_render_in), DL_ON(EV_RENDER_OUT, 90, on_render_out),
       DL_ON(EV_SONG_LOAD, 90, on_song_load), DL_ON(EV_SONG_SAVE, 90, on_song_save),
       DL_ON(EV_SERIAL, 90, on_serial), DL_ON(EV_NOTE, 90, on_note),
       DL_ON(EV_PLAY, 90, on_play), DL_ON(EV_STOP, 90, on_stop));
