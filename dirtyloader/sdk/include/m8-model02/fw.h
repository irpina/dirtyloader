/* SPDX-License-Identifier: GPL-2.0-or-later */
/* M8 Model:02 6.6.2A: the firmware locations core 0.5 and loadable mods use: the same names as m8-headless/fw.h.
 * Each address was found again from the headless one (code matched by instruction runs, data by the literals
 * the matched code loads); dirtyloader/core/bindings/m8_6.6.2A_model02.json records them. Built, not yet run
 * on a Model:02 unit. */
#ifndef DIRTYLOADER_M8_MODEL02_FW_H
#define DIRTYLOADER_M8_MODEL02_FW_H

#include <stdint.h>

#undef DL_FW                                    /* dl/mod.h's default is 0, "any firmware" */
#define DL_FW 0x02060602u                       /* 6.6.2A Model:02 (0x02: the model) */

#define fw_millis   (*(volatile uint32_t *)0x20040358u)
/* Teensyduino's _VectorsRam: the startup stores it in VTOR at 0x600014C4 (from the literal at 0x60001600). On a
 * unit, entry 86 (IRQ 70, the audio update) is 0x2929D. Not headless's 0x2000B800: core 0.5-0.6 used that here and
 * overwrote 5 words of the firmware's data at 0x2000B80C..18 and 0x2000BA58 (fixed 2026-11-17). */
#define FW_VECTORS  ((volatile uint32_t *)0x2000C000u)
/* Flash for mods (core 0.7), as headless: 1 MB, erased on a stock unit (read back on one); the chip is 16 MB, the
 * EEPROM emulation at 0x60FC0000. Teensyduino's routines are the headless ones, 0x1D64 further into ITCM. */
#define FW_MOD_FLASH        0x60600000u
#define FW_MOD_FLASH_END    0x60700000u
typedef void (*fw_flash_write_fn)(void *addr, const void *data, uint32_t len);
typedef void (*fw_flash_erase_fn)(void *addr);
#define fw_flash_write          ((fw_flash_write_fn)0x00029D35u)
#define fw_flash_erase_sector   ((fw_flash_erase_fn)0x00029E21u)

/* ---- SdFat 2.x as linked into this build -------------------------------------------------------------------
 * FsBaseFile is 0x40 bytes: 0x38 bytes of storage for the open FatFile (0x24) or ExFatFile (0x38), then
 * pointers to whichever is open. fw_sd is the SdFs volume setup() mounts. */
struct fw_file {
    uint8_t mem[0x38];
    void *fat;                                  /* FatFile *, or 0 */
    void *exfat;                                /* ExFatFile *, or 0 */
};
#define fw_sd               ((void *)0x200372F4u)
/* The firmware's storage object: +4 is nonzero while a card is mounted. Check FW_SD_MOUNTED() before any
 * file call, as the firmware checks before its own. fw_sd_ready() returns the flag after trying to mount a
 * card inserted since boot; it masks the audio interrupt while it tries, so core uses only the flag. */
typedef int (*fw_sd_ready_fn)(void *storage);
#define fw_storage          ((void *)0x20015BB0u)
#define fw_sd_ready         ((fw_sd_ready_fn)0x6007CDF9u)
#define FW_SD_MOUNTED()     (((volatile uint8_t *)fw_storage)[4])
#define FW_O_READ           0x000
#define FW_O_RDWR           0x002
#define FW_O_CREAT          0x200
#define FW_O_TRUNC          0x400
#define FW_ATTR_DIR         0x70                /* FatFile / ExFatFile attribute bits that mean a directory */

typedef int  (*fw_open_fn)(struct fw_file *f, void *vol, const char *path, int oflag);   /* FsBaseFile::open */
typedef int  (*fw_open_next_fn)(struct fw_file *f, struct fw_file *dir, int oflag);      /* ::openNext */
typedef int  (*fw_close_fn)(struct fw_file *f);                                          /* ::close */
typedef int  (*fw_io_fn)(void *file, void *buf, uint32_t n);
typedef int  (*fw_fat_seek_fn)(void *fat, uint32_t pos);
typedef int  (*fw_exfat_seek_fn)(void *exfat, uint32_t _r1, uint64_t pos);
typedef int  (*fw_name_fn)(void *file, char *buf, uint32_t size);

#define fw_file_open        ((fw_open_fn)0x600ABFFDu)
#define fw_file_open_next   ((fw_open_next_fn)0x600AC135u)
#define fw_file_close       ((fw_close_fn)0x600ABFD5u)
#define fw_fat_read         ((fw_io_fn)0x600AA765u)
#define fw_exfat_read       ((fw_io_fn)0x600A8D69u)
#define fw_fat_write        ((fw_io_fn)0x600AAD99u)
#define fw_exfat_write      ((fw_io_fn)0x600A983Du)
#define fw_fat_seek         ((fw_fat_seek_fn)0x600AAA09u)
#define fw_exfat_seek       ((fw_exfat_seek_fn)0x600A8F35u)
#define fw_fat_name         ((fw_name_fn)0x600AB995u)
#define fw_exfat_name       ((fw_name_fn)0x600A9B09u)

/* SdFat directories: FatFile::mkdir(this, parent, path, pFlag) / ExFatFile::mkdir; the volume's working
 * directory (the parent the firmware passes) is +0x448 of the FatVolume / ExFatVolume at fw_sd +0x480 / +0x484.
 * `this` is a zeroed FatFile (0x24 B) or ExFatFile (0x38 B), left open on success: close it. */
typedef int (*fw_mkdir_fn)(void *file, void *parent, const char *path, int pflag);
typedef int (*fw_fclose_fn)(void *file);
#define fw_fat_vol          (*(void *volatile *)((uint8_t *)fw_sd + 0x480))
#define fw_exfat_vol        (*(void *volatile *)((uint8_t *)fw_sd + 0x484))
#define FW_VOL_CWD          0x448
#define fw_fat_mkdir        ((fw_mkdir_fn)0x600AA481u)
#define fw_exfat_mkdir      ((fw_mkdir_fn)0x600A9681u)
#define fw_fat_fclose       ((fw_fclose_fn)0x600AA271u)
#define fw_exfat_fclose     ((fw_fclose_fn)0x600A8C15u)
/* FatFile::remove(this) / ExFatFile::remove(this): delete an open file (opened FW_O_RDWR); it is closed after */
typedef int (*fw_remove_fn)(void *file);
#define fw_fat_remove       ((fw_remove_fn)0x600AB6B5u)
#define fw_exfat_remove     ((fw_remove_fn)0x600A9245u)

/* ---- USB MIDI (Teensyduino usb_midi.c) -------------------------------------------------------------------------
 * A USB MIDI packet is a word: byte 0 cable << 4 | code index (CIN), bytes 1-3 the MIDI bytes (status first).
 * usb_midi_read (0x600AF468, what usbMIDI.read() runs) takes one packet from usb_midi_read_message and calls
 * the handlers the firmware set; usb_midi_write_packed queues one packet for the host. Core's ev_midi sees each
 * packet usb_midi_read takes, ev_midi_out each packet written. */
typedef uint32_t (*fw_midi_read_fn)(void);
typedef void (*fw_midi_write_fn)(uint32_t packet);
#define fw_usb_midi_read_message ((fw_midi_read_fn)0x600AF3C1u)
#define fw_usb_midi_write_packed ((fw_midi_write_fn)0x600AEF3Du)
#define FW_MIDI_READ_CALL   0x600AF46Eu
/* usbMIDI's partial-SysEx handler (data, len, last): the firmware sets it to 0x600A65B5 in setup(); core 0.5 chains it */
#define fw_sysex_handler    (*(volatile uint32_t *)0x20040748u)
#define fw_usb_configuration (*(volatile uint8_t *)0x200416C6u)   /* nonzero once the host configured USB */     /* usb_midi_read's bl usb_midi_read_message: core's ev_midi site */

/* ---- the song, the mixer, the sequencer (Ghidra, core 0.5's sites) ---------------------------------------------
 * The song in RAM; the firmware's accessors return pointers into it: a phrase step is 9 bytes (note, velocity,
 * instrument, 3 x (command, value)), an instrument 0xD7 bytes. */
#define fw_song             ((uint8_t *)0x2025A570u)
#define FW_PHRASE_STEP(p, s) (fw_song + 0xA6C + (p) * 0x90 + (s) * 9)
#define FW_INSTRUMENT(i)    (fw_song + 0x139BC + (i) * 0xD7)
#define fw_mixer            ((uint8_t *)0x20010858u)
#define fw_songs            ((void *)0x20015BB0u)                 /* the song loader/writer's object */
typedef int (*fw_inst_load_fn)(void *songs, const char *path, int slot, int flag);
typedef int (*fw_inst_save_fn)(void *songs, const char *path, int slot);
#define fw_inst_load        ((fw_inst_load_fn)0x6007E78Du)       /* ev_inst_load's routine (flag 0) */
#define fw_inst_save        ((fw_inst_save_fn)0x6007EE39u)       /* ev_inst_save's routine */
/* The audio graph (a float Teensy Audio graph: 32-frame blocks of float, 44.1 kHz): Model:02 keeps its objects as
 * globals, not in one engine object. Each has a vtable in RAM whose first slot is update(). The master chain is
 * OTT 0x2000C780 -> DJ filter 0x2001D9B8 -> limiter 0x2001D6DC -> soft clip 0x2001DA34, which sends the same blocks
 * two ways: to 0x2001D854 -> USB (0x20010620, 24 inputs: main, then the send effects' pairs), and to 0x2001DA7C ->
 * 0x20037A90 -> 0x2001BE9C -> I2S out 0x2001D2CC (speaker, headphones, line out). core's ev_audio_out wraps the soft
 * clip's update() and changes its input before the split, so both hear it (wrapping 0x2001D854 reached USB only).
 * Walked on a unit through each node's destination list (+0x1C). audio_block_t: +0 ref count (u8),
 * +4 float data[32]. */
#define FW_AUDIO_TAP_OBJ    ((uint8_t *)0x2001DA34u)                 /* the soft clip: the only one of its class */
#define FW_AUDIO_USB_OBJ    ((uint8_t *)0x2001D854u)                 /* the USB branch's first node */
#define FW_CLOCK_OBJ        ((uint8_t *)0x2000D218u)                 /* the sequencer clock: +0x28 playing */
#define fw_bpm              (*(volatile float *)(FW_CLOCK_OBJ + 0x30u))   /* the tempo (set_tempo 0x6009A6C0 stores it) */
/* Spare DTCM for mods' buffers (core's ram_claim): .bss ends at 0x20041700 (the reset handler's clear), the stack
 * grows down from 0x20050000. The same range as headless, where the stack was measured; not measured here. */
#define FW_SPARE_RAM        0x20041800u
#define FW_SPARE_RAM_END    0x2004B800u
/* The touch screen (ev_touch's argument): the touch engine 0x600A5E60 polls the controller (0x6007B6B4) into this
 * object. x and y are calibrated to 0..1: x from the left, y from the BOTTOM (on a unit: a marker drawn at y from
 * the top showed mirrored); +0x58 is the touch's start time while a finger is down
 * (0 once it lifts, with x and y); +0x30 / +0x34 the movement since it came down; +0x52 "a gesture happened". */
#define fw_touch            ((uint8_t *)0x200177D4u)
#define FW_TOUCH_X          0x40u
#define FW_TOUCH_Y          0x44u
#define FW_TOUCH_DOWN       0x58u
/* More of the graph (classes are unique; each vtable's update slot is in RAM):
 * - the 8 track voices (0x2001606C + 0x2E4 x track): class slot 0x200024A0; +0x3D the track; +0x38 the
 *   instrument; each transmits its block pair to its strip (an array, FW_TRACK_STRIP) and its sends
 * - send effects: MFX 0x2001DD14 (slot 0x20002CDC, stereo in), delay 0x20021D4C (slot 0x20002ED4, mono in), reverb
 *   0x20021F18 (slot 0x2000297C, stereo in); they run after the tracks
 * - the sequencer clock 0x2000D218 (slot 0x20001FE0): first in each block, before the tracks */
#define FW_SLOT_TRACK       0x200024A0u
#define FW_SLOT_MFX         0x20002CDCu
#define FW_SLOT_DELAY       0x20002ED4u
#define FW_SLOT_REVERB      0x2000297Cu
#define FW_SLOT_CLOCK       0x20001FE0u
#define FW_TRACK_STRIP(voice) ((uint8_t *)0x20011650u + 0x6C * ((uint8_t *)(voice))[0x3D])   /* strips are an array */
/* The phrase view (object 0x20014084, phrase number at +4): its vtable is in RAM. +0x34 redraws after a bulk edit
 * (cut / clear, paste, interpolate, rotate, the FILL generators, transposing a selection), +0x38 after a cell. */
#define fw_phrase_view      ((uint8_t *)0x20014084u)
#define FW_SLOT_PHRASE_BULK 0x20001888u
#define FW_SLOT_PHRASE_CELL 0x2000188Cu
enum { FW_FX_MFX, FW_FX_DELAY, FW_FX_REVERB };
typedef void (*fw_audio_transmit_fn)(void *obj, void *block, int port);
typedef void (*fw_audio_release_fn)(void *block);
#define fw_audio_transmit   ((fw_audio_transmit_fn)0x0001BDBDu)  /* AudioStream::transmit (ITCM) */
#define fw_audio_release    ((fw_audio_release_fn)0x0001BD51u)   /* AudioStream::release (ITCM) */
#define FW_AUDIO_FRAMES     32                          /* Model:02: 32-frame blocks */
#define FW_AUDIO_RATE       44100
typedef void *(*fw_audio_alloc_fn)(void);
#define fw_audio_alloc      ((fw_audio_alloc_fn)0x0001BB51u)        /* AudioStream::allocate (ITCM): ref count 1 */
#define fw_mute_mask        (*(volatile uint8_t *)0x20010A08u)  /* a bit per track */
#define fw_solo_mask        (*(volatile uint8_t *)0x20010A0Cu)
#define fw_seq_engine       ((uint8_t *)0x200140D0u)              /* ev_seq_tick's argument */
#define fw_sequencer        ((uint8_t *)0x2000D218u)              /* +FW_SEQ_PLAYING: playing */
#define FW_SEQ_PLAYING      0x28u
#define FW_PLAYER(t)        ((uint8_t *)0x200140E4u + 0x240 * (t))   /* a track's player: +0xC track, +0x4C the row */
#define FW_PLAYER_INST      0x170u          /* the player's instrument: its FW_INSTRUMENT() data (headless +0x178) */
/* Track voices and their four strips (walked on a unit through the voices' destination lists): each voice sends
 * its block pair to four gain nodes, each 0x6C long like headless's: DRY 0x20011650, REV 0x200119B0, DEL
 * 0x20011D10, MFX 0x20012070, each + 0x6C x track (REV reaches the reverb, DEL the delay, MFX the MFX). Fields
 * (the strip's update, ITCM 0x203B8): +0x38 target, +0x3C current, +0x55 ramping, +0x56 ramp on change; while
 * ramping each sample's gain is +0x58 start + +0x5C step x table[phase], phase (+0x60) going up 1/256 a sample, and
 * only when it reaches 1 does +0x3C take the target. +0x54 is not a word selector here (it flips by itself).
 * fw_gain_set is for a caller that sets a gain every block (lfo-sends): a ramp restarted every 32-frame block
 * would never finish, so it sets the gain at once. Blocks are 0.73 ms apart. */
#define FW_TRACK_VOICE(t)   ((uint8_t *)0x2001606Cu + 0x2E4u * (t))
#define FW_VOICE_TRACK      0x3Du
enum { FW_GAIN_DRY, FW_GAIN_MFX, FW_GAIN_DELAY, FW_GAIN_REVERB };
static inline uint8_t *fw_track_gain(int t, int which)
{
    static const uint32_t base[4] = { 0x20011650u, 0x20012070u, 0x20011D10u, 0x200119B0u };
    return (unsigned)t < 8 && FW_TRACK_VOICE(t)[FW_VOICE_TRACK] == (uint8_t)t ? (uint8_t *)base[which & 3] + 0x6C * t : 0;
}
static inline void fw_gain_set(uint8_t *node, float g)
{
    node[0x55] = 0;
    *(volatile float *)(node + 0x38) = g;
    *(volatile float *)(node + 0x3C) = g;
    *(float *)(node + 0x60) = 1.0f;
}
/* Modulators: as headless, 4 a track 0xA8 apart, in groups 0x2B0 apart: 9 groups at 0x2000D270 (the 8 tracks, then
 * one more), found on a unit by their +0xA0 (each points at its group's first). Same vtable layout (class vtable
 * 0x20002994, slot for slot the headless one). Unlike headless, 6.6.2A's group setup (0x6009D430) keeps no pointer
 * to the instrument it came from: FW_MODULATOR_INST_MODS takes the group's track's player's instrument instead. */
#define fw_modulators       ((uint8_t *)0x2000D270u)
#define FW_MODULATOR_SIZE   0xA8u
#define FW_MODULATOR_TRACK  0x2B0u
#define FW_MODULATOR_FIRST  0xA0u
typedef float (*fw_mod_float_fn)(void *mod);
#define FW_MOD_OUTPUT(m)    ((*(fw_mod_float_fn const *const *)(m))[1](m))
#define FW_MOD_AMOUNT(m)    ((*(fw_mod_float_fn const *const *)(m))[2](m))
enum { FW_INST_WAV, FW_INST_MACRO, FW_INST_SAMPLER, FW_INST_MIDI_OUT, FW_INST_FM, FW_INST_HYPER, FW_INST_EXTERNAL };
#define FW_INST_MODS        0x3Fu
#define FW_INST_SIZE        0xD7u
static inline const uint8_t *fw_modulator_inst_mods(const uint8_t *first)
{
    uint32_t t = (uint32_t)(first - fw_modulators) / FW_MODULATOR_TRACK;
    if (first < fw_modulators || t >= 8) return 0;
    const uint8_t *inst = *(const uint8_t *const *)(FW_PLAYER(t) + FW_PLAYER_INST);
    return inst ? inst + FW_INST_MODS : 0;
}
#define FW_MODULATOR_INST_MODS(first) fw_modulator_inst_mods((const uint8_t *)(first))
enum { FW_ENGINE_FM, FW_ENGINE_HYPER, FW_ENGINE_MACRO, FW_ENGINE_SAMPLER, FW_ENGINE_WAV, FW_ENGINE_EXTERNAL,
       FW_ENGINE_MIDI_OUT, FW_ENGINES };
/* Each engine's class vtable is in RAM (DTCM .data): +0xF8 name(eng, dest) and +0x104 count(eng) list its
 * modulation destinations (0 = OFF). A modulator keeps dest in the low nibble of its first byte (instrument +0x3F
 * + 6 x mod), so an engine has at most 16. Stock counts: 15, SAMPLER and EXTERNAL 14. Order: FW_ENGINE_*. */
#define FW_ENGINE_VTABLES   { 0x2000195Cu, 0x20002038u, 0x20002200u, 0x200027CCu, 0x20001DF8u, 0x200029F4u, 0x20001B9Cu }
#define FW_VT_DEST_NAME     0xF8u
#define FW_VT_DEST_COUNT    0x104u
#define FW_MOD_DESTS_MAX    16

/* core 0.4's API for mods (dl/core.h): a pointer to it sits after core's hook table (bindings: loader.ram +
 * 0x208). dl_core() checks it. */
#define DL_CORE_PTR         0x0002BAD8u

/* ---- USB serial (Teensyduino usb_serial.c): what m8c talks to ------------------------------------------------
 * The m8c command parser (fw_m8c_parse, 0x60079A7C) drains every waiting byte; core's ev_serial handler runs at
 * its entry and peeks the receive queue first. Received data waits in RX_NUM (8) 512-byte buffers queued in
 * rx_list (a ring of 9, head and tail are bytes); rx_index is how far each buffer has been read. Mask the USB
 * interrupt (IRQ 113) while looking, as usb_serial_read does. */
#define fw_rx_available     (*(volatile uint32_t *)0x2003341Cu)
#define fw_rx_head          (*(volatile uint8_t *)0x200416B4u)
#define fw_rx_tail          (*(volatile uint8_t *)0x200416B7u)
#define fw_rx_list          ((volatile uint8_t *)0x20033470u)
#define fw_rx_index         ((volatile uint16_t *)0x20033448u)
#define fw_rx_buffer        ((volatile uint8_t *)0x20279760u)
#define FW_RX_RING          9
#define FW_RX_BUF           512
#define FW_USB_IRQ_BIT      (1u << (113 - 96))
#define FW_NVIC_ISER3       (*(volatile uint32_t *)0xE000E10Cu)
#define FW_NVIC_ICER3       (*(volatile uint32_t *)0xE000E18Cu)
typedef int (*fw_serial_read_fn)(void *buf, uint32_t n);      /* usb_serial_read: no yield, returns bytes read */
typedef int (*fw_serial_putc_fn)(int c);                       /* usb_serial_putchar: dropped if USB is not up */
#define fw_serial_read      ((fw_serial_read_fn)0x600AFE0Du)
#define fw_serial_putc      ((fw_serial_putc_fn)0x600AFFD9u)

/* ---- the UI -----------------------------------------------------------------------------------------------
 * Screens are objects whose first word is an 8-slot method table: enter(view, arg), +04 (shared), input(view,
 * action), update(view) each loop, draw(view) each frame, +14, and two flags (+18, +1C). set_view(ui, id) leaves
 * the old screen, fetches fw_views[id] (30 slots, 7 is empty in this build) and enters it. The current id is at
 * ui + 0x15. Input actions are the m8c key bits of the chord: EDIT 01, OPT 02, RIGHT 04, PLAY 08, SHIFT 10,
 * DOWN 20, UP 40, LEFT 80. Text goes into a 40 x 24 character grid (fw_grid + 0x10 + row * 40 + col) that the
 * display task draws and sends to m8c. */
#define fw_ui               ((uint8_t *)0x20015458u)
#define FW_UI_VIEW          0x15
#define FW_UI_VISUALIZER    0x00    /* u8: the visualizer is on (all four directions: the router 0x6004C6C8 toggles it) */
#define FW_VIEW_FREE        7                           /* the empty slot core's MODS page takes */
#define FW_HAS_VIEW_TABLE   0                           /* set_view is a switch: core_view (ev_view) takes id 7 */
#define FW_VIEW_SETTINGS    0x1C
#define fw_settings         ((volatile uint8_t *)0x20015F50u)   /* SYSTEM SETTINGS: +4 cursor x, +5 cursor y */
#define fw_grid             ((uint8_t *)0x20012464u)
#define FW_GRID_COLS        40
#define FW_GRID_ROWS        24
typedef void (*fw_set_view_fn)(void *ui, int view);
typedef void (*fw_text_fn)(void *grid, int col, int row, const char *s);
#define fw_set_view         ((fw_set_view_fn)0x6004C13Du)
#define fw_text             ((fw_text_fn)0x6007878Bu)
/* Pixels: the firmware's fill-rect (129 callers; the visualizer's tracks draw with it). It skips a rect that
 * starts right of the clip column (grid + 0x12EA, 0 = none) and trims one that crosses it, sends m8c the rectangle
 * (0xFE) when the display stream is on, then draws a line or a fill into the frame. The screen is 480 x 320;
 * colours are RGB565. Draw in ev_vis_draw (the visualizer) or ev_draw: what you draw lasts until something
 * draws over it. */
typedef void (*fw_rect_fn)(void *grid, int x, int y, int w, int h, uint16_t rgb565);
#define fw_rect             ((fw_rect_fn)0x60078C35u)
/* The frame refresh's gate: it draws a frame only when fw_millis - this > 15 (0x6004B53C), then stores fw_millis
 * here (0x6004B5B4). Literals 0x6004B704 (millis) and 0x6004B708 (this). Setting it to fw_millis before the
 * refresh (ev_draw) skips a frame; to fw_millis - 16 lets one through. */
#define fw_frame_last       (*(volatile uint32_t *)0x2001B4DCu)
/* The visualizer's per-track scope (0x6004A64A, called from 0x6004B606 for each of the 8 tracks): it redraws the
 * columns of the track's scope that changed, with fill-rects. Core's ev_vis_scope sits on that call. */
/* m8c's screen stream (the remote display, 0x200159A4): fill-rect and text send it their frames unless +0x19 is set,
 * and the visualizer sets it on entry (0x6004B15C) so the scopes don't flood USB; leaving clears it. */
/* The input router (ev_key's target): what a key action does on the current screen, the visualizer's toggle (0xE4)
 * included. m8c's keys don't reach it while the visualizer is open. */
typedef void (*fw_router_fn)(void *ui, int action);
#define fw_input_router     ((fw_router_fn)0x6004C6C9u)
#define fw_remote           ((volatile uint8_t *)0x200159A4u)
#define FW_REMOTE_PAUSED    0x19u
typedef void (*fw_vis_scope_fn)(void *scope);
#define fw_vis_scope_draw   ((fw_vis_scope_fn)0x6004A64Bu)
/* The frame refresh's normal branch (0x6004B638) draws, besides the view, the routines below (each r0 = its object):
 * among them the right-hand column (tempo, the tracks' notes, the view map) that keeps repainting while a song plays.
 * Core's own full-screen pages (MOD LOADER, OPTIONS) skip them (`calls` sites core_side_*). */
typedef void (*fw_side_fn)(void *obj);
#define FW_SIDE_0           ((fw_side_fn)0x600474C5u)   /* bl at 0x6004B642, r0 0x200123F8 */
#define FW_SIDE_1           ((fw_side_fn)0x600480F9u)   /* bl at 0x6004B680, r0 0x20015AE0 */
/* 0x6004CB7C (bl at 0x6004B68A, r0 fw_ui) is the view-draw dispatcher: it calls the view's draw (+0x10) and, when
 * the view's +0x18 says 0 (core's does), first these, the column's tracks among them: */
#define FW_SIDE_2           ((fw_side_fn)0x6004B8C9u)   /* bl at 0x6004CB94, r0 fw_ui */
#define FW_SIDE_5           ((fw_side_fn)0x6004A549u)   /* bl at 0x6004CBA0 */
#define FW_SIDE_6           ((fw_side_fn)0x60049665u)   /* bl at 0x6004CBAC, r0 a track's object, 8 times */
#define FW_SIDE_7           ((fw_side_fn)0x600490B9u)   /* bl at 0x6004CBB6 */
#define FW_SIDE_3           ((fw_side_fn)0x600496F5u)   /* bl at 0x6004B696, r0 0x2001BC94 */
#define FW_SIDE_4           ((fw_side_fn)0x6004B2FDu)   /* bl at 0x6004B6EC, r0 the refresh's object: the output meters */
#define FW_SCREEN_W         480
#define FW_SCREEN_H         320
#define FW_RGB(r, g, b)     ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
#define FW_VIEW_SHARED_04   0x600A4359u                 /* the +04 method most screens share */
#define FW_VIEW_NOP         0x600A434Du                 /* an empty method */
#define FW_VIEW_FLAG_18     0x600A4351u                 /* the +18 / +1C flags SETTINGS uses: return 1; +18: the
                                                           screen keeps the right-hand column (0x6004CB7C) */
#define FW_VIEW_FLAG_1C     0x600A4355u                 /* +1C: the oscilloscope along the top (0x6004B6A8) */
enum { FW_KEY_EDIT = 0x01, FW_KEY_OPT = 0x02, FW_KEY_RIGHT = 0x04, FW_KEY_PLAY = 0x08, FW_KEY_SHIFT = 0x10,
       FW_KEY_DOWN = 0x20, FW_KEY_UP = 0x40, FW_KEY_LEFT = 0x80 };

/* The theme (SYSTEM SETTINGS > THEME). The system settings are a 0xCC-byte struct the firmware keeps in EEPROM
 * (+0xC8 a checksum the save works out; the save writes only the bytes that changed). +0x24: the 13 colours, R G B
 * each, in the .m8t file's order (BACKGROUND, TEXT:EMPTY/INFO/DEFAULT/VALUE/TITLES, PLAY MARKERS, CURSOR, SELECTION,
 * SCOPE/SLIDER, METER LOW/MID/PEAK); +0x4B: the theme's name, 13 bytes, 0-padded (loading a .m8t sets it).
 * The screen draws from an RGB565 palette set an entry at a time (set_pal ignores its first argument); the redraw
 * with 1 repaints every view in it. That is what loading a .m8t does (0x600770B8's loop). */
#define fw_sys              ((uint8_t *)0x200159C0u)
#define FW_SYS_THEME        0x24u
#define FW_SYS_THEME_NAME   0x4Bu
typedef void (*fw_sys_save_fn)(void *sys);
typedef void (*fw_set_pal_fn)(void *unused, int index, int r, int g, int b);
typedef void (*fw_redraw_fn)(void *obj, int full);
#define fw_sys_save         ((fw_sys_save_fn)0x600A7319u)
#define fw_set_pal          ((fw_set_pal_fn)0x600A5655u)
#define fw_redraw           ((fw_redraw_fn)0x6004AF19u)
#define FW_REDRAW_OBJ       ((void *)0x200137F8u)

/* The extended theme (core 0.7). Every text cell has an attribute byte (grid + 0x3D1 + row * 40 + col, beside its
 * character at grid + 0x10) that the draw loop (ITCM 0x18B84) turns into a palette index: '.' '/' '0'..'7' are 0..9,
 * '8'..'C' are 1..12, '5' and '6' swap fg and bg (the cursor and selection blocks), 0xAE is skipped, and 'D'..'R' are
 * 13..27, past the firmware's 13 entries: no screen uses them. The loop loads the palette's address from a literal
 * in ITCM (FW_ATTR_PAL_LIT); core points it at a 28-entry table of its own. The frame refresh draws only once
 * FW_FRAME_MS have passed since fw_frame_last. */
#define FW_PALETTE          ((volatile const uint32_t *)0x2000BC20u)
#define FW_ATTR_PAL_LIT     ((volatile uint32_t *)0x00018C1Cu)
#define FW_GRID_CHARS       0x10u
#define FW_GRID_ATTR        0x3D1u
#define FW_FRAME_MS         16u

/* Teensyduino's crash record (CrashReport): written by the fault handler, kept across the reboot */
#define fw_fault_info       ((const volatile uint32_t *)0x2027FF80u)

#endif
