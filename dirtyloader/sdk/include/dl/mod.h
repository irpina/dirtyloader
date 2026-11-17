/* SPDX-License-Identifier: GPL-2.0-or-later */
/* dirtyloader loadable mods (.m8x): the contract between a mod built with the SDK and core 0.3's loader.
 *
 * A loadable mod is C compiled for the Cortex-M7 and linked at address 0. Core reads it from the SD card at
 * boot (/dirtyloader/mods/<file>.m8x, listed in /dirtyloader/active.txt), copies it into free ITCM, adds the
 * load address to every word the file lists as a relocation, zeroes its .bss and adds its subscriptions to the
 * hook table. docs/LOADER.md has the file format.
 *
 *     #include "dl/mod.h"
 *     static void on_tick(void) { ... }
 *     DL_MOD("my-mod", "0.1.0", "My mod", DL_ON(EV_TICK, 50, on_tick));
 *
 * Everything a mod links into lives in ITCM, so it is fast and also safe on the audio thread. Firmware
 * addresses come from the device's own header (m8-headless/fw.h); a mod built for one firmware loads only on
 * that firmware (the core checks dl_mod.fw). */
#ifndef DIRTYLOADER_DL_MOD_H
#define DIRTYLOADER_DL_MOD_H

#include <stdint.h>

#define DL_MOD_MAGIC  0x314D4C44u     /* "DLM1" */
#define DL_ABI        1

/* event ids: dirtyloader/core/abi.py */
enum {
    EV_BOOT = 0x0001, EV_CARD_READY = 0x0002, EV_USB = 0x0003, EV_CRASH = 0x0004, EV_TICK = 0x0010, EV_DRAW = 0x0020, EV_RENDER_IN = 0x0030, EV_RENDER_OUT = 0x0031, EV_AUDIO_OUT = 0x0032, EV_TRACK_AUDIO = 0x0033, EV_FX_AUDIO = 0x0034,
    EV_RENDER_PARAMS = 0x0035,
    EV_KEY = 0x0040, EV_VIEW = 0x0041, EV_TOUCH = 0x0042, EV_MIDI = 0x0043, EV_SETTINGS = 0x0044,
    EV_SERIAL = 0x0045, EV_MIDI_OUT = 0x0046, EV_SYSEX = 0x0047,
    EV_NOTE = 0x0050, EV_FX_COMMAND = 0x0051, EV_FX_ROW = 0x0052, EV_MOD_APPLY = 0x0053, EV_NOTE_OFF = 0x0054,
    EV_ROW = 0x0055, EV_LIVE_NOTE = 0x0056, EV_SEQ_TICK = 0x0064, EV_MUTE = 0x0065,
    EV_INST_LOAD = 0x0072, EV_INST_SAVE = 0x0073, EV_INST_CLEAR = 0x0074, EV_PARAM_SET = 0x0080, EV_STEP_EDIT = 0x0081,
    EV_TEMPO = 0x0060, EV_TRANSPORT = 0x0061, EV_PLAY = 0x0062, EV_STOP = 0x0063, EV_SONG_LOAD = 0x0070, EV_SONG_SAVE = 0x0071,
};

struct dl_sub {
    uint16_t event;
    uint16_t order;           /* lower runs first; the stock-flash mods keep their own order */
    void *fn;
};

struct dl_mod {
    uint32_t magic;           /* DL_MOD_MAGIC */
    uint16_t abi;             /* DL_ABI */
    uint16_t nsubs;
    const char *id;           /* unique; a second mod with the same id is refused */
    const char *version;
    const char *title;
    const struct dl_sub *subs;
    uint32_t fw;              /* firmware the mod was built for: DL_FW from the device header, 0 = any */
};

#ifndef DL_FW
#define DL_FW 0
#endif

#define DL_ON(ev, order, fn)  { (ev), (order), (void *)(fn) }

/* One per mod. The linker script puts .dl_head first, so the header sits at the image's offset 0. */
#define DL_MOD(id_, version_, title_, ...)                                                          \
    static const struct dl_sub dl_subs_[] = { __VA_ARGS__ };                                       \
    __attribute__((section(".dl_head"), used)) const struct dl_mod dl_mod_ = {                     \
        DL_MOD_MAGIC, DL_ABI, sizeof(dl_subs_) / sizeof(dl_subs_[0]), (id_), (version_), (title_), \
        dl_subs_, DL_FW }

#endif
