/* SPDX-License-Identifier: GPL-2.0-or-later */
/* M8 Headless 6.6.4A: the firmware locations core 0.3 and loadable mods use.
 * docs/FIRMWARE-MAP.md and dirtyloader/core/bindings/m8_6.6.4A_headless.json record how each was found. */
#ifndef DIRTYLOADER_M8_HEADLESS_FW_H
#define DIRTYLOADER_M8_HEADLESS_FW_H

#include <stdint.h>

#undef DL_FW                                    /* dl/mod.h's default is 0, "any firmware" */
#define DL_FW 0x00060604u                       /* 6.6.4A headless */

#define fw_millis   (*(volatile uint32_t *)0x20040264u)

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
#define FW_MIDI_READ_CALL   0x600A376Au     /* usb_midi_read's bl usb_midi_read_message: core's ev_midi site */

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

/* Teensyduino's crash record (CrashReport): written by the fault handler, kept across the reboot */
#define fw_fault_info       ((const volatile uint32_t *)0x2027FF80u)

#endif
