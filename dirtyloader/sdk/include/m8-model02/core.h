/* SPDX-License-Identifier: GPL-2.0-or-later */
/* The M8 Model:02 core's hook bus in C: event handler prototypes and the firmware locations core exports
 * (docs/CORE-EVENTS.md). Modelled on Elekloader's digitakt-mk1/core3.h.
 *
 *     #include "m8-model02/core.h"
 *
 * Firmware 6.6.2A. The locations are plain addresses today; once the SDK links C mods they become symbols the
 * linker resolves against the core, so a mod naming only these rebuilds for another firmware unchanged.
 * Calling convention: AAPCS with hard float (ints r0-r3, floats s0-s3, result r0 / s0). Audio-thread
 * handlers go in the .itcm section; nothing here has run on hardware yet. */
#ifndef DIRTYLOADER_M8_MODEL02_CORE_H
#define DIRTYLOADER_M8_MODEL02_CORE_H

#include <stdint.h>

#define ITCM __attribute__((section(".itcm"), noinline))   /* code for audio-thread events */

/* ---- events: subscribe in mod.json ("event": "ev_tick", "order": 50) ------------------------------- */
/* UI thread (loop()) */
typedef void (*ev_boot_fn)(void);                                   /* once, after setup()            */
typedef void (*ev_tick_fn)(void);                                   /* every loop(): keep it tiny     */
typedef void (*ev_draw_fn)(void *ui);                               /* each frame, before the push    */
typedef int  (*ev_key_fn)(void *ui, int action);                    /* nonzero: take the action       */
typedef int  (*ev_view_fn)(void *ui, int view);                     /* nonzero: stay on this screen   */
struct m8_touch;
typedef int  (*ev_touch_fn)(struct m8_touch *t);                    /* nonzero: take the touch frame  */
typedef int  (*ev_tempo_fn)(float bpm);                             /* nonzero: refuse                */
typedef int  (*ev_transport_fn)(int state);                         /* 1 play, 0 pause, -1 stop       */
typedef int  (*ev_midi_fn)(const unsigned char *msg, int port);     /* site pending                   */
/* audio thread (IRQ 70, once per audio block): ITCM code, short, no UI calls */
typedef void (*ev_render_fn)(void);                                 /* ev_render_in / ev_render_out   */
typedef int  (*ev_note_fn)(int track, const unsigned char *step);   /* nonzero: skip the row          */
typedef int  (*ev_fx_command_fn)(int track, int cmd, int value);    /* nonzero: take the command      */
typedef int  (*ev_fx_row_fn)(int track, int column, int cmd, int value);
typedef void (*ev_mod_apply_fn)(int engine, void *voice, void *mod, int dest);

/* ---- the song (OCRAM): RAM offset = .m8s file offset - 0x82 ------------------------------------------ */
#define fw_song                 ((uint8_t *)0x2025A570u)
#define FW_GROOVE(g)            (fw_song + 0x006C + 16 * (g))
#define FW_SONG_ROW(r)          (fw_song + 0x026C + 8 * (r))            /* 8 tracks: chain numbers      */
#define FW_PHRASE(p, s)         (fw_song + 0x0A6C + 0x90 * (p) + 9 * (s)) /* note, vel, instr, 3x(cmd,val) */
#define FW_CHAIN(c, s)          (fw_song + 0x99DC + 32 * (c) + 2 * (s))   /* phrase, transpose            */
#define FW_TABLE(t, s)          (fw_song + 0xB9BC + 128 * (t) + 8 * (s))
#define FW_INSTRUMENT(i)        (fw_song + 0x139BC + 0xD7 * (i))           /* 215 bytes                    */
#define FW_INSTR_MOD(i, m)      (FW_INSTRUMENT(i) + 0x30 + 6 * (m))        /* 4 modulator slots            */
#define FW_EQ(n)                (fw_song + 0x1ACDC + 18 * (n))             /* 3 bands x 6 bytes            */

/* ---- sequencer and transport ---------------------------------------------------------------------- */
#define fw_clock                ((uint8_t *)0x2000D218u)  /* +0x28 running, +0x29 paused, +0x2C ticks (u32), +0x30 bpm (float) */
#define fw_track_players        ((uint8_t *)0x2000D270u)  /* 8 x 0x2B0 */
#define FW_TRACK_PLAYER(t)      (fw_track_players + 0x2B0 * (t))
#define FW_TICKS_PER_BEAT       192                        /* clock sub-ticks at 44.1 kHz */
typedef void (*fw_set_tempo_fn)(float bpm);
typedef void (*fw_set_playing_fn)(void *self, int playing);
#define fw_set_tempo            ((fw_set_tempo_fn)0x6009A6C1u)
#define fw_set_playing          ((fw_set_playing_fn)0x6009A529u)
#define fw_stop                 ((void (*)(void))0x6009A55Du)

/* ---- UI ------------------------------------------------------------------------------------------- */
#define fw_ui                   ((uint8_t *)0x20015458u)   /* +0x04 view object, +0x15 view id, +0x17 previous */
#define FW_UI_VIEW(ui)          (*(volatile uint8_t *)((uint8_t *)(ui) + 0x15))
#define fw_set_view             ((void (*)(void *ui, int view))0x6004C13Du)
#define fw_text                 ((void *)0x60030ECDu)     /* draw a string: arguments not confirmed yet */
enum { M8_SONG = 0x00, M8_GROOVE, M8_CHAIN, M8_PHRASE, M8_TABLE, M8_INSTRUMENT, M8_PROJECT,
       M8_KEYBOARD = 0x08, M8_FX_HELP = 0x09, M8_FILES = 0x0A, M8_EFFECTS = 0x0B, M8_CONFIRM = 0x0C,
       M8_MIXER = 0x0D, M8_MIDI_SETTINGS = 0x0E, M8_MIDI_MAPPING = 0x0F, M8_THEME = 0x10, M8_RENDER = 0x11,
       M8_SAMPLE_REC = 0x12, M8_SCALE = 0x13, M8_HW_SETTINGS = 0x14, M8_MKDIR = 0x15, M8_INST_MODS = 0x16,
       M8_TIME_STATS = 0x17, M8_INST_POOL = 0x18, M8_EQ = 0x19, M8_LIMITER = 0x1A, M8_GRID_PICK = 0x1B,
       M8_SETTINGS = 0x1C, M8_USB_DISK = 0x1D, M8_FIRST_MOD_VIEW = 0x1E };

/* ---- mixer and effects settings (song blocks) -------------------------------------------------------- */
#define FW_MIXER(n)             (fw_song + 0x004C + (n))
#define FW_EFFECTS(n)           (fw_song + 0x1A53C + (n))
enum { FX_MODFX_DEPTH = 0x03, FX_MODFX_FREQ, FX_MODFX_WIDTH, FX_MODFX_REVERB_SEND,
       FX_DELAY_TIME_L = 0x0C, FX_DELAY_TIME_R, FX_DELAY_FEEDBACK, FX_DELAY_WIDTH, FX_DELAY_REVERB_SEND,
       FX_REVERB_SIZE = 0x14, FX_REVERB_DECAY, FX_REVERB_MOD_DEPTH, FX_REVERB_MOD_FREQ, FX_REVERB_WIDTH,
       FX_REVERB_SHIMMER, FX_MODFX_TYPE = 0x1C };

struct m8_touch {                    /* at fw_touch */
    uint8_t _0[0x30];
    float dx, dy;                    /* +0x30 */
    uint8_t _1[0x08];
    float x, y;                      /* +0x40 */
};
#define fw_touch                ((struct m8_touch *)0x200177D4u)

/* ---- audio ------------------------------------------------------------------------------------------ */
#define FW_SEND_MIXER(t, bus)   ((void *)(0x20010F50u + 0x38u * (4u * (t) + (bus))))  /* bus 0 dry .. 3 reverb */
#define fw_audio_lock()         (*(volatile uint32_t *)0xE000E188u = 0x40u)   /* AudioNoInterrupts() */
#define fw_audio_unlock()       (*(volatile uint32_t *)0xE000E108u = 0x40u)   /* AudioInterrupts()   */

/* ---- instruments: one singleton per engine ---------------------------------------------------------- */
enum { M8_ENG_WAVSYNTH, M8_ENG_MACROSYNTH, M8_ENG_SAMPLER, M8_ENG_FMSYNTH, M8_ENG_HYPERSYNTH,
       M8_ENG_EXTERNAL, M8_ENG_MIDIOUT, M8_ENG_NONE };
#define FW_INSTRUMENT_OBJ_SAMPLER     ((void *)0x2000EAA0u)
#define FW_INSTRUMENT_OBJ_WAVSYNTH    ((void *)0x20037DB8u)
#define FW_INSTRUMENT_OBJ_MACROSYNTH  ((void *)0x20038DE4u)
#define FW_INSTRUMENT_OBJ_MIDIOUT     ((void *)0x2003AA94u)
#define FW_INSTRUMENT_OBJ_FMSYNTH     ((void *)0x2003B97Cu)
#define FW_INSTRUMENT_OBJ_HYPERSYNTH  ((void *)0x2003DAACu)
#define FW_INSTRUMENT_OBJ_EXTERNAL    ((void *)0x2003EC88u)

/* ---- core's tables (core 0.2) ----------------------------------------------------------------------- */
struct core_view {          /* core_views: a mod's screen, id >= M8_FIRST_MOD_VIEW; claim view:<name> */
    int32_t id;
    void *view;             /* an object whose first word is an 8-slot View vtable */
    const char *name;
};
struct core_mod_dest {      /* core_mod_dests: an extra LFO destination; claim moddest:<name> */
    uint8_t engines;        /* bit per M8_ENG_* */
    uint8_t _pad[3];
    const char *name;       /* as the DEST field shows it */
};

#endif
