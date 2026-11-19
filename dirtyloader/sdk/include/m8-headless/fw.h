/* SPDX-License-Identifier: GPL-2.0-or-later */
/* M8 Headless 6.6.4A: the firmware locations core 0.3 and loadable mods use.
 * docs/FIRMWARE-MAP.md and dirtyloader/core/bindings/m8_6.6.4A_headless.json record how each was found. */
#ifndef DIRTYLOADER_M8_HEADLESS_FW_H
#define DIRTYLOADER_M8_HEADLESS_FW_H

#include <stdint.h>

#undef DL_FW                                    /* dl/mod.h's default is 0, "any firmware" */
#define DL_FW 0x00060604u                       /* 6.6.4A headless */

#define fw_millis   (*(volatile uint32_t *)0x20040264u)
#define FW_VECTORS  ((volatile uint32_t *)0x2000B800u)   /* Teensyduino's _VectorsRam (VTOR): core's ev_render_*, ev_crash */
/* Flash for mods (core 0.7): a mod that doesn't fit in ITCM runs its code from here; core installs it from the SD
 * card. 1 MB, erased on a stock unit (read back on one), clear of the firmware, core's loader past it, and
 * Teensyduino's EEPROM emulation at the top (0x607C0000). Written with Teensyduino's own routines, in ITCM because
 * flash can't be read while it is written: eepromemu_flash_write (one page: up to 256 bytes, interrupts off,
 * D-cache lines dropped) and eepromemu_flash_erase_sector (4 KB). */
#define FW_MOD_FLASH        0x60600000u
#define FW_MOD_FLASH_END    0x60700000u
typedef void (*fw_flash_write_fn)(void *addr, const void *data, uint32_t len);
typedef void (*fw_flash_erase_fn)(void *addr);
#define fw_flash_write          ((fw_flash_write_fn)0x00027FD1u)
#define fw_flash_erase_sector   ((fw_flash_erase_fn)0x000280BDu)

/* ---- SdFat 2.x as linked into this build -------------------------------------------------------------------
 * FsBaseFile is 0x40 bytes: 0x38 bytes of storage for the open FatFile (0x24) or ExFatFile (0x38), then
 * pointers to whichever is open. fw_sd is the SdFs volume setup() mounts. */
struct fw_file {
    uint8_t mem[0x38];
    void *fat;                                  /* FatFile *, or 0 */
    void *exfat;                                /* ExFatFile *, or 0 */
};
#define fw_sd               ((void *)0x200376ECu)
/* The firmware's storage object: +4 is nonzero while a card is mounted. Check FW_SD_MOUNTED() before any
 * file call, as the firmware checks before its own. fw_sd_ready() returns the flag after trying to mount a
 * card inserted since boot; it masks the audio interrupt while it tries, so core uses only the flag. */
typedef int (*fw_sd_ready_fn)(void *storage);
#define fw_storage          ((void *)0x2001C8FCu)
#define fw_sd_ready         ((fw_sd_ready_fn)0x6007A3FDu)
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

#define fw_file_open        ((fw_open_fn)0x600A0895u)
#define fw_file_open_next   ((fw_open_next_fn)0x600A09CDu)
#define fw_file_close       ((fw_close_fn)0x600A086Du)
#define fw_fat_read         ((fw_io_fn)0x6009EFFDu)
#define fw_exfat_read       ((fw_io_fn)0x6009D601u)
#define fw_fat_write        ((fw_io_fn)0x6009F631u)
#define fw_exfat_write      ((fw_io_fn)0x6009E0D5u)
#define fw_fat_seek         ((fw_fat_seek_fn)0x6009F2A1u)
#define fw_exfat_seek       ((fw_exfat_seek_fn)0x6009D7CDu)
#define fw_fat_name         ((fw_name_fn)0x600A022Du)
#define fw_exfat_name       ((fw_name_fn)0x6009E3A1u)

/* SdFat directories: FatFile::mkdir(this, parent, path, pFlag) / ExFatFile::mkdir; the volume's working
 * directory (the parent the firmware passes) is +0x448 of the FatVolume / ExFatVolume at fw_sd +0x480 / +0x484.
 * `this` is a zeroed FatFile (0x24 B) or ExFatFile (0x38 B), left open on success: close it. */
typedef int (*fw_mkdir_fn)(void *file, void *parent, const char *path, int pflag);
typedef int (*fw_fclose_fn)(void *file);
#define fw_fat_vol          (*(void *volatile *)((uint8_t *)fw_sd + 0x480))
#define fw_exfat_vol        (*(void *volatile *)((uint8_t *)fw_sd + 0x484))
#define FW_VOL_CWD          0x448
#define fw_fat_mkdir        ((fw_mkdir_fn)0x6009ED19u)
#define fw_exfat_mkdir      ((fw_mkdir_fn)0x6009DF19u)
#define fw_fat_fclose       ((fw_fclose_fn)0x6009EB09u)
#define fw_exfat_fclose     ((fw_fclose_fn)0x6009D4ADu)
/* FatFile::remove(this) / ExFatFile::remove(this): delete an open file (opened FW_O_RDWR); it is closed after */
typedef int (*fw_remove_fn)(void *file);
#define fw_fat_remove       ((fw_remove_fn)0x6009FF4Du)
#define fw_exfat_remove     ((fw_remove_fn)0x6009DADDu)

/* ---- USB MIDI (Teensyduino usb_midi.c) -------------------------------------------------------------------------
 * A USB MIDI packet is a word: byte 0 cable << 4 | code index (CIN), bytes 1-3 the MIDI bytes (status first).
 * usb_midi_read (0x600A3764, what usbMIDI.read() runs) takes one packet from usb_midi_read_message and calls
 * the handlers the firmware set; usb_midi_write_packed queues one packet for the host. Core's ev_midi sees each
 * packet usb_midi_read takes, ev_midi_out each packet written. */
typedef uint32_t (*fw_midi_read_fn)(void);
typedef void (*fw_midi_write_fn)(uint32_t packet);
#define fw_usb_midi_read_message ((fw_midi_read_fn)0x600A36BDu)
#define fw_usb_midi_write_packed ((fw_midi_write_fn)0x600A3239u)
#define FW_MIDI_READ_CALL   0x600A376Au
/* usbMIDI's partial-SysEx handler (data, len, last): the firmware sets it to 0x6009C0B9 in setup(); core 0.5 chains it */
#define fw_sysex_handler    (*(volatile uint32_t *)0x20040654u)
#define fw_usb_configuration (*(volatile uint8_t *)0x2004159Fu)   /* nonzero once the host configured USB */     /* usb_midi_read's bl usb_midi_read_message: core's ev_midi site */

/* ---- the song, the mixer, the sequencer (Ghidra, core 0.5's sites) ---------------------------------------------
 * The song in RAM; the firmware's accessors return pointers into it: a phrase step is 9 bytes (note, velocity,
 * instrument, 3 x (command, value)), an instrument 0xD7 bytes. */
#define fw_song             ((uint8_t *)0x2025F674u)
#define FW_PHRASE_STEP(p, s) (fw_song + 0xA6C + (p) * 0x90 + (s) * 9)
#define FW_INSTRUMENT(i)    (fw_song + 0x139BC + (i) * 0xD7)
#define fw_mixer            ((uint8_t *)0x2000C260u)
#define fw_songs            ((void *)0x2001C8FCu)                 /* the song loader/writer's object */
typedef int (*fw_inst_load_fn)(void *songs, const char *path, int slot, int flag);
typedef int (*fw_inst_save_fn)(void *songs, const char *path, int slot);
#define fw_inst_load        ((fw_inst_load_fn)0x6007BDD1u)       /* ev_inst_load's routine (flag 0) */
#define fw_inst_save        ((fw_inst_save_fn)0x6007C47Du)       /* ev_inst_save's routine */
/* The audio engine (a float Teensy Audio graph: 64-frame blocks of float, 44.1 kHz, ~689 blocks a second) is the
 * object at 0x2000BE80 (the sequencer's). Its objects sit at fixed offsets; each has a vtable in RAM whose first
 * slot is update(). The master chain ends in the node at +0x9750 (the soft clip, by its place in the same graph on
 * the Model:02), which sends the same
 * blocks two ways: to +0x9308, the USB branch, and to +0x9798 -> +0x97FC -> +0x9920 -> +0x9968, the I2S branch (the
 * headphone out). core's ev_audio_out wraps the soft clip's update() and changes its input before the split, so
 * both outputs hear it (wrapping +0x9308 reached USB only: the I2S branch had copied the blocks first).
 * Walked on the unit through each node's destination list (+0x1C). audio_block_t: +0 ref count (u8),
 * +4 float data[64]. */
#define fw_audio_engine     ((uint8_t *)0x2000BE80u)
#define FW_AUDIO_TAP        0x9750u                                  /* the soft clip: the only one of its class */
#define FW_AUDIO_USB        0x9308u                                  /* the USB branch's first node */
#define FW_AUDIO_TAP_OBJ    (fw_audio_engine + FW_AUDIO_TAP)        /* the tap object (core's ev_audio_out) */
#define FW_CLOCK_OBJ        (fw_audio_engine + 0x390u)               /* the sequencer clock (ev_render_params' argument) */
#define fw_bpm              (*(volatile float *)(fw_audio_engine + 0x3C0u))   /* the tempo (set_tempo's store) */
/* Spare DTCM for mods' buffers (core's ram_claim hands it out): .bss ends at 0x200415E0 (the reset handler's clear)
 * and the stack grows down from 0x20050000. On hardware the gap still held power-up noise up to 0x2004EE00 after
 * a day of saves, loads and playback: the stack has never gone deeper than ~4.6 KB. Core keeps 14 KB clear of it. */
#define FW_SPARE_RAM        0x20041800u
#define FW_SPARE_RAM_END    0x2004B800u
/* More of the graph (classes are unique unless noted; each vtable's update slot is in RAM):
 * - the 8 track voices: class slot 0x20002348; +0x3D the track; +0x38 its engine voice; each transmits its block
 *   pair to its main strip (+0x3E4) and its reverb, delay and MFX sends (+0x450, +0x4BC, +0x528)
 * - send effects: MFX +0x3D08 (slot 0x20002B58, stereo in), delay +0x3A0C (slot 0x20002D50, mono in), reverb
 *   +0x7E50 (slot 0x20002814, stereo in, also gets the delay and MFX returns); they run after the tracks
 * - the sequencer clock +0x390 (slot 0x20001E94): first in each block, before the tracks */
#define FW_SLOT_TRACK       0x20002348u
#define FW_SLOT_MFX         0x20002B58u
#define FW_SLOT_DELAY       0x20002D50u
#define FW_SLOT_REVERB      0x20002814u
#define FW_SLOT_CLOCK       0x20001E94u
#define FW_TRACK_MAIN       0x3E4u
#define FW_TRACK_STRIP(voice) ((uint8_t *)(voice) + FW_TRACK_MAIN)     /* a track voice's main strip (it contains it) */
/* The track voices themselves (8, 0x674 apart, in the engine object) and their send strips. Each strip (main and
 * sends alike) is a gain node: +0x38 the target gain, +0x3C the current one (+0x54 picks which word, 0 here),
 * +0x55 ramping, +0x56 ramp on change, and the ramp's start, step and phase at +0x58, +0x5C, +0x60. The firmware
 * sets them when a note starts, from the instrument's DRY / MFX / DELAY / REVERB: an exponential curve, x1.556
 * every 0x10 (0.24 dB a step), 0x80 = 0.05797 for a send (at most 0.97705), the main strip x0.8696 of that.
 * fw_gain_set does what the firmware's setter does. Measured on 6.6.4A, examples/lfo-sends. */
/* track 1's voice is at +0x5C0 and is 0x594 long; tracks 2..8 follow from +0xB54, 0x674 apart (each read back by its
 * +0x3D track byte) */
#define FW_TRACK_VOICE(t)   ((t) ? fw_audio_engine + 0xB54u + 0x674u * ((t) - 1) : fw_audio_engine + 0x5C0u)
#define FW_VOICE_TRACK      0x3Du                       /* u8: the track (0..7) */
#define FW_VOICE_ENGINE     0x38u                       /* the sound engine's voice the track plays (+4: its modulators) */
#define FW_TRACK_REVERB     0x450u
#define FW_TRACK_DELAY      0x4BCu
#define FW_TRACK_MFX        0x528u
/* track t's gain node for its DRY (main strip) or a send; 0 when the voice there isn't track t's */
enum { FW_GAIN_DRY, FW_GAIN_MFX, FW_GAIN_DELAY, FW_GAIN_REVERB };
static inline uint8_t *fw_track_gain(int t, int which)
{
    static const uint16_t off[4] = { FW_TRACK_MAIN, FW_TRACK_MFX, FW_TRACK_DELAY, FW_TRACK_REVERB };
    uint8_t *voice = FW_TRACK_VOICE(t);
    return voice[FW_VOICE_TRACK] == (uint8_t)t ? voice + off[which & 3] : 0;
}
static inline void fw_gain_set(uint8_t *node, float g)
{
    *(volatile float *)(node + 0x38) = g;
    float *cur = (float *)(node + 0x3C + 4 * node[0x54]);
    if (node[0x56]) {
        *(float *)(node + 0x58) = *cur;
        *(float *)(node + 0x5C) = g - *cur;
        *(float *)(node + 0x60) = 0.0f;
        node[0x55] = 1;
    } else {
        node[0x55] = 0;
        *(float *)(node + 0x60) = 1.0f;
        *cur = g;
    }
}
/* Modulators: each track has 4 (one per instrument MOD slot), 0xA8 apart, in groups 0x2B0 apart from
 * fw_modulators (literal in the firmware). +0xA0 points at the first of the track's group. Methods (vtable at +0):
 * +0x04 output() and +0x08 amount() (floats; the stock apply adds output x amount x 16 to a parameter whose full
 * range is 16), +0x1C dest(). */
#define fw_modulators       ((uint8_t *)0x200159E0u)
#define FW_MODULATOR_SIZE   0xA8u
#define FW_MODULATOR_TRACK  0x2B0u
#define FW_MODULATOR_FIRST  0xA0u
#define FW_MODULATOR_INST   0x2ACu                      /* in a group: the instrument's modulator bytes it was set up from */
/* a group's instrument modulator bytes (FW_INSTRUMENT(i) + FW_INST_MODS), from its first modulator; 0 if unknown */
#define FW_MODULATOR_INST_MODS(first) (*(const uint8_t *const *)((const uint8_t *)(first) + FW_MODULATOR_INST))
typedef float (*fw_mod_float_fn)(void *mod);
#define FW_MOD_OUTPUT(m)    ((*(fw_mod_float_fn const *const *)(m))[1](m))
#define FW_MOD_AMOUNT(m)    ((*(fw_mod_float_fn const *const *)(m))[2](m))
/* Instruments: byte 0 the type (FW_INST_*, 0xFF none); the 4 modulators' bytes at FW_INST_MODS + 6 x k, the first
 * of each type << 4 | dest (AHD, ADSR, DRUM, LFO, TRIG, TRACKING). */
enum { FW_INST_WAV, FW_INST_MACRO, FW_INST_SAMPLER, FW_INST_MIDI_OUT, FW_INST_FM, FW_INST_HYPER, FW_INST_EXTERNAL };
#define FW_INST_MODS        0x3Fu
#define FW_INST_SIZE        0xD7u
/* The phrase view (object 0x2001AD90, phrase number at +4): its vtable is in RAM. +0x34 redraws after a bulk edit
 * (cut / clear, paste, interpolate, rotate, the FILL generators, transposing a selection), +0x38 after a cell. */
#define fw_phrase_view      ((uint8_t *)0x2001AD90u)
#define FW_SLOT_PHRASE_BULK 0x2000173Cu
#define FW_SLOT_PHRASE_CELL 0x20001740u
enum { FW_FX_MFX, FW_FX_DELAY, FW_FX_REVERB };
typedef void (*fw_audio_transmit_fn)(void *obj, void *block, int port);
typedef void (*fw_audio_release_fn)(void *block);
#define fw_audio_transmit   ((fw_audio_transmit_fn)0x0001ADD5u)  /* AudioStream::transmit (ITCM) */
#define fw_audio_release    ((fw_audio_release_fn)0x0001AD69u)   /* AudioStream::release (ITCM) */
#define FW_AUDIO_FRAMES     64
#define FW_AUDIO_RATE       44100
typedef void *(*fw_audio_alloc_fn)(void);
#define fw_audio_alloc      ((fw_audio_alloc_fn)0x0001AB5Du)        /* AudioStream::allocate (ITCM): ref count 1 */
#define fw_mute_mask        (*(volatile uint8_t *)0x2000C410u)  /* a bit per track */
#define fw_solo_mask        (*(volatile uint8_t *)0x2000C414u)
#define fw_seq_engine       ((uint8_t *)0x2001ADDCu)              /* ev_seq_tick's argument */
#define fw_sequencer        ((uint8_t *)0x2000BE80u)              /* +FW_SEQ_PLAYING: playing */
#define FW_SEQ_PLAYING      0x3B8u
#define FW_PLAYER(t)        ((uint8_t *)0x2001ADF0u + 0x248 * (t))   /* a track's player: +0xC track, +0x4C the row */
#define FW_PLAYER_INST      0x178u                      /* the player's instrument: its FW_INSTRUMENT() data */
enum { FW_ENGINE_FM, FW_ENGINE_HYPER, FW_ENGINE_MACRO, FW_ENGINE_SAMPLER, FW_ENGINE_WAV, FW_ENGINE_EXTERNAL,
       FW_ENGINE_MIDI_OUT, FW_ENGINES };
/* Each engine's class vtable is in RAM (DTCM .data): +0xF8 name(eng, dest) and +0x104 count(eng) list its
 * modulation destinations (0 = OFF). A modulator keeps dest in the low nibble of its first byte (instrument +0x3F
 * + 6 x mod), so an engine has at most 16. Stock counts: 15, SAMPLER and EXTERNAL 14. Order: FW_ENGINE_*. */
#define FW_ENGINE_VTABLES   { 0x20001810u, 0x20001EE0u, 0x200020A8u, 0x20002664u, 0x20001CACu, 0x2000288Cu, 0x20001A50u }
#define FW_VT_DEST_NAME     0xF8u
#define FW_VT_DEST_COUNT    0x104u
#define FW_MOD_DESTS_MAX    16

/* core 0.4's API for mods (dl/core.h): a pointer to it sits after core's hook table (bindings: loader.ram +
 * 0x208). dl_core() checks it. */
#define DL_CORE_PTR         0x00029D48u

/* ---- USB serial (Teensyduino usb_serial.c): what m8c talks to ------------------------------------------------
 * The m8c command parser (fw_m8c_parse, 0x6007846C) drains every waiting byte; core's ev_serial handler runs at
 * its entry and peeks the receive queue first. Received data waits in RX_NUM (8) 512-byte buffers queued in
 * rx_list (a ring of 9, head and tail are bytes); rx_index is how far each buffer has been read. Mask the USB
 * interrupt (IRQ 113) while looking, as usb_serial_read does. */
#define fw_rx_available     (*(volatile uint32_t *)0x2003382Cu)
#define fw_rx_head          (*(volatile uint8_t *)0x20041590u)
#define fw_rx_tail          (*(volatile uint8_t *)0x20041592u)
#define fw_rx_list          ((volatile uint8_t *)0x20033870u)
#define fw_rx_index         ((volatile uint16_t *)0x20033858u)
#define fw_rx_buffer        ((volatile uint8_t *)0x2027C4E0u)
#define FW_RX_RING          9
#define FW_RX_BUF           512
#define FW_USB_IRQ_BIT      (1u << (113 - 96))
#define FW_NVIC_ISER3       (*(volatile uint32_t *)0xE000E10Cu)
#define FW_NVIC_ICER3       (*(volatile uint32_t *)0xE000E18Cu)
typedef int (*fw_serial_read_fn)(void *buf, uint32_t n);      /* usb_serial_read: no yield, returns bytes read */
typedef int (*fw_serial_putc_fn)(int c);                       /* usb_serial_putchar: dropped if USB is not up */
#define fw_serial_read      ((fw_serial_read_fn)0x600A3F9Du)
#define fw_serial_putc      ((fw_serial_putc_fn)0x600A4169u)

/* ---- the UI -----------------------------------------------------------------------------------------------
 * Screens are objects whose first word is an 8-slot method table: enter(view, arg), +04 (shared), input(view,
 * action), update(view) each loop, draw(view) each frame, +14, and two flags (+18, +1C). set_view(ui, id) leaves
 * the old screen, fetches fw_views[id] (30 slots, 7 is empty in this build) and enters it. The current id is at
 * ui + 0x15. Input actions are the m8c key bits of the chord: EDIT 01, OPT 02, RIGHT 04, PLAY 08, SHIFT 10,
 * DOWN 20, UP 40, LEFT 80. Text goes into a 40 x 24 character grid (fw_grid + 0x10 + row * 40 + col) that the
 * display task draws and sends to m8c. */
#define fw_ui               ((uint8_t *)0x2001C1A4u)
#define FW_UI_VIEW          0x15
#define fw_views            ((void *volatile *)0x20000B24u)
#define FW_VIEWS            30
#define FW_VIEW_FREE        7                           /* the empty slot core's MODS page takes */
#define FW_HAS_VIEW_TABLE   1                           /* set_view reads fw_views (Model:02: a switch) */
#define FW_VIEW_SETTINGS    0x1C
#define fw_settings         ((volatile uint8_t *)0x2001CCECu)   /* SYSTEM SETTINGS: +4 cursor x, +5 cursor y */
#define fw_grid             ((uint8_t *)0x20019160u)
#define FW_GRID_COLS        40
#define FW_GRID_ROWS        24
typedef void (*fw_set_view_fn)(void *ui, int view);
typedef void (*fw_text_fn)(void *grid, int col, int row, const char *s);
#define fw_set_view         ((fw_set_view_fn)0x6004A96Du)
#define fw_text             ((fw_text_fn)0x60077543u)
#define FW_VIEW_SHARED_04   0x60099B25u                 /* the +04 method most screens share */
#define FW_VIEW_NOP         0x60099B19u                 /* an empty method */
#define FW_VIEW_FLAG_18     0x60099B1Du                 /* the +18 / +1C flags SETTINGS uses: return 0 */
#define FW_VIEW_FLAG_1C     0x60099B21u
enum { FW_KEY_EDIT = 0x01, FW_KEY_OPT = 0x02, FW_KEY_RIGHT = 0x04, FW_KEY_PLAY = 0x08, FW_KEY_SHIFT = 0x10,
       FW_KEY_DOWN = 0x20, FW_KEY_UP = 0x40, FW_KEY_LEFT = 0x80 };

/* The theme (SYSTEM SETTINGS > THEME). The system settings are a 0xCC-byte struct the firmware keeps in EEPROM
 * (+0xC8 a checksum the save works out; the save writes only the bytes that changed). +0x24: the 13 colours, R G B
 * each, in the .m8t file's order (BACKGROUND, TEXT:EMPTY/INFO/DEFAULT/VALUE/TITLES, PLAY MARKERS, CURSOR, SELECTION,
 * SCOPE/SLIDER, METER LOW/MID/PEAK); +0x4B: the theme's name, 13 bytes, 0-padded (loading a .m8t sets it).
 * The screen draws from an RGB565 palette set an entry at a time (set_pal ignores its first argument); the redraw
 * with 1 repaints every view in it. That is what loading a .m8t does (0x60075CF0). */
#define fw_sys              ((uint8_t *)0x2001C70Cu)
#define FW_SYS_THEME        0x24u
#define FW_SYS_THEME_NAME   0x4Bu
typedef void (*fw_sys_save_fn)(void *sys);
typedef void (*fw_set_pal_fn)(void *unused, int index, int r, int g, int b);
typedef void (*fw_redraw_fn)(void *obj, int full);
#define fw_sys_save         ((fw_sys_save_fn)0x6009C987u)
#define fw_set_pal          ((fw_set_pal_fn)0x6009AF29u)
#define fw_redraw           ((fw_redraw_fn)0x600496B9u)
#define FW_REDRAW_OBJ       ((void *)0x2001A4F4u)

/* The extended theme (core 0.7). Every text cell has an attribute byte (grid + 0x3D1 + row * 40 + col, beside its
 * character at grid + 0x10) that the draw loop (ITCM 0x1902A) turns into a palette index: '.' '/' '0'..'7' are 0..9,
 * '8'..'C' are 1..12, '5' and '6' swap fg and bg (the cursor and selection blocks), 0xAE is skipped, and 'D'..'R' are
 * 13..27, past the firmware's 13 entries: no screen uses them. The loop loads the palette's address from a literal
 * in ITCM (FW_ATTR_PAL_LIT); core points it at a 28-entry table of its own. The frame refresh draws only once
 * FW_FRAME_MS have passed since fw_frame_last. */
#define FW_PALETTE          ((volatile const uint32_t *)0x2000B590u)
#define FW_ATTR_PAL_LIT     ((volatile uint32_t *)0x000190A0u)
#define FW_GRID_CHARS       0x10u
#define FW_GRID_ATTR        0x3D1u
#define FW_FRAME_MS         32u
#define fw_frame_last       (*(volatile uint32_t *)0x200206BCu)   /* the frame refresh's last time (fw_millis) */
/* Teensyduino's crash record (CrashReport): written by the fault handler, kept across the reboot */
#define fw_fault_info       ((const volatile uint32_t *)0x2027FF80u)

#endif
