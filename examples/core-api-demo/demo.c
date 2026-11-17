/* SPDX-License-Identifier: GPL-2.0-or-later */
/* core-api-demo: the core API (dl/core.h) in one small mod.
 *
 * - a page of its own: SYSTEM SETTINGS > MODS (TELOS), RIGHT on its row
 * - a value kept with each song (song data): UP / DOWN change it, it is saved with the song and comes back on load
 * - MIDI: EDIT sends a note on (C4, the value as velocity) to the host; RIGHT plays one into the M8 itself, which
 *   the mod's own ev_midi handler sees; the page counts both directions
 * - LEFT saves instrument 00 to /Instruments/api.m8i and loads that file into instrument 01 (core 0.5)
 * - a WAVSYNTH modulation destination, DEMO: the page counts the modulator applications that reach it (core 0.5)
 * - OPT closes the page */
#include "dl/mod.h"
#include "m8-headless/fw.h"
#include "dl/core.h"

static struct { uint32_t value; } song_state;          /* what the song keeps */
static uint32_t loaded_n, loads, midi_in, midi_out, last_in, injected, inst_result, demo_dest, demo_applied;
static const struct dl_core *core;

static void hex8(char *o, uint32_t v) { for (int i = 7; i >= 0; i--, v >>= 4) o[i] = "0123456789ABCDEF"[v & 15]; }
static void dec(char *o, uint32_t v, int w) { for (int i = w - 1; i >= 0; i--, v /= 10) o[i] = (char)('0' + v % 10); }

static void line(int r, const char *label, uint32_t v, int hex)
{
    char b[40];
    int i = 0;
    b[i++] = ' ';
    while (*label) b[i++] = *label++;
    while (i < 20) b[i++] = ' ';
    if (hex) { hex8(b + i, v); i += 8; } else { dec(b + i, v, 6); i += 6; }
    while (i < 33) b[i++] = ' ';
    b[i] = 0;
    fw_text(fw_grid, 0, r, b);
}

static void draw(void)
{
    line(5, "SONG VALUE", song_state.value, 0);
    line(6, "SONG LOADS", loads, 0);
    line(7, "BYTES BACK", loaded_n, 0);
    line(9, "MIDI IN", midi_in, 0);
    line(10, "LAST IN", last_in, 1);
    line(11, "MIDI OUT", midi_out, 0);
    line(12, "PLAYED IN", injected, 0);
    line(14, "INST COPY", inst_result, 0);
    line(15, "DEMO DEST", demo_dest, 0);
    line(16, "DEMO APPLIED", demo_applied, 0);
    fw_text(fw_grid, 0, 20, " UP/DOWN VALUE  EDIT SEND");     /* columns 34 on are the firmware's */
    fw_text(fw_grid, 0, 21, " RIGHT PLAY IN  LEFT COPY INST");
    fw_text(fw_grid, 0, 22, " OPT BACK");
}

static int key(int action)
{
    if (action == FW_KEY_UP) { song_state.value++; return 1; }
    if (action == FW_KEY_DOWN) { if (song_state.value) song_state.value--; return 1; }
    if (action == FW_KEY_EDIT) { core->midi_send(DL_MIDI_PACKET(0x90, 60, song_state.value & 0x7F)); return 1; }
    if (action == FW_KEY_RIGHT) { core->midi_receive(DL_MIDI_PACKET(0x90, 0x7E, 1)); injected++; return 1; }
    if (action == FW_KEY_LEFT && core->version >= 0x500) {   /* 1 saved, 2 saved and loaded */
        inst_result = core->inst_save("/Instruments/api.m8i", 0) ? 1 : 0;
        if (inst_result) inst_result += core->inst_load("/Instruments/api.m8i", 1) ? 1 : 0;
        return 1;
    }
    return 0;
}

static const struct dl_page page = { "core-api-demo", "CORE API DEMO", 0, draw, key };

static void loaded(uint32_t n)
{
    loads++;
    loaded_n = n;
    if (!n) song_state.value = 0;                       /* a song without our data: defaults */
}
static const struct dl_song_data data = { "core-api-demo", &song_state, sizeof song_state, loaded };

static void on_boot(void)
{
    core = dl_core();
    if (!core) return;
    core->page_add(&page);
    core->song_data(&data);
    if (core->version >= 0x500) demo_dest = (uint32_t)core->mod_dest_add(FW_ENGINE_WAV, "DEMO");
}

/* audio thread: a WAVSYNTH modulator pointed at DEMO. The stock does nothing with this destination; a real
   mod would apply the modulator's output (s16/s17 at the site, or the modulator object) to its own target. */
static int on_mod_apply(int dest, void *modulator, void *target, int engine)
{
    if (engine == FW_ENGINE_WAV && demo_dest && (uint32_t)dest == demo_dest) demo_applied++;
    return 0;
}

static int on_midi(uint32_t packet) { midi_in++; last_in = packet; return 0; }
static int on_midi_out(uint32_t packet) { midi_out++; return 0; }

DL_MOD("core-api-demo", "0.1.0", "Core API demo",
       DL_ON(EV_BOOT, 50, on_boot), DL_ON(EV_MIDI, 50, on_midi), DL_ON(EV_MIDI_OUT, 50, on_midi_out),
       DL_ON(EV_MOD_APPLY, 50, on_mod_apply));
