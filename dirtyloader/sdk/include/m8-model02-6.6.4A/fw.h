/* SPDX-License-Identifier: GPL-2.0-or-later */
/* M8 Model:02 6.6.4A: the firmware locations core and loadable mods use: the same names as m8-headless/fw.h and
 * m8-model02/fw.h. 6.6.4A Model:02 is built like Headless 6.6.4A where 6.6.2A Model:02 was not (one audio engine
 * object, a view table, 0x248-byte players); its touch screen, visualizer, right-hand column, 32-frame audio
 * blocks and track strips are the Model:02's. Each address was found from both 6.6.2A Model:02 and Headless 6.6.4A
 * and checked by hand; dirtyloader/core/bindings/m8_6.6.4A_model02.json and docs/MODEL02-664-PORT.md record how.
 * Built and checked against the stock image, not yet run on a unit. */
#ifndef DIRTYLOADER_M8_MODEL02_FW_H
#define DIRTYLOADER_M8_MODEL02_FW_H

#include <stdint.h>

#undef DL_FW                                    /* dl/mod.h's default is 0, "any firmware" */
#define DL_FW 0x02060604u                       /* 6.6.4A Model:02 (0x02: the model) */

#define fw_millis   (*(volatile uint32_t *)0x2004054Cu)
/* Teensyduino's _VectorsRam: the startup stores it in VTOR (the literal at 0x60001600, as 6.6.2A) */
#define FW_VECTORS  ((volatile uint32_t *)0x2000C000u)
/* Flash for mods (core 0.7), as headless: 1 MB, clear of the firmware and core's loader; the chip is 16 MB, the
 * EEPROM emulation at 0x60FC0000. Teensyduino's routines, in ITCM. */
#define FW_MOD_FLASH        0x60600000u
#define FW_MOD_FLASH_END    0x60700000u
typedef void (*fw_flash_write_fn)(void *addr, const void *data, uint32_t len);
typedef void (*fw_flash_erase_fn)(void *addr);
#define fw_flash_write          ((fw_flash_write_fn)0x0002A3FDu)
#define fw_flash_erase_sector   ((fw_flash_erase_fn)0x0002A4E9u)

/* ---- SdFat 2.x as linked into this build -------------------------------------------------------------------
 * FsBaseFile is 0x40 bytes: 0x38 bytes of storage for the open FatFile (0x24) or ExFatFile (0x38), then
 * pointers to whichever is open. fw_sd is the SdFs volume setup() mounts. */
struct fw_file {
    uint8_t mem[0x38];
    void *fat;                                  /* FatFile *, or 0 */
    void *exfat;                                /* ExFatFile *, or 0 */
};
#define fw_sd               ((void *)0x200379C0u)
/* The firmware's storage object: +4 is nonzero while a card is mounted. Check FW_SD_MOUNTED() before any
 * file call, as the firmware checks before its own. fw_sd_ready() returns the flag after trying to mount a
 * card inserted since boot; it masks the audio interrupt while it tries, so core uses only the flag. */
typedef int (*fw_sd_ready_fn)(void *storage);
#define fw_storage          ((void *)0x2001C48Cu)
#define fw_sd_ready         ((fw_sd_ready_fn)0x60080605u)
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

#define fw_file_open        ((fw_open_fn)0x600B2381u)
#define fw_file_open_next   ((fw_open_next_fn)0x600B24B9u)
#define fw_file_close       ((fw_close_fn)0x600B2359u)
#define fw_fat_read         ((fw_io_fn)0x600B0AE9u)
#define fw_exfat_read       ((fw_io_fn)0x600AF0EDu)
#define fw_fat_write        ((fw_io_fn)0x600B111Du)
#define fw_exfat_write      ((fw_io_fn)0x600AFBC1u)
#define fw_fat_seek         ((fw_fat_seek_fn)0x600B0D8Du)
#define fw_exfat_seek       ((fw_exfat_seek_fn)0x600AF2B9u)
#define fw_fat_name         ((fw_name_fn)0x600B1D19u)
#define fw_exfat_name       ((fw_name_fn)0x600AFE8Du)

/* SdFat directories: FatFile::mkdir(this, parent, path, pFlag) / ExFatFile::mkdir; the volume's working
 * directory (the parent the firmware passes) is +0x448 of the FatVolume / ExFatVolume at fw_sd +0x480 / +0x484.
 * `this` is a zeroed FatFile (0x24 B) or ExFatFile (0x38 B), left open on success: close it. */
typedef int (*fw_mkdir_fn)(void *file, void *parent, const char *path, int pflag);
typedef int (*fw_fclose_fn)(void *file);
#define fw_fat_vol          (*(void *volatile *)((uint8_t *)fw_sd + 0x480))
#define fw_exfat_vol        (*(void *volatile *)((uint8_t *)fw_sd + 0x484))
#define FW_VOL_CWD          0x448
#define fw_fat_mkdir        ((fw_mkdir_fn)0x600B0805u)
#define fw_exfat_mkdir      ((fw_mkdir_fn)0x600AFA05u)
#define fw_fat_fclose       ((fw_fclose_fn)0x600B05F5u)
#define fw_exfat_fclose     ((fw_fclose_fn)0x600AEF99u)
/* FatFile::remove(this) / ExFatFile::remove(this): delete an open file (opened FW_O_RDWR); it is closed after */
typedef int (*fw_remove_fn)(void *file);
#define fw_fat_remove       ((fw_remove_fn)0x600B1A39u)
#define fw_exfat_remove     ((fw_remove_fn)0x600AF5C9u)

/* ---- USB MIDI (Teensyduino usb_midi.c) -------------------------------------------------------------------------
 * A USB MIDI packet is a word: byte 0 cable << 4 | code index (CIN), bytes 1-3 the MIDI bytes (status first).
 * usb_midi_read (0x600B570C, what usbMIDI.read() runs) takes one packet from usb_midi_read_message and calls
 * the handlers the firmware set; usb_midi_write_packed queues one packet for the host. Core's ev_midi sees each
 * packet usb_midi_read takes, ev_midi_out each packet written. */
typedef uint32_t (*fw_midi_read_fn)(void);
typedef void (*fw_midi_write_fn)(uint32_t packet);
#define fw_usb_midi_read_message ((fw_midi_read_fn)0x600B5665u)
#define fw_usb_midi_write_packed ((fw_midi_write_fn)0x600B51E1u)
#define FW_MIDI_READ_CALL   0x600B5712u        /* usb_midi_read's bl usb_midi_read_message: core's ev_midi site */
/* usbMIDI's partial-SysEx handler (data, len, last): the firmware sets it to 0x600ACCF1 in setup(); core chains it */
#define fw_sysex_handler    (*(volatile uint32_t *)0x2004093Cu)
#define fw_usb_configuration (*(volatile uint8_t *)0x200418B1u)   /* nonzero once the host configured USB */

/* ---- the song, the mixer, the sequencer --------------------------------------------------------------------------
 * The song in RAM; the firmware's accessors return pointers into it: a phrase step is 9 bytes (note, velocity,
 * instrument, 3 x (command, value)), an instrument 0xD7 bytes. */
#define fw_song             ((uint8_t *)0x2025A570u)
#define FW_PHRASE_STEP(p, s) (fw_song + 0xA6C + (p) * 0x90 + (s) * 9)
#define FW_INSTRUMENT(i)    (fw_song + 0x139BC + (i) * 0xD7)
#define fw_songs            ((void *)0x2001C48Cu)                 /* the song loader/writer's object */
typedef int (*fw_inst_load_fn)(void *songs, const char *path, int slot, int flag);
typedef int (*fw_inst_save_fn)(void *songs, const char *path, int slot);
#define fw_inst_load        ((fw_inst_load_fn)0x6008210Du)       /* ev_inst_load's routine (flag 0) */
#define fw_inst_save        ((fw_inst_save_fn)0x600827B9u)       /* ev_inst_save's routine */
/* The audio engine (a float Teensy Audio graph: 32-frame blocks of float, 44.1 kHz) is one object, as on headless:
 * 0x2000C780, a function-local static the first call of 0x600A07AC builds (0x6009D9D4); 0x2002068C points at it.
 * Its objects sit at fixed offsets, not headless's: the Model:02's members differ (each offset below was matched,
 * instruction by instruction, with the headless one). Each object has a vtable in RAM whose first slot is update().
 * The master chain ends in the soft clip (+0x88D8, the only one of its class; headless +0x9750), which sends the same
 * blocks to the USB branch (+0x8538; headless +0x9308) and the I2S branch (+0x8920 -> +0x8984 -> +0x8AA8 -> +0x8AF0).
 * core's ev_audio_out wraps the soft clip's update(), so both outputs hear it. The graph has not been walked on a
 * 6.6.4A unit. audio_block_t: +0 ref count (u8), +4 float data[32] (the pool's blocks are 0x94 apart, as 6.6.2A). */
#define fw_audio_engine     ((uint8_t *)0x2000C780u)
#define FW_AUDIO_TAP        0x88D8u                                  /* the soft clip */
#define FW_AUDIO_USB        0x8538u                                  /* the USB branch's first node */
#define FW_AUDIO_TAP_OBJ    (fw_audio_engine + FW_AUDIO_TAP)        /* the tap object (core's ev_audio_out) */
#define FW_AUDIO_USB_OBJ    (fw_audio_engine + FW_AUDIO_USB)
/* The sequencer block sits 0x28 further into the engine than on headless (clock +0x3B8, playing +0x3E0, bpm +0x3E8,
 * mixer +0x408; headless +0x390/+0x3B8/+0x3C0/+0x3E0): play 0x600A1010 sets engine+0x3E0, set_tempo stores +0x3E8,
 * engine+0x3B8 holds the clock's vtable 0x20002060, and the code adds #0x3B8 5 times and #0x408 4 times (headless
 * #0x390 5, #0x3E0 2, neither in this build). Checked on a unit: +0x3E8 reads 120.0 at T 120. */
#define FW_CLOCK_OBJ        (fw_audio_engine + 0x3B8u)               /* the sequencer clock (ev_render_params' argument) */
#define fw_bpm              (*(volatile float *)(fw_audio_engine + 0x3E8u))   /* the tempo (set_tempo 0x600A1370 stores it) */
#define fw_mixer            (fw_audio_engine + 0x408u)               /* the mixer (headless: engine + 0x3E0) */
/* Spare DTCM for mods' buffers (core's ram_claim): .bss ends at 0x200418E0 (the reset handler's clear, literal
 * 0x6000142C), the stack grows down from 0x20050000. Not measured on this build: the same gap below the stack as
 * headless, where it was. */
#define FW_SPARE_RAM        0x20041A00u
#define FW_SPARE_RAM_END    0x2004B800u
/* The touch screen (ev_touch's argument): the touch engine 0x60086008 (called each loop) polls the controller
 * (0x6007ED14) into this object. x and y are calibrated to 0..1: x from the left, y from the BOTTOM; +0x58 is the
 * touch's start time while a finger is down (0 once it lifts, with x and y); +0x30 / +0x34 the movement since it came
 * down; +0x52 "a gesture happened". The poll and the gesture routine are the same code as 6.6.2A's. */
#define fw_touch            ((uint8_t *)0x2001C9E0u)
#define FW_TOUCH_X          0x40u
#define FW_TOUCH_Y          0x44u
#define FW_TOUCH_DOWN       0x58u
/* More of the graph (classes are unique; each vtable's update slot is in RAM, checked by the update() it holds):
 * - the 8 track voices: class slot 0x20002514; +0x3D the track; each transmits its block pair to its main strip and
 *   its reverb, delay and MFX sends
 * - send effects: MFX +0x34B0 (slot 0x20002D50, stereo in), delay +0x3234 (slot 0x20002F48, mono in), reverb +0x75F8
 *   (slot 0x200029F0, stereo in); they run after the tracks
 * - the sequencer clock +0x3B8 (slot 0x20002060): first in each block, before the tracks */
#define FW_SLOT_TRACK       0x20002514u
#define FW_SLOT_MFX         0x20002D50u
#define FW_SLOT_DELAY       0x20002F48u
#define FW_SLOT_REVERB      0x200029F0u
#define FW_SLOT_CLOCK       0x20002060u
/* The track voices, in the engine object: track 1's at +0x5E8, tracks 2..8 from +0xA7C, 0x574 apart (the engine's
 * constructor builds each with 0x6009D6F0). The voice class is 0x100 smaller than headless's, and its four strips
 * are 0x100 earlier: main +0x2E4, then the reverb, delay and MFX sends 0x6C apart, in headless's order. Each strip is
 * the Model:02's gain node (update ITCM 0x207A8, 6.6.2A's 0x203B8): +0x38 target, +0x3C current, +0x55 ramping,
 * +0x56 ramp on change; while ramping each sample's gain is +0x58 start + +0x5C step x table[phase], phase (+0x60)
 * going up 1/256 a sample, and only when it reaches 1 does +0x3C take the target. fw_gain_set sets a gain at once
 * (a ramp restarted every block would never finish). */
#define FW_TRACK_MAIN       0x2E4u
#define FW_TRACK_REVERB     0x350u
#define FW_TRACK_DELAY      0x3BCu
#define FW_TRACK_MFX        0x428u
#define FW_TRACK_STRIP(voice) ((uint8_t *)(voice) + FW_TRACK_MAIN)     /* a track voice's main strip (it contains it) */
#define FW_TRACK_VOICE(t)   ((t) ? fw_audio_engine + 0xA7Cu + 0x574u * ((t) - 1) : fw_audio_engine + 0x5E8u)
#define FW_VOICE_TRACK      0x3Du                       /* u8: the track (0..7) */
enum { FW_GAIN_DRY, FW_GAIN_MFX, FW_GAIN_DELAY, FW_GAIN_REVERB };
static inline uint8_t *fw_track_gain(int t, int which)
{
    static const uint16_t off[4] = { FW_TRACK_MAIN, FW_TRACK_MFX, FW_TRACK_DELAY, FW_TRACK_REVERB };
    if ((unsigned)t >= 8) return 0;
    uint8_t *voice = FW_TRACK_VOICE(t);
    return voice[FW_VOICE_TRACK] == (uint8_t)t ? voice + off[which & 3] : 0;
}
static inline void fw_gain_set(uint8_t *node, float g)
{
    node[0x55] = 0;
    *(volatile float *)(node + 0x38) = g;
    *(volatile float *)(node + 0x3C) = g;
    *(float *)(node + 0x60) = 1.0f;
}
/* The phrase view (object 0x2001A920, phrase number at +4): its vtable is in RAM. +0x34 redraws after a bulk edit
 * (cut / clear, paste, interpolate, rotate, the FILL generators, transposing a selection), +0x38 after a cell. */
#define fw_phrase_view      ((uint8_t *)0x2001A920u)
#define FW_SLOT_PHRASE_BULK 0x20001908u
#define FW_SLOT_PHRASE_CELL 0x2000190Cu
enum { FW_FX_MFX, FW_FX_DELAY, FW_FX_REVERB };
typedef void (*fw_audio_transmit_fn)(void *obj, void *block, int port);
typedef void (*fw_audio_release_fn)(void *block);
#define fw_audio_transmit   ((fw_audio_transmit_fn)0x0001C189u)  /* AudioStream::transmit (ITCM) */
#define fw_audio_release    ((fw_audio_release_fn)0x0001C11Du)   /* AudioStream::release (ITCM) */
#define FW_AUDIO_FRAMES     32                          /* Model:02: 32-frame blocks */
#define FW_AUDIO_RATE       44100
typedef void *(*fw_audio_alloc_fn)(void);
#define fw_audio_alloc      ((fw_audio_alloc_fn)0x0001BF1Du)        /* AudioStream::allocate (ITCM): ref count 1 */
#define fw_mute_mask        (*(volatile uint8_t *)(fw_mixer + 0x1B0u))  /* a bit per track (mute 0x6003CE7C reads both) */
#define fw_solo_mask        (*(volatile uint8_t *)(fw_mixer + 0x1B4u))
#define fw_seq_engine       ((uint8_t *)0x2001A96Cu)              /* ev_seq_tick's argument */
#define fw_sequencer        fw_audio_engine                        /* +FW_SEQ_PLAYING: playing */
#define FW_SEQ_PLAYING      0x3E0u
#define FW_PLAYER(t)        ((uint8_t *)0x2001A980u + 0x248 * (t))   /* a track's player: +0xC track, +0x4C the row */
#define FW_PLAYER_INST      0x178u                      /* the player's instrument: its FW_INSTRUMENT() data */
/* Modulators: each track has 4 (one per instrument MOD slot), 0xA8 apart, in groups 0x2B0 apart from fw_modulators.
 * +0xA0 points at the first of the track's group. Methods (vtable at +0): +0x04 output() and +0x08 amount(). As on
 * headless (not 6.6.2A Model:02), a group keeps the instrument's modulator bytes it was set up from at +0x2AC. */
#define fw_modulators       ((uint8_t *)0x20015570u)
#define FW_MODULATOR_SIZE   0xA8u
#define FW_MODULATOR_TRACK  0x2B0u
#define FW_MODULATOR_FIRST  0xA0u
#define FW_MODULATOR_INST   0x2ACu
#define FW_MODULATOR_INST_MODS(first) (*(const uint8_t *const *)((const uint8_t *)(first) + FW_MODULATOR_INST))
typedef float (*fw_mod_float_fn)(void *mod);
#define FW_MOD_OUTPUT(m)    ((*(fw_mod_float_fn const *const *)(m))[1](m))
#define FW_MOD_AMOUNT(m)    ((*(fw_mod_float_fn const *const *)(m))[2](m))
enum { FW_INST_WAV, FW_INST_MACRO, FW_INST_SAMPLER, FW_INST_MIDI_OUT, FW_INST_FM, FW_INST_HYPER, FW_INST_EXTERNAL };
#define FW_INST_MODS        0x3Fu
#define FW_INST_SIZE        0xD7u
enum { FW_ENGINE_FM, FW_ENGINE_HYPER, FW_ENGINE_MACRO, FW_ENGINE_SAMPLER, FW_ENGINE_WAV, FW_ENGINE_EXTERNAL,
       FW_ENGINE_MIDI_OUT, FW_ENGINES };
/* Each engine's class vtable is in RAM (DTCM .data): +0xF8 name(eng, dest) and +0x104 count(eng) list its
 * modulation destinations (0 = OFF). Found by the two methods each holds. Order: FW_ENGINE_*. */
#define FW_ENGINE_VTABLES   { 0x200019DCu, 0x200020ACu, 0x20002274u, 0x20002840u, 0x20001E78u, 0x20002A68u, 0x20001C1Cu }
#define FW_VT_DEST_NAME     0xF8u
#define FW_VT_DEST_COUNT    0x104u
#define FW_MOD_DESTS_MAX    16

/* core's API for mods (dl/core.h): a pointer to it sits after core's hook table (bindings: loader.ram + 0x208). */
#define DL_CORE_PTR         0x0002C1B8u

/* ---- USB serial (Teensyduino usb_serial.c): what m8c talks to ------------------------------------------------
 * The m8c command parser (fw_m8c_parse, 0x6007D0CC) drains every waiting byte; core's ev_serial handler runs at
 * its entry and peeks the receive queue first. Received data waits in RX_NUM (8) 512-byte buffers queued in
 * rx_list (a ring of 9, head and tail are bytes); rx_index is how far each buffer has been read. Mask the USB
 * interrupt (IRQ 113) while looking, as usb_serial_read does. */
#define fw_rx_available     (*(volatile uint32_t *)0x20033AE8u)
#define fw_rx_head          (*(volatile uint8_t *)0x2004189Fu)
#define fw_rx_tail          (*(volatile uint8_t *)0x200418A2u)
#define fw_rx_list          ((volatile uint8_t *)0x20033B3Cu)
#define fw_rx_index         ((volatile uint16_t *)0x20033B14u)
#define fw_rx_buffer        ((volatile uint8_t *)0x20279760u)
#define FW_RX_RING          9
#define FW_RX_BUF           512
#define FW_USB_IRQ_BIT      (1u << (113 - 96))
#define FW_NVIC_ISER3       (*(volatile uint32_t *)0xE000E10Cu)
#define FW_NVIC_ICER3       (*(volatile uint32_t *)0xE000E18Cu)
typedef int (*fw_serial_read_fn)(void *buf, uint32_t n);      /* usb_serial_read: no yield, returns bytes read */
typedef int (*fw_serial_putc_fn)(int c);                       /* usb_serial_putchar: dropped if USB is not up */
#define fw_serial_read      ((fw_serial_read_fn)0x600B60B1u)
#define fw_serial_putc      ((fw_serial_putc_fn)0x600B627Du)

/* ---- the UI -----------------------------------------------------------------------------------------------
 * Screens are objects whose first word is an 8-slot method table: enter(view, arg), +04 (shared), input(view,
 * action), update(view) each loop, draw(view) each frame, +14, and two flags (+18, +1C). set_view(ui, id) leaves
 * the old screen, fetches fw_views[id] (30 slots, 7 is empty in this build, as headless) and enters it. The current
 * id is at ui + 0x15. Input actions are the m8c key bits of the chord: EDIT 01, OPT 02, RIGHT 04, PLAY 08, SHIFT 10,
 * DOWN 20, UP 40, LEFT 80. Text goes into a 40 x 24 character grid (fw_grid + 0x10 + row * 40 + col) that the
 * display task draws and sends to m8c. */
#define fw_ui               ((uint8_t *)0x2001BD34u)
#define FW_UI_VIEW          0x15
#define FW_UI_VISUALIZER    0x00    /* u8: the visualizer is on (all four directions: the router 0x6004F620 toggles it) */
#define fw_views            ((void *volatile *)0x20000BD8u)
#define FW_VIEWS            30
#define FW_VIEW_FREE        7                           /* the empty slot core's MODS page takes */
#define FW_HAS_VIEW_TABLE   1                           /* 6.6.4A's set_view reads fw_views (6.6.2A's was a switch) */
#define FW_VIEW_SETTINGS    0x1C
#define fw_settings         ((volatile uint8_t *)0x2001C87Cu)   /* SYSTEM SETTINGS (fw_views[0x1C]): +4 cursor x, +5 y */
#define fw_grid             ((uint8_t *)0x20018CF0u)
#define FW_GRID_COLS        40
#define FW_GRID_ROWS        24
typedef void (*fw_set_view_fn)(void *ui, int view);
typedef void (*fw_text_fn)(void *grid, int col, int row, const char *s);
#define fw_set_view         ((fw_set_view_fn)0x6004EEA5u)
#define fw_text             ((fw_text_fn)0x6007BDAFu)
/* Pixels: the firmware's fill-rect (the visualizer's tracks draw with it). It skips a rect that starts right of the
 * clip column (grid + 0x12EA, 0 = none) and trims one that crosses it, sends m8c the rectangle (0xFE) when the
 * display stream is on, then draws a line or a fill into the frame. The screen is 480 x 320; colours are RGB565.
 * Draw in ev_vis_draw (the visualizer) or ev_draw: what you draw lasts until something draws over it. */
typedef void (*fw_rect_fn)(void *grid, int x, int y, int w, int h, uint16_t rgb565);
#define fw_rect             ((fw_rect_fn)0x6007C285u)
/* The frame refresh's gate: it draws a frame only when fw_millis - this > 15 (0x6004E240), then stores fw_millis
 * here. Literals 0x6004E420 (millis) and 0x6004E424 (this). Setting it to fw_millis before the refresh (ev_draw)
 * skips a frame; to fw_millis - 16 lets one through. */
#define fw_frame_last       (*(volatile uint32_t *)0x200206F0u)
/* The visualizer's per-track scope (0x6004D31A, called from 0x6004E312 for each of the 8 tracks): it redraws the
 * columns of the track's scope that changed, with fill-rects. Core's ev_vis_scope sits on that call. */
/* m8c's screen stream (the remote display, 0x2001C280): fill-rect and text send it their frames unless +0x19 is set,
 * and the visualizer sets it on entry (0x6004DE36) so the scopes don't flood USB; leaving clears it. */
/* The input router (ev_key's target): what a key action does on the current screen, the visualizer's toggle (0xE4)
 * included. m8c's keys don't reach it while the visualizer is open. */
typedef void (*fw_router_fn)(void *ui, int action);
#define fw_input_router     ((fw_router_fn)0x6004F621u)
#define fw_remote           ((volatile uint8_t *)0x2001C280u)
#define FW_REMOTE_PAUSED    0x19u
typedef void (*fw_vis_scope_fn)(void *scope);
#define fw_vis_scope_draw   ((fw_vis_scope_fn)0x6004D31Bu)
/* The frame refresh's normal branch draws, besides the view, the routines below (each r0 = its object): among them
 * the right-hand column (tempo, the tracks' notes, the view map) that keeps repainting while a song plays. Core's
 * own full-screen pages (MOD LOADER, OPTIONS) skip them (`calls` sites core_side_*). */
typedef void (*fw_side_fn)(void *obj);
#define FW_SIDE_0           ((fw_side_fn)0x6004A1BDu)   /* bl at 0x6004E376 */
#define FW_SIDE_1           ((fw_side_fn)0x6004ADB1u)   /* bl at 0x6004E3B0 */
/* 0x6004F4A4 (bl at 0x6004E3BA, r0 fw_ui) is the view-draw dispatcher: it calls the view's draw (+0x10) and, when
 * the view's +0x18 says 0 (core's does), first these, the column's tracks among them: */
#define FW_SIDE_2           ((fw_side_fn)0x6004E601u)   /* bl at 0x6004F4BC, r0 fw_ui */
#define FW_SIDE_5           ((fw_side_fn)0x6004D215u)   /* bl at 0x6004F4C8 */
#define FW_SIDE_6           ((fw_side_fn)0x6004C331u)   /* bl at 0x6004F4D4, r0 a track's object, 8 times */
#define FW_SIDE_7           ((fw_side_fn)0x6004BD85u)   /* bl at 0x6004F4DE */
#define FW_SIDE_3           ((fw_side_fn)0x6004C3C1u)   /* bl at 0x6004E3C6 */
#define FW_SIDE_4           ((fw_side_fn)0x6004DFF9u)   /* bl at 0x6004E408: the output meters */
#define FW_SCREEN_W         480
#define FW_SCREEN_H         320
#define FW_RGB(r, g, b)     ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
#define FW_VIEW_SHARED_04   0x600AA52Du                 /* the +04 method most screens share */
#define FW_VIEW_NOP         0x600AA521u                 /* an empty method */
#define FW_VIEW_FLAG_18     0x600AA525u                 /* the +18 / +1C flags SETTINGS uses: return 1; +18: the
                                                           screen keeps the right-hand column (0x6004F4A4) */
#define FW_VIEW_FLAG_1C     0x600AA529u                 /* +1C: the oscilloscope along the top */
enum { FW_KEY_EDIT = 0x01, FW_KEY_OPT = 0x02, FW_KEY_RIGHT = 0x04, FW_KEY_PLAY = 0x08, FW_KEY_SHIFT = 0x10,
       FW_KEY_DOWN = 0x20, FW_KEY_UP = 0x40, FW_KEY_LEFT = 0x80 };

/* The theme (SYSTEM SETTINGS > THEME). The system settings are a 0xCC-byte struct the firmware keeps in EEPROM
 * (+0xC8 a checksum the save works out; the save writes only the bytes that changed). +0x24: the 13 colours, R G B
 * each, in the .m8t file's order (BACKGROUND, TEXT:EMPTY/INFO/DEFAULT/VALUE/TITLES, PLAY MARKERS, CURSOR, SELECTION,
 * SCOPE/SLIDER, METER LOW/MID/PEAK); +0x4B: the theme's name, 13 bytes, 0-padded (loading a .m8t sets it).
 * The screen draws from an RGB565 palette set an entry at a time (set_pal ignores its first argument); the redraw
 * with 1 repaints every view in it. */
#define fw_sys              ((uint8_t *)0x2001C29Cu)
#define FW_SYS_THEME        0x24u
#define FW_SYS_THEME_NAME   0x4Bu
typedef void (*fw_sys_save_fn)(void *sys);
typedef void (*fw_set_pal_fn)(void *unused, int index, int r, int g, int b);
typedef void (*fw_redraw_fn)(void *obj, int full);
#define fw_sys_save         ((fw_sys_save_fn)0x600AD5BFu)
#define fw_set_pal          ((fw_set_pal_fn)0x600AB981u)
#define fw_redraw           ((fw_redraw_fn)0x6004DBF1u)
#define FW_REDRAW_OBJ       ((void *)0x2001A084u)

/* The extended theme (core 0.7). Every text cell has an attribute byte (grid + 0x3D1 + row * 40 + col, beside its
 * character at grid + 0x10) that the draw loop (ITCM 0x18F6C) turns into a palette index: '.' '/' '0'..'7' are 0..9,
 * '8'..'C' are 1..12, '5' and '6' swap fg and bg (the cursor and selection blocks), 0xAE is skipped, and 'D'..'R' are
 * 13..27, past the firmware's 13 entries: no screen uses them. The loop loads the palette's address from a literal
 * in ITCM (FW_ATTR_PAL_LIT); core points it at a 28-entry table of its own. The frame refresh draws only once
 * FW_FRAME_MS have passed since fw_frame_last. */
#define FW_PALETTE          ((volatile const uint32_t *)0x2000BD08u)
#define FW_ATTR_PAL_LIT     ((volatile uint32_t *)0x00018FECu)
#define FW_GRID_CHARS       0x10u
#define FW_GRID_ATTR        0x3D1u
#define FW_FRAME_MS         16u

/* Teensyduino's crash record (CrashReport): written by the fault handler, kept across the reboot */
#define fw_fault_info       ((const volatile uint32_t *)0x2027FF80u)

#endif
