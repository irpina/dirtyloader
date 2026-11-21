/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DIRTYLOADER_M8_MODEL01_664_FW_H
#define DIRTYLOADER_M8_MODEL01_664_FW_H

#include <stddef.h>
#include <stdint.h>

#undef DL_FW
#define DL_FW 0x01060604u
#define DL_CORE_PTR 0x0002B4A8u

/* SdFat FsBaseFile in stock Model:01 6.6.4A. The open routine uses the
 * last two words to identify the active volume type. */
struct fw_file {
    uint32_t storage[14];
    void *fat;
    void *exfat;
};

_Static_assert(offsetof(struct fw_file, fat) == 0x38, "incorrect FatFile offset");
_Static_assert(offsetof(struct fw_file, exfat) == 0x3C, "incorrect ExFatFile offset");
_Static_assert(sizeof(struct fw_file) == 0x40, "incorrect FsBaseFile size");

#define fw_sd               ((void *)0x2003745Cu)
#define fw_storage          ((void *)0x2001C08Cu)
#define FW_SD_MOUNTED()     (((volatile uint8_t *)fw_storage)[4])
#define FW_O_READ           0x000
#define FW_O_RDWR           0x002
#define FW_O_CREAT          0x200
#define FW_O_TRUNC          0x400

typedef int (*fw_open_fn)(struct fw_file *f, void *vol, const char *path, int mode);
typedef int (*fw_close_fn)(struct fw_file *f);
typedef int (*fw_io_fn)(void *file, void *buf, uint32_t size);

#define fw_file_open        ((fw_open_fn)0x600AE1FDu)
#define fw_file_close       ((fw_close_fn)0x600AE1D5u)
#define fw_fat_read         ((fw_io_fn)0x600AC965u)
#define fw_exfat_read       ((fw_io_fn)0x600AAF69u)
#define fw_fat_write        ((fw_io_fn)0x600ACF99u)
#define fw_exfat_write      ((fw_io_fn)0x600ABA3Du)

/* SysTick, USB receive, and the fault record for the boot guard. */
#define fw_millis            (*(volatile uint32_t *)0x2003FF88u)
#define fw_usb_configuration (*(volatile uint8_t *)0x200412EDu)
#define fw_rx_available      (*(volatile uint32_t *)0x20033584u)
typedef int (*fw_serial_read_fn)(void *buf, uint32_t count);
#define fw_serial_read       ((fw_serial_read_fn)0x600B1F41u)
#define fw_fault_info        ((const volatile uint32_t *)0x2027FF80u)

/* Touch state after the stock poll. */
#define fw_touch      ((uint8_t *)0x2001C5E0u)
#define FW_TOUCH_X    0x40u
#define FW_TOUCH_Y    0x44u
#define FW_TOUCH_DOWN 0x58u

/* Master soft clip, before the USB and I2S branches. */
#define FW_AUDIO_TAP_OBJ ((uint8_t *)0x20014C58u)
#define FW_AUDIO_RATE 44100
typedef void *(*fw_audio_alloc_fn)(void);
#define fw_audio_alloc ((fw_audio_alloc_fn)0x0001B201u)

/* Track voice update slot and embedded main strip. The allocator uses 32 float samples per block. */
#define FW_SLOT_TRACK        0x20002504u
#define FW_AUDIO_FRAMES      32
#define FW_TRACK_STRIP(voice) ((uint8_t *)(voice) + 0x2E4u)

/* The 40 x 24 character grid and view table in Model:01 6.6.4A. */
#define FW_GRID_COLS 40
#define FW_GRID_ROWS 24
#define FW_GRID_ATTR 0x3D1u
#define FW_VIEW_FREE 7
#define FW_UI_VIEW 0x15
#define fw_grid ((uint8_t *)0x200188F0u)
#define fw_ui   ((uint8_t *)0x2001B934u)
#define fw_views ((void *volatile *)0x20000BD8u)
typedef void (*fw_text_fn)(void *grid, int col, int row, const char *text);
typedef void (*fw_set_view_fn)(void *ui, int view);
#define fw_text     ((fw_text_fn)0x6007B053u)
#define fw_set_view ((fw_set_view_fn)0x6004E1A5u)
/* Stock overlay reset used during set_view, and the frame's overlay draw. */
#define fw_clear_cursors ((void (*)(void *))0x6004A05Bu)
#define fw_draw_cursors  ((void (*)(void *))0x6004A0B1u)
#define fw_draw_selection ((void (*)(void *))0x600494BDu)
#define fw_background ((uint16_t (*)(void *))0x6007AD29u)
#define fw_clear_display ((void (*)(void *, uint16_t))0x6007B255u)
#define FW_VIEW_SHARED_04 0x600A4B65u
#define FW_VIEW_NOP 0x600A4B59u

typedef int (*fw_open_next_fn)(struct fw_file *f, struct fw_file *dir, int mode);
typedef int (*fw_name_fn)(void *file, char *name, uint32_t size);
#define fw_file_open_next ((fw_open_next_fn)0x600AE335u)
#define fw_fat_name       ((fw_name_fn)0x600ADB95u)
#define fw_exfat_name     ((fw_name_fn)0x600ABD09u)

#endif
