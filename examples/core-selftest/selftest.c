/* SPDX-License-Identifier: GPL-2.0-or-later */
/* core-selftest: counts every event core raises, for checking a core build on hardware. The counters are in
 * `selftest_counts` (.bss); read them with python -m dirtyloader.unit and the mod's load address (status.txt),
 * as tools/selftest.py does. It changes nothing: every handler returns 0. */
#include "dl/mod.h"

struct { uint32_t boot, tick, draw, key, view, tempo, render_in, render_out, song_load, song_save, serial,
                  last_key, last_view, note, note_args[4], play, stop, midi, last_midi, midi_out, last_midi_out,
                  card_ready, usb, last_usb,
                  seq_tick, note_off, row, fx_row, fx_command, mod_apply, mod_engines, mute, inst_load, inst_save,
                  param_set, step_edit, sysex, audio_out; } selftest_counts;

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
static void on_card_ready(int mounted) { selftest_counts.card_ready++; }
static void on_usb(int configured) { selftest_counts.usb++; selftest_counts.last_usb = (uint32_t)configured; }
static int on_midi(uint32_t packet) { selftest_counts.midi++; selftest_counts.last_midi = packet; return 0; }
static int on_midi_out(uint32_t packet) { selftest_counts.midi_out++; selftest_counts.last_midi_out = packet; return 0; }

static int on_seq_tick(void *engine) { selftest_counts.seq_tick++; return 0; }
static int on_note_off(void *player, int kill) { selftest_counts.note_off++; return 0; }
static void on_row(void *player) { selftest_counts.row++; }
static int on_fx_row(void *player, int column, int cmd, int value) { selftest_counts.fx_row++; return 0; }
static int on_fx_command(void *runner, int column, int cmd, int value) { selftest_counts.fx_command++; return 0; }
static int on_mod_apply(int dest, void *mod, void *target, int engine)
{
    selftest_counts.mod_apply++;
    selftest_counts.mod_engines |= 1u << (engine & 31);
    return 0;
}
static int on_mute(void *mixer, int track) { selftest_counts.mute++; return 0; }
static int on_inst_load(void *songs, const char *path, int slot) { selftest_counts.inst_load++; return 0; }
static int on_inst_save(void *songs, const char *path, int slot) { selftest_counts.inst_save++; return 0; }
static void on_param_set(void *view, int field, int old) { selftest_counts.param_set++; }
static void on_step_edit(void *view, uint8_t *cell, int n, int column) { selftest_counts.step_edit++; }
static int on_sysex(const uint8_t *data, int len, int last) { selftest_counts.sysex++; return 0; }
static int on_audio_out(float *left, float *right, int frames) { selftest_counts.audio_out++; return 0; }

DL_MOD("core-selftest", "0.1.0", "Core self-test",
       DL_ON(EV_BOOT, 90, on_boot), DL_ON(EV_TICK, 90, on_tick), DL_ON(EV_DRAW, 90, on_draw),
       DL_ON(EV_KEY, 90, on_key), DL_ON(EV_VIEW, 90, on_view), DL_ON(EV_TEMPO, 90, on_tempo),
       DL_ON(EV_RENDER_IN, 90, on_render_in), DL_ON(EV_RENDER_OUT, 90, on_render_out),
       DL_ON(EV_SONG_LOAD, 90, on_song_load), DL_ON(EV_SONG_SAVE, 90, on_song_save),
       DL_ON(EV_SERIAL, 90, on_serial), DL_ON(EV_NOTE, 90, on_note),
       DL_ON(EV_PLAY, 90, on_play), DL_ON(EV_STOP, 90, on_stop),
       DL_ON(EV_MIDI, 90, on_midi), DL_ON(EV_MIDI_OUT, 90, on_midi_out),
       DL_ON(EV_CARD_READY, 90, on_card_ready), DL_ON(EV_USB, 90, on_usb),
       DL_ON(EV_SEQ_TICK, 90, on_seq_tick), DL_ON(EV_NOTE_OFF, 90, on_note_off), DL_ON(EV_ROW, 90, on_row),
       DL_ON(EV_FX_ROW, 90, on_fx_row), DL_ON(EV_FX_COMMAND, 90, on_fx_command), DL_ON(EV_MOD_APPLY, 90, on_mod_apply),
       DL_ON(EV_MUTE, 90, on_mute), DL_ON(EV_INST_LOAD, 90, on_inst_load), DL_ON(EV_INST_SAVE, 90, on_inst_save),
       DL_ON(EV_PARAM_SET, 90, on_param_set), DL_ON(EV_STEP_EDIT, 90, on_step_edit), DL_ON(EV_SYSEX, 90, on_sysex),
       DL_ON(EV_AUDIO_OUT, 40, on_audio_out));
