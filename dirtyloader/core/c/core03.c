/* SPDX-License-Identifier: GPL-2.0-or-later */
/* core 0.4: load mods from the SD card at boot, and serve them (docs/LOADER.md).
 *
 * Runs from flash past the end of the stock image and keeps all of its state in the free ITCM tail, so it has
 * no .data or .bss of its own. Three entry points, all called from stubs the builder places:
 *
 *   core_early()  first thing in main(), before setup(): make ITCM writable, retire the last boot's table
 *   core_load()   inside setup(), just after the card is mounted and before the firmware touches it (no
 *                 autosave yet, no samples, no audio): crash guard, load the mods in active.txt, status.txt
 *   core_boot()   after setup(), before ev_boot: switch the dispatcher to the table in ITCM
 *
 * Every SD access is in core_load, before the firmware itself uses the card, so core never has a file open
 * while the firmware does. The crash guard needs no file write later on either: Teensy's crash record and
 * this RAM survive the reboot after a crash, so core_load can tell that the last boot with mods crashed.
 *
 * Built for one firmware: CORE_FW_H names its header (m8-headless/fw.h). */
#include <stdint.h>
#include "dl/mod.h"
#include CORE_FW_H
#include "dl/core.h"

/* ---- layout, shared with dirtyloader/core/builder.py (build_core03_mod) -------------------------------- */
#ifndef CORE_RAM
#error "CORE_RAM, CORE_RAM_END, CORE_FLASH_TABLE, CORE_FLASH_SLOTS come from the builder"
#endif
#define RAM_MAGIC    0x33524C44u       /* "DLR3": the dispatcher uses ram->table only when this is set */
#define RAM_SIG      0x47495344u       /* "DSIG": ram->nmods is from a previous boot of this core */
#define SLOTS        64
#define MAX_MODS     16
#define NAME_MAX     28                /* an .m8x file name the MODS page and the boot record keep */
#define FLAG_ENABLED 1u
#define MAX_PAGES    8
#define MAX_DATA     8
#define MIDI_Q       8
#define MAX_SETTINGS 8

struct hook { uint16_t event, flags; void *fn; };

struct core_ram {
    uint32_t magic;
    uint32_t count;
    struct hook table[SLOTS];
    const struct dl_core *api;   /* +0x208, DL_CORE_PTR: mods find core's API here */
    uint32_t sig;                /* RAM_SIG once core_load has run; ITCM survives a reset, not a power cycle */
    uint32_t loaded;             /* core_load ran this boot */
    uint32_t next;               /* next free byte of the mods' area */
    uint32_t nmods;
    const struct dl_mod *mods[MAX_MODS];
    /* what core_load did with each line of active.txt, for the MODS page */
    uint32_t nboot;
    struct { char name[NAME_MAX]; int32_t err; } boot[MAX_MODS];
    /* the MODS page (TELOS): a screen in the firmware's free view slot */
    struct { const void *const *vt; uint8_t body[0x3C]; } page_view;
    uint32_t page_n, page_sel, page_dirty, last_action;
    struct { char name[NAME_MAX]; uint8_t on, check; } page[MAX_MODS];   /* check: E<n> found when switching on */
    /* songs and their mods: core_tick writes / checks <song>.mods after the firmware's own save / load */
    uint32_t booted, song_pending, page_mode, prev_view, nwant, song_result, song_at, song_tries;
    uint32_t audio_orig;           /* the audio interrupt core_audio wraps */
    uint32_t skipped;              /* the crash guard skipped the mods this boot */
    char song[128];
    struct { char name[NAME_MAX]; } want[MAX_MODS];
    /* core 0.4: mods' pages and song data, MIDI played in by mods, the hang guard, the crash the boot found */
    const struct dl_page *pages[MAX_PAGES];
    uint32_t npages;
    const struct dl_page *cur_page;
    uint32_t page_back;            /* the view a mod page was opened over; PAGE_BACK_MODS: the MODS page */
    const struct dl_song_data *data[MAX_DATA];
    uint32_t ndata, data_done;
    uint32_t midi_q[MIDI_Q];
    uint32_t midi_head, midi_tail;
    uint32_t armed, armed_at;      /* the guard says ARMD until the boot has run ARMED_MS */
    uint32_t crash[8];             /* Teensyduino's crash record as the boot found it; [0] 0: none */
    uint32_t fault_orig, in_fault, fault_handled, fault_pc;   /* ev_crash; the last two survive the reset */
    uint32_t dest_name_orig[FW_ENGINES], dest_count_orig[FW_ENGINES], dest_stock[FW_ENGINES], dest_n[FW_ENGINES];
    const char *dest_extra[FW_ENGINES][FW_MOD_DESTS_MAX];
    uint32_t tap_orig, audio_subs;
    uint32_t track_orig, mfx_orig, delay_orig, reverb_orig, clock_orig, track_subs, fx_subs, params_subs;   /* the tap's update() core_tap wraps; ev_audio_out has handlers */
    uint32_t sysex_orig;           /* the firmware's SysEx handler core_sysex hands chunks on to */
    const struct dl_setting *settings[MAX_SETTINGS];
    uint32_t nsettings, menu_sel, menu_back;
    uint32_t bulk_orig, cell_orig, snap_phrase;   /* ev_step_edit's bulk reports: the phrase as last seen */
    uint8_t snap[16 * 9];
    uint32_t usb_last;             /* usb_configuration as ev_usb last reported it; 0xFF before the first */
};
_Static_assert(__builtin_offsetof(struct core_ram, api) == 0x208, "dl/core.h: DL_CORE_PTR is the RAM + 0x208");
#ifdef DL_CORE_PTR
_Static_assert(DL_CORE_PTR == CORE_RAM + 0x208, "the device header's DL_CORE_PTR is not this core's");
#endif
#define PAGE_BACK_MODS 0xFFu
#define PAGE_BACK_MENU 0xFEu
#define ram ((struct core_ram *)CORE_RAM)
#define AREA_START ((CORE_RAM + sizeof(struct core_ram) + 7u) & ~7u)
/* boot-time scratch for status.txt and active.txt at the top of ITCM, off the main stack */
#define STATUS_SIZE 1024u
#define LIST_SIZE 512u
#define SCRATCH (CORE_RAM_END - STATUS_SIZE - LIST_SIZE)
#define AREA_END SCRATCH

/* ---- small libc ------------------------------------------------------------------------------------------ */
static int seq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static void zero(void *p, uint32_t n) { uint8_t *b = p; while (n--) *b++ = 0; }
static char *put(char *o, const char *s) { while (*s) *o++ = *s++; return o; }
static char *put_hex(char *o, uint32_t v)
{
    o = put(o, "0x");
    for (int i = 28; i >= 0; i -= 4) *o++ = "0123456789ABCDEF"[(v >> i) & 15];
    return o;
}
static char *put_dec(char *o, uint32_t v)
{
    char t[10]; int n = 0;
    do { t[n++] = '0' + v % 10; v /= 10; } while (v);
    while (n) *o++ = t[--n];
    return o;
}

static uint32_t crc32(uint32_t c, const uint8_t *p, uint32_t n)
{
    c = ~c;
    while (n--) {
        c ^= *p++;
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & -(c & 1));
    }
    return ~c;
}

/* ---- files (core_load only) -------------------------------------------------------------------------------- */
static int f_open(struct fw_file *f, const char *path, int oflag)
{
    zero(f, sizeof *f);
    if (!FW_SD_MOUNTED()) return 0;                 /* SdFat stalls on an unmounted volume */
    return fw_file_open(f, fw_sd, path, oflag);
}
static int f_read(struct fw_file *f, void *buf, uint32_t n)
{
    if (f->fat) return fw_fat_read(f->fat, buf, n);
    if (f->exfat) return fw_exfat_read(f->exfat, buf, n);
    return -1;
}
static int f_write(struct fw_file *f, const void *buf, uint32_t n)
{
    if (f->fat) return fw_fat_write(f->fat, (void *)buf, n);
    if (f->exfat) return fw_exfat_write(f->exfat, (void *)buf, n);
    return -1;
}
static int read_exact(struct fw_file *f, void *buf, uint32_t n) { return f_read(f, buf, n) == (int)n; }
static int f_seek(struct fw_file *f, uint32_t pos)
{
    if (f->fat) return fw_fat_seek(f->fat, pos);
    if (f->exfat) return fw_exfat_seek(f->exfat, 0, pos);
    return 0;
}
static int f_remove(const char *path)
{
    struct fw_file f;
    if (!f_open(&f, path, FW_O_RDWR)) return 0;
    int ok = f.fat ? fw_fat_remove(f.fat) : f.exfat ? fw_exfat_remove(f.exfat) : 0;
    fw_file_close(&f);
    return ok;
}

static int write_file(const char *path, const char *text, uint32_t n)
{
    struct fw_file f;
    if (!f_open(&f, path, FW_O_RDWR | FW_O_CREAT | FW_O_TRUNC)) return 0;
    int ok = f_write(&f, text, n) == (int)n;
    fw_file_close(&f);
    return ok;
}

static void restart_now(void)
{
    *(volatile uint32_t *)0xE000ED0Cu = 0x05FA0004u;  /* SCB_AIRCR: SYSRESETREQ */
    for (;;) { }
}

/* ---- the crash guard ------------------------------------------------------------------------------------------
 * /dirtyloader/guard holds SKIP once a boot with mods crashed; while it does, nothing is loaded. Anything else
 * (or no file) means load. Writing GOOD there (dirtyloader sd does) re-enables the mods. */
#define GUARD_PATH "/dirtyloader/guard"
#define G_SKIP 0x50494B53u   /* "SKIP" */
#define G_ARMD 0x444D5241u   /* "ARMD": a boot with mods has not run ARMED_MS yet (core_tick writes GOOD after) */
#define ARMED_MS 10000u
enum { SKIP_NONE, SKIP_CRASH, SKIP_GUARD, SKIP_HANG, SKIP_HOST };
static uint32_t read_guard(void)
{
    struct fw_file f;
    uint32_t w = 0;
    if (f_open(&f, GUARD_PATH, FW_O_READ)) {
        if (!read_exact(&f, &w, 4)) w = 0;
        fw_file_close(&f);
    }
    return w;
}

/* Teensyduino's fault handler leaves a record in RAM (len, ipsr, cfsr, hfsr, mmfar, bfar, pc, xpsr, ...) and reboots. */
static int crashed(void)     /* len is 11 (words) in this build, 44 (bytes) in some Teensyduino versions */
{
    return (fw_fault_info[0] == 11u || fw_fault_info[0] == 44u) && (fw_fault_info[2] | fw_fault_info[3]);
}
static void forget_crash(void) { ((volatile uint32_t *)fw_fault_info)[0] = 0; }

/* ---- loading ----------------------------------------------------------------------------------------------- */
/* .m8x header (docs/LOADER.md) */
struct m8x {
    uint32_t magic;              /* "DLX1" */
    uint32_t image, bss, nrel;   /* bytes, bytes, relocation count */
    uint32_t crc;                /* crc32 of image then relocations */
};
#define M8X_MAGIC 0x31584C44u

enum { E_OPEN = 1, E_HEADER, E_SPACE, E_READ, E_CRC, E_MOD, E_FIRMWARE, E_DUPLICATE, E_TABLE, E_COUNT };
static const char *const ERRORS[] = {
    "", "cannot open", "not an .m8x", "no room", "read failed", "checksum", "not a dl_mod",
    "built for other firmware", "id already loaded", "hook table full", "too many mods",
};

static int add_hook(uint16_t event, uint16_t order, void *fn, uint16_t *orders)
{
    if (ram->count >= SLOTS) return 0;
    uint32_t i = ram->count;
    while (i && orders[i - 1] > order) {           /* stable: after hooks of the same order */
        ram->table[i] = ram->table[i - 1];
        orders[i] = orders[i - 1];
        i--;
    }
    ram->table[i].event = event;
    ram->table[i].flags = FLAG_ENABLED;
    ram->table[i].fn = fn;
    orders[i] = order;
    ram->count++;
    return 1;
}

static void flash_hooks(uint16_t *orders)
{
    const struct hook *flash = (const struct hook *)CORE_FLASH_TABLE;
    ram->count = 0;
    for (uint32_t i = 0; i < CORE_FLASH_SLOTS; i++)       /* the flash-linked hooks keep their order */
        if (flash[i].fn && (flash[i].flags & FLAG_ENABLED))
            add_hook(flash[i].event, 0, flash[i].fn, orders);
}

static int load_one(const char *name, uint16_t *orders, const struct dl_mod **out)
{
    char path[96];
    char *o = put(path, "/dirtyloader/mods/");
    for (uint32_t i = 0; name[i] && o < path + sizeof path - 1; i++) *o++ = name[i];
    *o = 0;

    struct fw_file f;
    struct m8x h;
    if (!f_open(&f, path, FW_O_READ)) return E_OPEN;
    int err = 0;
    uint32_t base = ram->next;
    if (!read_exact(&f, &h, sizeof h) || h.magic != M8X_MAGIC || h.image < sizeof(struct dl_mod)
        || h.image > AREA_END || h.nrel > AREA_END / 4 || h.bss > AREA_END) {
        err = E_HEADER;
        goto done;
    }
    uint32_t tail = h.nrel * 4 > h.bss ? h.nrel * 4 : h.bss;
    if (base + h.image + tail > AREA_END) { err = E_SPACE; goto done; }
    uint8_t *img = (uint8_t *)base;
    uint32_t *rel = (uint32_t *)(base + h.image);   /* relocations sit where .bss will be */
    if (!read_exact(&f, img, h.image) || !read_exact(&f, rel, h.nrel * 4)) { err = E_READ; goto done; }
    if (crc32(crc32(0, img, h.image), (uint8_t *)rel, h.nrel * 4) != h.crc) { err = E_CRC; goto done; }
    for (uint32_t i = 0; i < h.nrel; i++)
        if (rel[i] > h.image - 4 || (rel[i] & 3)) { err = E_HEADER; goto done; }
    for (uint32_t i = 0; i < h.nrel; i++)
        *(uint32_t *)(img + rel[i]) += base;
    zero(rel, tail);

    const struct dl_mod *m = (const struct dl_mod *)img;
    if (m->magic != DL_MOD_MAGIC || m->abi != DL_ABI) { err = E_MOD; goto done; }
    if (m->fw && m->fw != DL_FW) { err = E_FIRMWARE; goto done; }
    for (uint32_t i = 0; i < ram->nmods; i++)
        if (seq(ram->mods[i]->id, m->id)) { err = E_DUPLICATE; goto done; }
    if (ram->nmods >= MAX_MODS) { err = E_COUNT; goto done; }
    if (ram->count + m->nsubs > SLOTS) { err = E_TABLE; goto done; }
    for (uint32_t i = 0; i < m->nsubs; i++)
        add_hook(m->subs[i].event, m->subs[i].order, m->subs[i].fn, orders);
    ram->mods[ram->nmods++] = m;
    ram->next = (base + h.image + tail + 7u) & ~7u;
    *out = m;
done:
    fw_file_close(&f);
    return err;
}



/* ---- entry points ------------------------------------------------------------------------------------------ */
/* ---- mods over USB (docs/LOADER.md, "Transfer") ------------------------------------------------------------
 * Requests travel in the m8c serial stream: 0xD1, cmd, seq, len (u16 LE), payload[len], sum8 (cmd..payload).
 * m8c's own commands are ASCII, so 0xD1 never starts one. core_serial, subscribed to ev_serial at order 0,
 * sees each request before the m8c parser can drain it. Replies are SLIP frames like the display stream's:
 * 0xF1, cmd, seq, status, data. Files live under /dirtyloader; nothing here loads a mod: the next boot does. */
#define PKT_MARK  0xD1
#define PKT_REPLY 0xF1
#define PKT_MAX   1100u                             /* payload bytes; the request lands in SCRATCH */
enum { C_INFO = 1, C_LIST, C_PUT, C_CHECK, C_GET, C_MKDIRS, C_RESTART, C_PEEK, C_DELETE, C_POKE };
enum { S_OK = 0, S_BAD, S_SUM, S_PATH, S_IO, S_NOCARD, S_TIMEOUT, S_CMD };

static int rx_peek(void)
{
    int c = -1;
    FW_NVIC_ICER3 = FW_USB_IRQ_BIT;
    uint8_t t = fw_rx_tail;
    if (fw_rx_head != t) {
        if (++t >= FW_RX_RING) t = 0;
        uint8_t i = fw_rx_list[t];
        c = fw_rx_buffer[i * FW_RX_BUF + fw_rx_index[i]];
    }
    FW_NVIC_ISER3 = FW_USB_IRQ_BIT;
    return c;
}

static int rx_exact(uint8_t *p, uint32_t n, uint32_t ms)
{
    uint32_t t0 = fw_millis;
    while (n) {
        uint32_t k = fw_rx_available;
        if (k) {
            if (k > n) k = n;
            int got = fw_serial_read(p, k);
            if (got > 0) { p += got; n -= (uint32_t)got; t0 = fw_millis; }
        } else if (fw_millis - t0 > ms) {
            return 0;
        }
    }
    return 1;
}

static void tx(uint8_t c)
{
    if (c == 0xC0) { fw_serial_putc(0xDB); fw_serial_putc(0xDC); }
    else if (c == 0xDB) { fw_serial_putc(0xDB); fw_serial_putc(0xDD); }
    else fw_serial_putc(c);
}
static void reply(uint8_t cmd, uint8_t seq, uint8_t status, const void *data, uint32_t n)
{
    const uint8_t *d = data;
    tx(PKT_REPLY); tx(cmd); tx(seq); tx(status);
    while (n--) tx(*d++);
    fw_serial_putc(0xC0);
}

static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static void put32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

/* "/dirtyloader/" + a relative name of [A-Za-z0-9._-/], no "..", under 64 bytes */
/* "/dirtyloader/" + a relative name; with `anywhere` (reads only) an absolute path is taken as it is */
static int dl_path_in(char *out, const uint8_t *name, uint32_t n, int anywhere)
{
    if (!n || n > 63 || (name[0] == '/' && !anywhere)) return 0;
    char *o = name[0] == '/' ? out : put(out, "/dirtyloader/");
    for (uint32_t i = 0; i < n; i++) {
        uint8_t c = name[i];
        int ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '_'
                 || c == '-' || c == '/';
        if (!ok || (c == '.' && i + 1 < n && name[i + 1] == '.')) return 0;
        *o++ = (char)c;
    }
    *o = 0;
    return 1;
}
static int dl_path(char *out, const uint8_t *name, uint32_t n) { return dl_path_in(out, name, n, 0); }
static int rd_path(char *out, const uint8_t *name, uint32_t n) { return dl_path_in(out, name, n, 1); }
#ifdef PUT_ANYWHERE
#define PUT_PATH rd_path
#else
#define PUT_PATH dl_path
#endif


static int mkdirs(const char *path)
{
    uint32_t t[0x40 / 4];
    zero(t, sizeof t);
    if (fw_fat_vol) {
        if (fw_fat_mkdir(t, (uint8_t *)fw_fat_vol + FW_VOL_CWD, path, 1)) fw_fat_fclose(t);
    } else if (fw_exfat_vol) {
        if (fw_exfat_mkdir(t, (uint8_t *)fw_exfat_vol + FW_VOL_CWD, path, 1)) fw_exfat_fclose(t);
    }
    struct fw_file f;
    int ok = f_open(&f, path, FW_O_READ);
    if (ok) fw_file_close(&f);
    return ok;
}

static void serve(uint8_t cmd, uint8_t seq, const uint8_t *p, uint32_t len)
{
    char path[96];
    uint8_t out[600];
    struct fw_file f;

    if (cmd == C_RESTART) {
        if (ram->armed && FW_SD_MOUNTED()) write_file(GUARD_PATH, "GOOD", 4);   /* asked for: not a hang */
        reply(cmd, seq, S_OK, 0, 0);
        uint32_t t = fw_millis;
        while (fw_millis - t < 50) { }                  /* let the reply leave */
        restart_now();
    }
    if (cmd == C_INFO) {
        char *o = (char *)out;
        o = put(o, "dirtyloader core 0.5\nfirmware ");
        o = put_hex(o, DL_FW);
        o = put(o, "\nsd ");
        o = put(o, FW_SD_MOUNTED() ? "mounted" : "none");
        o = put(o, "\nmods area ");
        o = put_dec(o, AREA_END - AREA_START);
        o = put(o, "\nloaded");
        for (uint32_t i = 0; i < ram->nmods && i < MAX_MODS; i++) { *o++ = ' '; o = put(o, ram->mods[i]->id); }
        o = put(o, "\n");
        reply(cmd, seq, S_OK, out, (uint32_t)(o - (char *)out));
        return;
    }
    if (cmd == C_PEEK) {                                /* address u32, length u16 (<= 512): read memory */
        if (len != 6) { reply(cmd, seq, S_BAD, 0, 0); return; }
        uint32_t at = le32(p), n = p[4] | p[5] << 8;
        if (n > 512) n = 512;
        reply(cmd, seq, S_OK, (const void *)at, n);
        return;
    }
    if (cmd == C_POKE) {                                /* address u32, bytes: write RAM (development, tests) */
        uint32_t at = len >= 4 ? le32(p) : 0, n = len - 4;
        if (len < 5 || at < 0x20000000u || at + n > 0x20280000u) { reply(cmd, seq, S_BAD, 0, 0); return; }
        for (uint32_t i = 0; i < n; i++) ((volatile uint8_t *)at)[i] = p[4 + i];
        reply(cmd, seq, S_OK, 0, 0);
        return;
    }
    if (!FW_SD_MOUNTED()) { reply(cmd, seq, S_NOCARD, 0, 0); return; }
    if (cmd == C_MKDIRS) {
        reply(cmd, seq, mkdirs("/dirtyloader/mods") ? S_OK : S_IO, 0, 0);
        return;
    }
    if (cmd == C_LIST) {                                /* names in /dirtyloader/<payload>, one per line */
        struct fw_file dir;
        if (!rd_path(path, p, len) || !f_open(&dir, path, FW_O_READ)) { reply(cmd, seq, S_PATH, 0, 0); return; }
        uint32_t n = 0;
        for (;;) {
            zero(&f, sizeof f);
            if (!fw_file_open_next(&f, &dir, FW_O_READ)) break;
            char name[64];
            int k = f.fat ? fw_fat_name(f.fat, name, sizeof name) : fw_exfat_name(f.exfat, name, sizeof name);
            fw_file_close(&f);
            if (k <= 0 || n + (uint32_t)k + 1 > sizeof out) continue;
            for (int i = 0; i < k; i++) out[n++] = (uint8_t)name[i];
            out[n++] = '\n';
        }
        fw_file_close(&dir);
        reply(cmd, seq, S_OK, out, n);
        return;
    }
    if (cmd == C_PUT) {                                 /* offset u32, name len u8, name, data */
        if (len < 5 || len < 5u + p[4] || !PUT_PATH(path, p + 5, p[4])) { reply(cmd, seq, S_PATH, 0, 0); return; }
        uint32_t off = le32(p), skip = 5u + p[4];
        int oflag = off ? FW_O_RDWR : (FW_O_RDWR | FW_O_CREAT | FW_O_TRUNC);
        if (!f_open(&f, path, oflag)) { reply(cmd, seq, S_IO, 0, 0); return; }
        int w = (off && !f_seek(&f, off)) ? -1 : f_write(&f, p + skip, len - skip);
        fw_file_close(&f);
        put32(out, w < 0 ? 0 : (uint32_t)w);
        reply(cmd, seq, w == (int)(len - skip) ? S_OK : S_IO, out, 4);
        return;
    }
    if (cmd == C_CHECK) {                               /* name -> size u32, crc32 u32 */
        if (!rd_path(path, p, len) || !f_open(&f, path, FW_O_READ)) { reply(cmd, seq, S_PATH, 0, 0); return; }
        uint32_t size = 0, crc = 0;
        int k;
        while ((k = f_read(&f, out, 512)) > 0) { crc = crc32(crc, out, (uint32_t)k); size += (uint32_t)k; }
        fw_file_close(&f);
        put32(out, size);
        put32(out + 4, crc);
        reply(cmd, seq, k < 0 ? S_IO : S_OK, out, 8);
        return;
    }
    if (cmd == C_DELETE) {                              /* name: a file under /dirtyloader */
        if (!dl_path(path, p, len)) { reply(cmd, seq, S_PATH, 0, 0); return; }
        reply(cmd, seq, f_remove(path) ? S_OK : S_PATH, 0, 0);
        return;
    }
    if (cmd == C_GET) {                                 /* offset u32, max u16, name len u8, name -> data */
        if (len < 7 || len < 7u + p[6] || !rd_path(path, p + 7, p[6])) { reply(cmd, seq, S_PATH, 0, 0); return; }
        uint32_t off = le32(p), max = p[4] | p[5] << 8;
        if (max > 512) max = 512;
        if (!f_open(&f, path, FW_O_READ)) { reply(cmd, seq, S_PATH, 0, 0); return; }
        int k = (off && !f_seek(&f, off)) ? -1 : f_read(&f, out, max);
        fw_file_close(&f);
        reply(cmd, seq, k < 0 ? S_IO : S_OK, out, k < 0 ? 0 : (uint32_t)k);
        return;
    }
    reply(cmd, seq, S_CMD, 0, 0);
}

#define FW_VECTORS ((volatile uint32_t *)0x2000B800u)

int core_serial(void *m8c)
{
    if (rx_peek() != PKT_MARK) return 0;                /* not ours: the m8c parser runs */
    uint8_t h[5];
    if (!rx_exact(h, 5, 200)) return 1;
    uint32_t len = h[3] | h[4] << 8;
    uint8_t *buf = (uint8_t *)SCRATCH;
    if (len > PKT_MAX) { reply(h[1], h[2], S_BAD, 0, 0); return 1; }
    if (!rx_exact(buf, len + 1, 500)) { reply(h[1], h[2], S_TIMEOUT, 0, 0); return 1; }
    uint8_t sum = (uint8_t)(h[1] + h[2] + h[3] + h[4]);
    for (uint32_t i = 0; i < len; i++) sum += buf[i];
    if (sum != buf[len]) { reply(h[1], h[2], S_SUM, 0, 0); return 1; }
    serve(h[1], h[2], buf, len);
    return 1;
}

/* ---- the MODS page (TELOS) -----------------------------------------------------------------------------------
 * SYSTEM SETTINGS > MODS (TELOS) > OPEN. A screen of the firmware's own kind, in its free view slot: one row
 * per .m8x on the card with its state, APPLY & RESTART last. UP/DOWN move, EDIT switches a mod on or off for the
 * next boot (written to active.txt at once) or restarts on the last row, OPT goes back to SYSTEM SETTINGS.
 *   ON running   +ON on from the next boot   OFF   -OFF off from the next boot   E<n> on, but the boot refused it */
#ifndef SETTINGS_MODS_Y
#define SETTINGS_MODS_Y 12                          /* the field row core's settings template adds */
#endif
#define PAGE_TOP  5                                 /* grid row of the first mod */

static int name_eq(const char *a, const char *b, uint32_t n)
{
    for (uint32_t i = 0; i < n; i++) {
        if (a[i] != b[i]) return 0;
        if (!a[i]) return 1;
    }
    return 1;
}

static void page_read(void)
{
    struct fw_file dir, f;
    ram->page_n = 0;
    if (!f_open(&dir, "/dirtyloader/mods", FW_O_READ)) return;
    while (ram->page_n < MAX_MODS) {
        zero(&f, sizeof f);
        if (!fw_file_open_next(&f, &dir, FW_O_READ)) break;
        char *nm = ram->page[ram->page_n].name;
        int k = f.fat ? fw_fat_name(f.fat, nm, NAME_MAX) : fw_exfat_name(f.exfat, nm, NAME_MAX);
        fw_file_close(&f);
        if (k > 4 && name_eq(nm + k - 4, ".m8x", 5)) { ram->page[ram->page_n].check = 0; ram->page[ram->page_n++].on = 0; }
    }
    fw_file_close(&dir);
    char *const list = (char *)(SCRATCH + STATUS_SIZE);
    int n = 0;
    if (f_open(&f, "/dirtyloader/active.txt", FW_O_READ)) {
        n = f_read(&f, list, LIST_SIZE - 1);
        fw_file_close(&f);
    }
    if (n < 0) n = 0;
    list[n] = 0;
    for (char *p = list; *p;) {
        char *line = p;
        while (*p && *p != '\n' && *p != '\r') p++;
        if (*p) *p++ = 0;
        for (uint32_t i = 0; i < ram->page_n; i++)
            if (name_eq(ram->page[i].name, line, NAME_MAX)) ram->page[i].on = 1;
    }
}

static void page_write(void)
{
    char *const t = (char *)(SCRATCH + STATUS_SIZE);
    char *o = put(t, "# one .m8x per line, from /dirtyloader/mods/; core loads them at boot\n");
    for (uint32_t i = 0; i < ram->page_n; i++)
        if (ram->page[i].on) { o = put(o, ram->page[i].name); *o++ = '\n'; }
    write_file("/dirtyloader/active.txt", t, (uint32_t)(o - t));
    write_file(GUARD_PATH, "GOOD", 4);
}

static int boot_err(const char *name)               /* -1 not loaded at boot, 0 running, n refused */
{
    for (uint32_t i = 0; i < ram->nboot; i++)
        if (name_eq(ram->boot[i].name, name, NAME_MAX)) return ram->boot[i].err;
    return -1;
}

static void row(int r, const char *s)               /* a whole grid row, padded */
{
    char line[FW_GRID_COLS + 1];
    uint32_t i = 0;
    for (; s[i] && i < FW_GRID_COLS; i++) line[i] = s[i];
    for (; i < FW_GRID_COLS; i++) line[i] = ' ';
    line[FW_GRID_COLS] = 0;
    fw_text(fw_grid, 0, r, line);
}

static int page_changed(void)
{
    for (uint32_t i = 0; i < ram->page_n; i++) {
        int e = boot_err(ram->page[i].name);
        if (ram->page[i].on != (e >= 0)) return 1;
    }
    return 0;
}

/* the running mod an .m8x file became, and the page it added */
static const struct dl_mod *mod_of_file(const char *name)
{
    uint32_t k = 0;
    for (uint32_t i = 0; i < ram->nboot && k < ram->nmods; i++) {
        if (ram->boot[i].err) continue;
        if (name_eq(ram->boot[i].name, name, NAME_MAX)) return ram->mods[k];
        k++;
    }
    return 0;
}
static const struct dl_page *page_of_file(const char *name)
{
    const struct dl_mod *m = mod_of_file(name);
    for (uint32_t i = 0; m && i < ram->npages; i++)
        if (ram->pages[i]->mod && seq(ram->pages[i]->mod, m->id)) return ram->pages[i];
    return 0;
}

static void page_draw_all(void)
{
    char b[64], *o;
    for (int r = 0; r < FW_GRID_ROWS; r++) row(r, "");
    o = put(b, ram->skipped == SKIP_CRASH ? " MODS (TELOS)   SKIPPED: A CRASH"
             : ram->skipped == SKIP_HANG ? " MODS (TELOS)   SKIPPED: NO 10 S RUN"
             : ram->skipped == SKIP_HOST ? " MODS (TELOS)   SKIPPED: SAFE BOOT"
             : ram->skipped ? " MODS (TELOS)   SKIPPED" : " MODS (TELOS)");
    *o = 0;
    row(3, b);
    for (uint32_t i = 0; i <= ram->page_n; i++) {
        o = b;
        *o++ = ' ';
        *o++ = i == ram->page_sel ? '>' : ' ';
        if (i == ram->page_n) {
            o = put(o, page_changed() ? "APPLY & RESTART" : "RESTART");
            *o = 0;
            row(PAGE_TOP + (int)i + 1, b);
            o = put(b, " ");
            *o++ = ram->page_sel == ram->page_n + 1 ? '>' : ' ';
            o = put(o, "MOD MENU");
            *o = 0;
            row(PAGE_TOP + (int)i + 2, b);
            break;
        }
        const char *nm = ram->page[i].name;
        uint32_t k = 0;
        while (nm[k] && k < 26) *o++ = nm[k++];
        while (k++ < 27) *o++ = ' ';
        int e = boot_err(nm);
        if (ram->page[i].on && e > 0) { *o++ = 'E'; o = put_dec(o, (uint32_t)e); }
        else if (!ram->page[i].on && ram->page[i].check) { *o++ = 'E'; o = put_dec(o, ram->page[i].check); *o++ = '!'; }
        else if (ram->page[i].on) o = put(o, e == 0 ? "ON" : "+ON");
        else o = put(o, e == 0 ? "-OFF" : "OFF");
        if (page_of_file(nm)) o = put(o, " >");
        *o = 0;
        row(PAGE_TOP + (int)i, b);
    }
    if (!ram->page_n) row(PAGE_TOP, "   NO MODS IN /DIRTYLOADER/MODS");
    o = put(b, " ");
    o = put_dec(o, ram->next - AREA_START);
    o = put(o, " / ");
    o = put_dec(o, AREA_END - AREA_START);
    o = put(o, " BYTES IN USE");
    *o = 0;
    row(20, b);
    row(21, " EDIT ON/OFF  LEFT OFF  RIGHT ON");    /* the firmware draws its track list from column 34 */
    row(22, " RIGHT ON A > ROW: THE MOD'S PAGE");
    row(23, " OPT BACK");
}

static void page_enter(void *view, int arg)
{
    if (ram->page_mode >= 2) { ram->page_dirty = 1; return; }   /* a mod's page, the Mod Menu */
    if (FW_SD_MOUNTED()) page_read();
    else ram->page_n = 0;
    ram->page_sel = 0;
    ram->page_dirty = 1;
}

static int wanted(const char *name)
{
    for (uint32_t i = 0; i < ram->nwant; i++)
        if (name_eq(ram->want[i].name, name, NAME_MAX)) return 1;
    return 0;
}

/* LOAD SONG MODS?: what YES would do to the mods on the card, and what it cannot (not on the card) */
static void song_draw_all(void)
{
    char b[64], *o;
    for (int r = 0; r < FW_GRID_ROWS; r++) row(r, "");
    row(3, " LOAD SONG MODS?");
    int r = PAGE_TOP;
    for (uint32_t i = 0; i < ram->page_n && r < 19; i++) {
        const char *nm = ram->page[i].name;
        int run = boot_err(nm) == 0, want = wanted(nm);
        if (run == want) continue;
        o = put(b, want ? "  + " : "  - ");
        o = put(o, nm);
        *o = 0;
        row(r++, b);
    }
    for (uint32_t i = 0; i < ram->nwant && r < 19; i++) {
        int found = 0;
        for (uint32_t k = 0; k < ram->page_n; k++)
            if (name_eq(ram->page[k].name, ram->want[i].name, NAME_MAX)) found = 1;
        if (found) continue;
        o = put(b, "  ? ");
        o = put(o, ram->want[i].name);
        o = put(o, "  NOT ON THE CARD");
        *o = 0;
        row(r++, b);
    }
    row(20, " + ON  - OFF  ? MISSING");
    row(21, " EDIT YES (RESTART)   OPT NO");
}

static void api_page_open(const struct dl_page *p);
static void api_page_close(void);

/* The check before switching on (core 0.5; TELOS lists it as "not yet"): what core_load would refuse, found
   now. The file is read once: the header, the size against the mods area, the CRC of image and relocations, and
   the dl_mod header's magic, ABI and firmware. A refusal leaves the mod off and shows E<n>! on its row. */
static int check_m8x(const char *name)
{
    char path[96];
    char *o = put(path, "/dirtyloader/mods/");
    for (uint32_t i = 0; name[i] && o < path + sizeof path - 1; i++) *o++ = name[i];
    *o = 0;
    struct fw_file f;
    struct m8x h;
    if (!f_open(&f, path, FW_O_READ)) return E_OPEN;
    int err = 0;
    uint8_t *buf = (uint8_t *)SCRATCH;               /* status text area: free after boot */
    if (!read_exact(&f, &h, sizeof h) || h.magic != M8X_MAGIC || h.image < sizeof(struct dl_mod)) { err = E_HEADER; goto done; }
    uint32_t tail = h.nrel * 4 > h.bss ? h.nrel * 4 : h.bss;
    if (h.image + tail > AREA_END - AREA_START) { err = E_SPACE; goto done; }
    uint32_t left = h.image + h.nrel * 4, crc = 0, first = 1;
    while (left) {
        uint32_t n = left < STATUS_SIZE ? left : STATUS_SIZE;
        if (!read_exact(&f, buf, n)) { err = E_READ; goto done; }
        if (first) {
            const struct dl_mod *m = (const struct dl_mod *)buf;
            if (m->magic != DL_MOD_MAGIC || m->abi != DL_ABI) { err = E_MOD; goto done; }
            if (m->fw && m->fw != DL_FW) { err = E_FIRMWARE; goto done; }
            first = 0;
        }
        crc = crc32(crc, buf, n);
        left -= n;
    }
    if (crc != h.crc) err = E_CRC;
done:
    fw_file_close(&f);
    return err;
}

static void page_set(uint32_t i, uint8_t on)
{
    if (on && FW_SD_MOUNTED() && (ram->page[i].check = (uint8_t)check_m8x(ram->page[i].name)) != 0) return;
    ram->page[i].on = on;
    page_write();
}

static void menu_show(uint32_t back);
static void menu_input(int action);

static void page_input(void *view, int action)
{
    ram->last_action = (uint32_t)action;
    if (ram->page_mode == 3) { menu_input(action); return; }
    if (ram->page_mode == 2) {                      /* a mod's page */
        const struct dl_page *p = ram->cur_page;
        if (p && p->key && p->key(action)) return;
        if (action == FW_KEY_OPT) api_page_close();
        return;
    }
    if (ram->page_mode) {                           /* LOAD SONG MODS? */
        if (action == FW_KEY_EDIT) {
            for (uint32_t i = 0; i < ram->page_n; i++) ram->page[i].on = (uint8_t)wanted(ram->page[i].name);
            page_write();
            restart_now();
        }
        if (action == FW_KEY_OPT) { ram->page_mode = 0; fw_set_view(fw_ui, (int)ram->prev_view); }
        return;
    }
    uint32_t rows = ram->page_n + 2;                 /* the mods, RESTART, MOD MENU */
    if (action == FW_KEY_EDIT && ram->page_sel == ram->page_n + 1) { menu_show(PAGE_BACK_MODS); return; }
    if (action == FW_KEY_UP && ram->page_sel) ram->page_sel--;
    else if (action == FW_KEY_DOWN && ram->page_sel + 1 < rows) ram->page_sel++;
    else if (action == FW_KEY_OPT) { fw_set_view(fw_ui, FW_VIEW_SETTINGS); return; }
    else if (action == FW_KEY_EDIT) {
        if (ram->page_sel == ram->page_n) {         /* RESTART also lifts the crash guard */
            write_file(GUARD_PATH, "GOOD", 4);
            restart_now();
        }
        page_set(ram->page_sel, !ram->page[ram->page_sel].on);
    }
    else if ((action == FW_KEY_RIGHT || action == FW_KEY_LEFT) && ram->page_sel < ram->page_n) {
        const struct dl_page *pg = page_of_file(ram->page[ram->page_sel].name);
        if (action == FW_KEY_RIGHT && pg) { api_page_open(pg); return; }
        uint8_t on = action == FW_KEY_RIGHT;          /* as TELOS: RIGHT on, LEFT off */
        if (ram->page[ram->page_sel].on != on) page_set(ram->page_sel, on);
    }
    ram->page_dirty = 1;
}

static void page_update(void *view) { }

static void menu_draw_all(void);

static void page_draw(void *view)
{
    if (ram->page_mode == 2) {                      /* a mod's page: cleared once, then the mod draws */
        const struct dl_page *p = ram->cur_page;
        if (ram->page_dirty) {
            ram->page_dirty = 0;
            for (int r = 0; r < FW_GRID_ROWS; r++) row(r, "");
            if (p && p->title) { char b[44], *o = put(b, " "); o = put(o, p->title); *o = 0; row(3, b); }
        }
        if (p && p->draw) p->draw();
        return;
    }
    if (!ram->page_dirty) return;
    ram->page_dirty = 0;
    if (ram->page_mode == 3) menu_draw_all();
    else if (ram->page_mode) song_draw_all();
    else page_draw_all();
}

static const void *const page_vt[8] = {
    (const void *)page_enter, (const void *)FW_VIEW_SHARED_04, (const void *)page_input, (const void *)page_update,
    (const void *)page_draw, (const void *)FW_VIEW_NOP, (const void *)FW_VIEW_FLAG_18, (const void *)FW_VIEW_FLAG_1C,
};

/* ev_key, order 0: EDIT on the settings row core adds opens the page */
int core_key(void *ui, int action)
{
    if (((uint8_t *)ui)[FW_UI_VIEW] == FW_VIEW_SETTINGS && fw_settings[5] == SETTINGS_MODS_Y
        && action == FW_KEY_EDIT && fw_views[FW_VIEW_FREE] == &ram->page_view) {
        ram->page_mode = 0;
        fw_set_view(ui, FW_VIEW_FREE);
        return 1;
    }
    return 0;
}

/* ---- songs and their mods ------------------------------------------------------------------------------------
 * After a save, <song>.mods lists the mods that were running (file, id, version per line). After a load (not
 * the boot's own), when the list differs from what runs, the MODS page asks LOAD SONG MODS?. A song saved
 * without a list says nothing. The SD work waits for core_tick: the firmware's own file is closed by then. */
/* what: 1 a load (the user's: data, then LOAD SONG MODS?), 2 a save, 3 the boot's load (data only) */
static void song_note(const char *path, uint32_t what)
{
    uint32_t i = 0;
    for (; path && path[i] && i < sizeof ram->song - 1; i++) ram->song[i] = path[i];
    ram->song[i] = 0;
    if (!i) return;
    ram->song_at = fw_millis;
    ram->song_tries = 0;
    ram->data_done = 0;
    ram->song_pending = what;
}

void core_song_load(void *songs, const char *path)
{
    song_note(path, ram->booted ? 1 : 3);           /* the AUTOSAVE load during setup(): its data, no prompt */
}

void core_song_save(void *songs, const char *path) { song_note(path, 2); }

static char *mods_path(char *out)                  /* put() does not terminate: these do */
{
    char *o = put(put(out, ram->song), ".mods");
    *o = 0;
    return o;
}

/* <song>.dldata: "DLD1", count u32, then per block: id[24], size u32, the bytes */
#define DATA_MAGIC 0x31444C44u
#define DATA_ID    24u
static char *data_path(char *out)
{
    char *o = put(put(out, ram->song), ".dldata");
    *o = 0;
    return o;
}

static int data_save(void)
{
    if (!ram->ndata) return 1;
    char path[140];
    struct fw_file f;
    data_path(path);
    if (!f_open(&f, path, FW_O_RDWR | FW_O_CREAT | FW_O_TRUNC)) return 0;
    uint32_t h[2] = { DATA_MAGIC, ram->ndata };
    int ok = f_write(&f, h, 8) == 8;
    for (uint32_t i = 0; ok && i < ram->ndata; i++) {
        const struct dl_song_data *d = ram->data[i];
        char id[DATA_ID];
        zero(id, sizeof id);
        for (uint32_t k = 0; d->id[k] && k < DATA_ID - 1; k++) id[k] = d->id[k];
        ok = f_write(&f, id, DATA_ID) == DATA_ID && f_write(&f, &d->size, 4) == 4
             && f_write(&f, d->data, d->size) == (int)d->size;
    }
    fw_file_close(&f);
    return ok;
}

/* 0 done, 1 the card is still busy: try again */
static int data_load(void)
{
    if (!ram->ndata || ram->data_done) return 0;
    char path[140];
    struct fw_file f;
    uint32_t got[MAX_DATA];
    zero(got, sizeof got);
    data_path(path);
    if (f_open(&f, path, FW_O_READ)) {
        uint32_t h[2], pos = 8;
        if (read_exact(&f, h, 8) && h[0] == DATA_MAGIC) {
            for (uint32_t b = 0; b < h[1] && b < 64; b++) {
                char id[DATA_ID];
                uint32_t size;
                if (!read_exact(&f, id, DATA_ID) || !read_exact(&f, &size, 4)) break;
                pos += DATA_ID + 4;
                id[DATA_ID - 1] = 0;
                for (uint32_t i = 0; i < ram->ndata; i++) {
                    const struct dl_song_data *d = ram->data[i];
                    if (!name_eq(d->id, id, DATA_ID)) continue;
                    uint32_t n = size < d->size ? size : d->size;
                    if (read_exact(&f, d->data, n)) got[i] = n ? n : 1;
                }
                pos += size;
                if (!f_seek(&f, pos)) break;
            }
        }
        fw_file_close(&f);
    } else {
        if (!f_open(&f, ram->song, FW_O_READ)) return 1;  /* the card is busy: the song itself will not open */
        fw_file_close(&f);                                /* the song has no data */
    }
    ram->data_done = 1;
    for (uint32_t i = 0; i < ram->ndata; i++)
        if (ram->data[i]->loaded) ram->data[i]->loaded(got[i]);
    return 0;
}

static void song_saved(void)
{
    char path[140], *const t = (char *)(SCRATCH + STATUS_SIZE), *o = t;
    o = put(o, "# dirtyloader: the mods running when this song was saved (file id version)\n");
    uint32_t k = 0;
    for (uint32_t i = 0; i < ram->nboot && k < ram->nmods; i++) {
        if (ram->boot[i].err) continue;
        const struct dl_mod *m = ram->mods[k++];
        o = put(o, ram->boot[i].name); *o++ = ' ';
        o = put(o, m->id); *o++ = ' ';
        o = put(o, m->version); *o++ = '\n';
    }
    mods_path(path);
    ram->song_result = write_file(path, t, (uint32_t)(o - t)) && data_save() ? 1 : 2;
}

static int song_loaded(void)                       /* 0 done, 1 the list could not be read yet */
{
    char path[140];
    struct fw_file f;
    char *const t = (char *)(SCRATCH + STATUS_SIZE);
    mods_path(path);
    if (!f_open(&f, path, FW_O_READ)) return 1;     /* still busy, or saved without a list */
    int n = f_read(&f, t, LIST_SIZE - 1);
    fw_file_close(&f);
    if (n < 0) return 1;
    t[n] = 0;
    ram->nwant = 0;
    for (char *p = t; *p;) {
        char *line = p;
        while (*p && *p != '\n' && *p != '\r') p++;
        if (*p) *p++ = 0;
        if (*line == '#' || !*line || ram->nwant >= MAX_MODS) continue;
        uint32_t i = 0;
        while (line[i] && line[i] != ' ' && i < NAME_MAX - 1) { ram->want[ram->nwant].name[i] = line[i]; i++; }
        ram->want[ram->nwant++].name[i] = 0;
    }
    uint32_t same = 1, running = 0;
    for (uint32_t i = 0; i < ram->nboot; i++)
        if (!ram->boot[i].err) { running++; if (!wanted(ram->boot[i].name)) same = 0; }
    if (same && running == ram->nwant) return 0;
    page_read();
    ram->page_mode = 1;
    ram->prev_view = fw_ui[FW_UI_VIEW];
    fw_set_view(fw_ui, FW_VIEW_FREE);
    return 0;
}

/* The firmware is still writing (or reading) the song for a while after its routine is entered, and a file
   core creates meanwhile fails: wait SONG_WAIT ms, and retry a failed write, before giving up. */
#define SONG_WAIT  300u
#define SONG_TRIES 10u
#define EV_USB_W 0x0003u
static int fire(uint32_t word, uint32_t a0, uint32_t a1);
void core_tick(void)
{
    uint32_t usb = fw_usb_configuration != 0;
    if (usb != ram->usb_last) { ram->usb_last = usb; fire(EV_USB_W, usb, 0); }
    if (ram->armed && ram->booted && fw_millis - ram->armed_at >= ARMED_MS && FW_SD_MOUNTED()) {
        if (write_file(GUARD_PATH, "GOOD", 4)) ram->armed = 0;   /* this set runs: no hang at boot */
        else ram->armed_at += 1000;
    }
    uint32_t what = ram->song_pending;
    if (!what || !FW_SD_MOUNTED() || fw_millis - ram->song_at < SONG_WAIT) return;
    if (what == 2) {
        song_saved();
        if (ram->song_result != 1 && ++ram->song_tries < SONG_TRIES) { ram->song_at = fw_millis; return; }
        ram->song_pending = 0;
    } else {
        int busy = data_load();
        if (!busy && what == 1) busy = song_loaded();
        if (busy && ++ram->song_tries < SONG_TRIES) { ram->song_at = fw_millis; return; }
        if (busy && !ram->data_done) {               /* never readable: tell the mods there is nothing */
            ram->data_done = 1;
            for (uint32_t i = 0; i < ram->ndata; i++) if (ram->data[i]->loaded) ram->data[i]->loaded(0);
        }
        ram->song_pending = 0;
    }
}

/* ---- events core raises from C --------------------------------------------------------------------------------
 * fire() calls the dispatcher (core 0.2's, at the start of the hook bus, CORE_DISPATCH) as a site stub does:
 * ip = event | TAKE, arguments in r0-r3; it returns the taking handler's result, or 0. */
#ifndef CORE_DISPATCH
#error "CORE_DISPATCH comes from the builder"
#endif
#define TAKE 0x10000u
static int fire(uint32_t word, uint32_t a0, uint32_t a1)
{
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r1 __asm__("r1") = a1;
    register uint32_t ip __asm__("ip") = word;
    register uint32_t fn __asm__("r3") = CORE_DISPATCH;
    __asm volatile("blx r3" : "+r"(r0), "+r"(r1), "+r"(ip), "+r"(fn) : : "r2", "lr", "memory", "cc");
    return (int)r0;
}
static int fire3(uint32_t word, uint32_t a0, uint32_t a1, uint32_t a2)
{
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r1 __asm__("r1") = a1;
    register uint32_t r2 __asm__("r2") = a2;
    register uint32_t ip __asm__("ip") = word;
    register uint32_t fn __asm__("r3") = CORE_DISPATCH;
    __asm volatile("blx r3" : "+r"(r0), "+r"(r1), "+r"(r2), "+r"(ip), "+r"(fn) : : "lr", "memory", "cc");
    return (int)r0;
}

/* ev_audio_out: the tap's update() (vtable slot 0, in RAM) gets the master output's two blocks first: a handler
   processes them in place (insert: USB, the recorder and I2S all get it) or writes them (exclusive). A silent
   output has no blocks: with handlers, core allocates zeroed ones so they can write. */
#define EV_AUDIO_OUT_W (0x0032u | TAKE)
static void core_tap(void *obj)
{
    uint8_t **q = *(uint8_t ***)((uint8_t *)obj + 0x20);
    if (ram->audio_subs && q) {
        for (int i = 0; i < 2; i++)
            if (!q[i] && (q[i] = fw_audio_alloc()) != 0) zero(q[i] + 4, FW_AUDIO_FRAMES * 4);
        if (q[0] && q[1]) fire3(EV_AUDIO_OUT_W, (uint32_t)(q[0] + 4), (uint32_t)(q[1] + 4), FW_AUDIO_FRAMES);
    }
    ((void (*)(void *))ram->tap_orig)(obj);
}

/* ev_track_audio, ev_fx_audio, ev_render_params: the same idea at other objects of the graph (fw.h). A track's
   blocks are read after its update, from its main strip's input queue: the same blocks reach its three sends, so
   a change in place is heard everywhere. A send effect's input is handed over before the effect runs. */
#define EV_TRACK_AUDIO_W 0x0033u
#define EV_FX_AUDIO_W    (0x0034u | TAKE)
#define EV_PARAMS_W      0x0035u
typedef void (*update_fn)(void *);
static void core_track(void *obj)
{
    ((update_fn)ram->track_orig)(obj);
    if (!ram->track_subs) return;
    uint8_t *strip = (uint8_t *)obj + FW_TRACK_MAIN;
    uint8_t **q = *(uint8_t ***)(strip + 0x20);
    uint32_t inputs = strip[0x18];                  /* the track sends on ports 0/1, and 2/3 while it crossfades */
    for (uint32_t p = 0; q && p + 1 < inputs && p < 4; p += 2)
        if (q[p] && q[p + 1])
            fire3(EV_TRACK_AUDIO_W, (uint32_t)(q[p] + 4), (uint32_t)(q[p + 1] + 4), ((uint8_t *)obj)[0x3D]);
}
/* A taken stereo effect (MFX, reverb) does not run: the handler's blocks go to its two outputs in its place, and
   its input queue is released and cleared as its own update would. The delay (mono in) is not replaceable. */
static int fx_in(void *obj, uint32_t stage, int stereo)
{
    uint8_t **q = *(uint8_t ***)((uint8_t *)obj + 0x20);
    if (!ram->fx_subs || !q || !q[0] || (stereo && !q[1])) return 0;
    int taken = fire3(EV_FX_AUDIO_W, stage, (uint32_t)(q[0] + 4), stereo ? (uint32_t)(q[1] + 4) : 0);
    if (!taken || !stereo) return 0;
    for (int i = 0; i < 2; i++) {
        fw_audio_transmit(obj, q[i], i);
        fw_audio_release(q[i]);
        q[i] = 0;
    }
    return 1;
}
static void core_mfx(void *obj) { if (!fx_in(obj, FW_FX_MFX, 1)) ((update_fn)ram->mfx_orig)(obj); }
static void core_delay(void *obj) { fx_in(obj, FW_FX_DELAY, 0); ((update_fn)ram->delay_orig)(obj); }
static void core_reverb(void *obj) { if (!fx_in(obj, FW_FX_REVERB, 1)) ((update_fn)ram->reverb_orig)(obj); }
static void core_clock(void *obj)
{
    if (ram->params_subs) fire3(EV_PARAMS_W, (uint32_t)fw_audio_engine, 0, 0);
    ((update_fn)ram->clock_orig)(obj);
}

/* ev_step_edit for bulk edits: every phrase edit ends in the phrase view's +0x34 (bulk) or +0x38 (one cell; its
   entry is already ev_step_edit's site). Core keeps the phrase as it last saw it and, after a bulk redraw, reports
   the steps that changed: ev_step_edit(view, first changed step, steps from it to the last changed, -1). A redraw
   that changed nothing (a selection, a copy) says nothing. */
#define EV_STEP_EDIT_W 0x0081u
static int fire4(uint32_t word, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3);
static uint8_t *phrase_of(void *view) { return FW_PHRASE_STEP(((uint8_t *)view)[4], 0); }
static void snap_take(void *view)
{
    uint8_t *p = phrase_of(view);
    for (uint32_t i = 0; i < sizeof ram->snap; i++) ram->snap[i] = p[i];
    ram->snap_phrase = ((uint8_t *)view)[4];
}
static void core_phrase_bulk(void *view, uint32_t a1, uint32_t a2, uint32_t a3)
{
    ((void (*)(void *, uint32_t, uint32_t, uint32_t))ram->bulk_orig)(view, a1, a2, a3);
    uint8_t *p = phrase_of(view);
    if (ram->snap_phrase == ((uint8_t *)view)[4]) {
        int first = -1, last = -1;
        for (int s = 0; s < 16; s++)
            for (int k = 0; k < 9; k++)
                if (p[s * 9 + k] != ram->snap[s * 9 + k]) { if (first < 0) first = s; last = s; break; }
        if (first >= 0)
            fire4(EV_STEP_EDIT_W, (uint32_t)view, (uint32_t)(p + first * 9), (uint32_t)(last - first + 1), 0xFFFFFFFFu);
    }
    snap_take(view);
}
static void core_phrase_cell(void *view, uint32_t a1, uint32_t a2, uint32_t a3)
{
    ((void (*)(void *, uint32_t, uint32_t, uint32_t))ram->cell_orig)(view, a1, a2, a3);   /* ev_step_edit's site */
    snap_take(view);
}

static uint32_t has_subs(uint16_t ev)
{
    for (uint32_t i = 0; i < ram->count; i++) if (ram->table[i].event == ev) return 1;
    return 0;
}
static void wrap_slot(uint32_t slot, uint32_t *orig, uint32_t fn)
{
    volatile uint32_t *s = (volatile uint32_t *)slot;
    if (*s != (fn | 1)) { *orig = *s; *s = fn | 1; }
}

static int fire4(uint32_t word, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3)
{
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r1 __asm__("r1") = a1;
    register uint32_t r2 __asm__("r2") = a2;
    register uint32_t r3 __asm__("r3") = a3;
    register uint32_t ip __asm__("ip") = word;
    register uint32_t fn __asm__("r4") = CORE_DISPATCH;
    __asm volatile("blx r4" : "+r"(r0), "+r"(r1), "+r"(r2), "+r"(r3), "+r"(ip), "+r"(fn) : : "lr", "memory", "cc");
    return (int)r0;
}

/* ev_sysex: usbMIDI's SysEx handler pointer (FW_SYSEX_HANDLER) is the firmware's, set in setup(); core_boot
   puts core_sysex there and keeps the firmware's to call when no handler takes the chunk. */
#define EV_SYSEX_W (0x0047u | TAKE)
static void core_sysex(const uint8_t *data, uint32_t len, uint32_t last)
{
    if (fire3(EV_SYSEX_W, (uint32_t)data, len, last)) return;
    if (ram->sysex_orig) ((void (*)(const uint8_t *, uint32_t, uint32_t))ram->sysex_orig)(data, len, last);
}

/* ev_render_in / ev_render_out: the audio library renders each block in the software interrupt (IRQ 70, vector
   86 of the RAM vector table); core_boot puts this in its place. Audio-thread handlers belong in ITCM, which is
   where loaded mods run. */
#define EV_RENDER_IN_W  0x0030u
#define EV_RENDER_OUT_W 0x0031u
#define FW_AUDIO_VECTOR (16 + 70)
static void core_audio(void)
{
    fire(EV_RENDER_IN_W, 0, 0);
    ((void (*)(void))ram->audio_orig)();
    fire(EV_RENDER_OUT_W, 0, 0);
}

/* ev_midi: usb_midi_read's call of usb_midi_read_message comes here. Packets mods played in (midi_receive) go
   first; a packet a handler takes is dropped, and the next one is read. */
#define EV_MIDI_W (0x0043u | TAKE)
uint32_t core_midi_read(void)
{
    for (;;) {
        uint32_t pk;
        if (ram->midi_head != ram->midi_tail) pk = ram->midi_q[ram->midi_tail++ % MIDI_Q];
        else pk = fw_usb_midi_read_message();
        if (!pk || !fire(EV_MIDI_W, pk, 0)) return pk;
    }
}

/* ---- the API for mods (dl/core.h) --------------------------------------------------------------------------- */
static void api_restart(void)
{
    if (ram->armed && FW_SD_MOUNTED()) write_file(GUARD_PATH, "GOOD", 4);       /* asked for: not a hang */
    uint32_t t = fw_millis;
    while (fw_millis - t < 50) { }                  /* let USB send what it has */
    restart_now();
}
static int api_page_add(const struct dl_page *p)
{
    if (!p || ram->npages >= MAX_PAGES) return 0;
    ram->pages[ram->npages++] = p;
    return 1;
}
static void api_page_open(const struct dl_page *p)
{
    if (!p || fw_views[FW_VIEW_FREE] != &ram->page_view) return;
    uint32_t here = fw_ui[FW_UI_VIEW];
    ram->page_back = here == FW_VIEW_FREE ? (ram->page_mode == 2 ? ram->page_back
                                             : ram->page_mode == 3 ? PAGE_BACK_MENU : PAGE_BACK_MODS) : here;
    ram->cur_page = p;
    ram->page_mode = 2;
    ram->page_dirty = 1;
    if (p->open) p->open();
    if (here != FW_VIEW_FREE) fw_set_view(fw_ui, FW_VIEW_FREE);
}
static void api_page_close(void)
{
    if (ram->page_mode != 2) return;
    ram->page_mode = 0;
    ram->cur_page = 0;
    if (ram->page_back == PAGE_BACK_MODS) {
        if (FW_SD_MOUNTED()) page_read();
        ram->page_dirty = 1;
    } else if (ram->page_back == PAGE_BACK_MENU) {
        ram->page_mode = 3;
        ram->page_dirty = 1;
    } else {
        fw_set_view(fw_ui, (int)ram->page_back);
    }
}
/* ---- the Mod Menu (core-dn1's) --------------------------------------------------------------------------------
 * Every mod page as a grid, two across, then the mods' settings. UP / DOWN move a row; LEFT / RIGHT move across the
 * grid, or change the setting under the cursor; EDIT opens a page; OPT goes back. Settings are kept in
 * /dirtyloader/settings.txt as label=value lines. */
#define SETTINGS_PATH "/dirtyloader/settings.txt"
#define MENU_TOP 5

static void settings_save(void)
{
    char *const t = (char *)(SCRATCH + STATUS_SIZE), *o = t;
    for (uint32_t i = 0; i < ram->nsettings && o < t + LIST_SIZE - 32; i++) {
        o = put(o, ram->settings[i]->label);
        *o++ = '=';
        o = put_dec(o, *ram->settings[i]->value);
        *o++ = 10;
    }
    if (FW_SD_MOUNTED()) write_file(SETTINGS_PATH, t, (uint32_t)(o - t));
}

static void setting_load(const struct dl_setting *s)
{
    struct fw_file f;
    char *const t = (char *)(SCRATCH + STATUS_SIZE);
    if (!f_open(&f, SETTINGS_PATH, FW_O_READ)) return;
    int n = f_read(&f, t, LIST_SIZE - 1);
    fw_file_close(&f);
    if (n <= 0) return;
    t[n] = 0;
    for (char *p = t; *p;) {
        char *line = p;
        while (*p && *p != 10 && *p != 13) p++;
        if (*p) *p++ = 0;
        char *eq = line;
        while (*eq && *eq != '=') eq++;
        if (!*eq) continue;
        *eq = 0;
        if (!seq(line, s->label)) continue;
        uint32_t v = 0;
        for (char *d = eq + 1; *d >= '0' && *d <= '9'; d++) v = v * 10 + (uint32_t)(*d - '0');
        if (v >= s->min && v <= s->max) *s->value = (uint8_t)v;
    }
}

static int api_setting_add(const struct dl_setting *s)
{
    if (!s || !s->label || !s->value || s->min > s->max || ram->nsettings >= MAX_SETTINGS) return 0;
    ram->settings[ram->nsettings++] = s;
    if (FW_SD_MOUNTED()) setting_load(s);
    return 1;
}

static uint32_t menu_rows_pages(void) { return (ram->npages + 1) / 2; }

static void menu_draw_all(void)
{
    char b[48], *o;
    for (int r = 0; r < FW_GRID_ROWS; r++) row(r, "");
    row(3, " MOD MENU");
    for (uint32_t i = 0; i < ram->npages; i++) {
        o = b;
        *o++ = ' ';
        *o++ = ram->menu_sel == i ? '>' : ' ';
        const char *t = ram->pages[i]->title ? ram->pages[i]->title : ram->pages[i]->mod;
        for (uint32_t k = 0; t && t[k] && k < 14; k++) *o++ = t[k];
        *o = 0;
        fw_text(fw_grid, (int)(i & 1) * 16, MENU_TOP + (int)(i / 2), b);
    }
    if (!ram->npages) row(MENU_TOP, "   NO MOD PAGES");
    int r = MENU_TOP + (int)(ram->npages ? menu_rows_pages() : 1) + 1;
    if (ram->nsettings) row(r++, " SETTINGS");
    for (uint32_t i = 0; i < ram->nsettings && r < 20; i++, r++) {
        const struct dl_setting *s = ram->settings[i];
        o = b;
        *o++ = ' ';
        *o++ = ram->menu_sel == ram->npages + i ? '>' : ' ';
        uint32_t k = 0;
        for (; s->label[k] && k < 16; k++) *o++ = s->label[k];
        while (k++ < 18) *o++ = ' ';
        uint8_t v = *s->value;
        if (s->names) { const char *nm = s->names[v - s->min]; for (k = 0; nm[k] && k < 12; k++) *o++ = nm[k]; }
        else o = put_dec(o, v);
        *o = 0;
        row(r, b);
    }
    row(21, " EDIT OPEN  LEFT/RIGHT CHANGE");
    row(22, " OPT BACK");
}

static void menu_show(uint32_t back)
{
    if (fw_views[FW_VIEW_FREE] != &ram->page_view) return;
    uint32_t here = fw_ui[FW_UI_VIEW];
    ram->menu_back = here == FW_VIEW_FREE ? back : here;
    ram->menu_sel = 0;
    ram->page_mode = 3;
    ram->page_dirty = 1;
    if (here != FW_VIEW_FREE) fw_set_view(fw_ui, FW_VIEW_FREE);
}
static void api_menu_open(void) { menu_show(PAGE_BACK_MODS); }

static void menu_input(int action)
{
    uint32_t np = ram->npages, n = np + ram->nsettings, sel = ram->menu_sel;
    if (action == FW_KEY_OPT) {
        ram->page_mode = 0;
        if (ram->menu_back == PAGE_BACK_MODS) { if (FW_SD_MOUNTED()) page_read(); ram->page_dirty = 1; }
        else fw_set_view(fw_ui, (int)ram->menu_back);
        return;
    }
    if (sel < np) {                                 /* the grid */
        if (action == FW_KEY_EDIT) { api_page_open(ram->pages[sel]); return; }
        if (action == FW_KEY_RIGHT && (sel & 1) == 0 && sel + 1 < np) sel++;
        else if (action == FW_KEY_LEFT && (sel & 1)) sel--;
        else if (action == FW_KEY_DOWN) sel = sel + 2 < np ? sel + 2 : (ram->nsettings ? np : sel);
        else if (action == FW_KEY_UP && sel >= 2) sel -= 2;
    } else if (sel < n) {                           /* a setting */
        const struct dl_setting *s = ram->settings[sel - np];
        uint8_t v = *s->value;
        if (action == FW_KEY_RIGHT && v < s->max) v++;
        else if (action == FW_KEY_LEFT && v > s->min) v--;
        else if (action == FW_KEY_DOWN && sel + 1 < n) sel++;
        else if (action == FW_KEY_UP) sel = sel > np ? sel - 1 : (np ? ((np - 1) & ~1u) : sel);
        if (v != *s->value) { *s->value = v; settings_save(); if (s->changed) s->changed(); }
    }
    ram->menu_sel = sel;
    ram->page_dirty = 1;
}

static int api_song_data(const struct dl_song_data *d)
{
    if (!d || !d->id || ram->ndata >= MAX_DATA) return 0;
    ram->data[ram->ndata++] = d;
    return 1;
}
static int api_file_read(const char *path, uint32_t off, void *buf, uint32_t n)
{
    struct fw_file f;
    if (!f_open(&f, path, FW_O_READ)) return -1;
    int k = (off && !f_seek(&f, off)) ? -1 : f_read(&f, buf, n);
    fw_file_close(&f);
    return k;
}
static int api_file_write(const char *path, const void *buf, uint32_t n)
{
    return write_file(path, buf, n) ? (int)n : -1;
}
static void api_midi_receive(uint32_t packet)
{
    if (ram->midi_head - ram->midi_tail < MIDI_Q) ram->midi_q[ram->midi_head++ % MIDI_Q] = packet;
}
static void api_midi_send(uint32_t packet) { fw_usb_midi_write_packed(packet); }

/* core_mod_dests: each engine's destination getters (vtable +0xF8 name, +0x104 count, in RAM) are swapped for
   these the first time a mod adds a destination to that engine; `this`'s vtable says which engine it is. */
static const uint32_t ENGINE_VT[FW_ENGINES] = FW_ENGINE_VTABLES;
static int engine_of(const void *eng)
{
    uint32_t vt = *(const uint32_t *)eng;
    for (int i = 0; i < FW_ENGINES; i++) if (ENGINE_VT[i] == vt) return i;
    return -1;
}
static uint32_t core_dest_count(void *eng)
{
    int i = engine_of(eng);
    return i < 0 ? 1 : ram->dest_stock[i] + ram->dest_n[i];
}
static const char *core_dest_name(void *eng, uint32_t dest)
{
    int i = engine_of(eng);
    if (i < 0) return "";
    uint32_t n = ram->dest_stock[i] + ram->dest_n[i];
    if (dest >= n) dest = n - 1;
    if (dest < ram->dest_stock[i])                  /* the stock getter clamps with the count: below it, fine */
        return ((const char *(*)(void *, uint32_t))ram->dest_name_orig[i])(eng, dest);
    return ram->dest_extra[i][dest - ram->dest_stock[i]];
}
static int api_mod_dest_add(int engine, const char *name)
{
    if (engine < 0 || engine >= FW_ENGINES || !name) return 0;
    volatile uint32_t *vt = (volatile uint32_t *)ENGINE_VT[engine];
    if (vt[FW_VT_DEST_COUNT / 4] != ((uint32_t)core_dest_count | 1)) {
        ram->dest_name_orig[engine] = vt[FW_VT_DEST_NAME / 4];
        ram->dest_count_orig[engine] = vt[FW_VT_DEST_COUNT / 4];
        uint32_t as_engine = ENGINE_VT[engine];     /* an object whose vtable is this engine's: the getter is
                                                       `movs r0, #N` and reads nothing, but give it the right one */
        ram->dest_stock[engine] = ((uint32_t (*)(void *))ram->dest_count_orig[engine])(&as_engine);
        ram->dest_n[engine] = 0;
        vt[FW_VT_DEST_NAME / 4] = (uint32_t)core_dest_name | 1;
        vt[FW_VT_DEST_COUNT / 4] = (uint32_t)core_dest_count | 1;
    }
    if (ram->dest_stock[engine] + ram->dest_n[engine] >= FW_MOD_DESTS_MAX) return 0;
    ram->dest_extra[engine][ram->dest_n[engine]++] = name;
    return (int)(ram->dest_stock[engine] + ram->dest_n[engine] - 1);
}
static int api_inst_load(const char *path, int slot)
{
    if (slot < 0 || slot > 0x7F || !FW_SD_MOUNTED()) return 0;
    return fw_inst_load(fw_songs, path, slot, 0);
}
static int api_inst_save(const char *path, int slot)
{
    if (slot < 0 || slot > 0x7F || !FW_SD_MOUNTED()) return 0;
    return fw_inst_save(fw_songs, path, slot);
}

static const struct dl_core api = {
    DL_CORE_MAGIC, DL_CORE_VERSION, sizeof(struct dl_core),
    api_restart, api_page_add, api_page_open, api_page_close, api_song_data, api_file_read, api_file_write,
    api_midi_receive, api_midi_send, ram->crash, ram->song, api_inst_load, api_inst_save, api_mod_dest_add,
    api_setting_add, api_menu_open,
};

/* ev_crash: core's handler in front of Teensyduino's for HardFault, MemManage, BusFault and UsageFault (RAM vector
   table). It runs the mods' handlers with the exception frame (r0-r3, r12, lr, pc, xpsr), counts that they ran in
   ITCM (which survives the reset), and goes on to Teensyduino's handler with the stack and lr as they were: that
   handler records the crash and resets. A handler that faults again is skipped (in_fault). Handlers run in the
   fault: no SD, no USB, no waiting. */
#define EV_CRASH_W 0x0004u
uint32_t core_crash(const uint32_t *frame)
{
    if (!ram->in_fault && ram->magic == RAM_MAGIC) {
        ram->in_fault = 1;
        ram->fault_pc = frame[6];
        fire(EV_CRASH_W, (uint32_t)frame, 0);
        ram->fault_handled++;
    }
    return ram->fault_orig;
}
__attribute__((naked)) static void core_fault(void)
{
    __asm volatile(
        "tst    lr, #4          \n"
        "ite    eq              \n"
        "mrseq  r0, msp         \n"
        "mrsne  r0, psp         \n"
        "push   {r4, lr}        \n"
        "bl     core_crash      \n"
        "pop    {r4, lr}        \n"
        "bx     r0              \n");
}

static void itcm_writable(void)
{
    volatile uint32_t *rnr = (uint32_t *)0xE000ED98u, *rasr = (uint32_t *)0xE000EDA0u;
    *rnr = 1;                                       /* MPU region 1 = ITCM: read-only -> read/write */
    *rasr = (*rasr & ~(7u << 24)) | (3u << 24);
    __asm volatile("dsb; isb" ::: "memory");
}

/* The ITCM sites' veneers: the builder lists them at CORE_VENEERS (count, then itcm address and flash stub per
   site); each becomes `ldr.w pc, [pc, #0]` and the stub's address, in the ITCM tail above core's RAM. */
#ifndef CORE_VENEERS
#error "CORE_VENEERS comes from the builder"
#endif
static void write_veneers(void)
{
    const uint32_t *t = (const uint32_t *)CORE_VENEERS;
    uint32_t n = t[0];
    if (n > 16) return;                             /* erased flash: no ITCM sites */
    for (uint32_t i = 0; i < n; i++) {
        volatile uint32_t *v = (volatile uint32_t *)t[1 + 2 * i];
        v[0] = 0xF000F8DFu;                         /* ldr.w pc, [pc, #0] */
        v[1] = t[2 + 2 * i];
    }
    __asm volatile("dsb; isb" ::: "memory");
}

void core_early(void)
{
    itcm_writable();
    write_veneers();
    ram->magic = 0;
    ram->loaded = 0;
    ram->api = &api;
}


/* The skip key at power-on, for a unit without keys: `python -m dirtyloader.unit safe` keeps sending SAFE_MAGIC
   over USB serial while the unit boots. core_load runs about 0.3 s after reset; a computer has configured USB
   within ~10 ms of that, and the tool's first bytes arrive ~160 ms later (measured on the Teensy). So core waits
   up to USB_WAIT_MS for USB, then listens SAFE_MS: a boot costs ~0.35 s more on a computer, 0.25 s on a charger.
   The bytes are all >= 0x80: they start no m8c command (ASCII) and are not core's request mark (0xD1). */
#define USB_WAIT_MS 250u
#define SAFE_MS 350u
static int safe_boot_asked(void)
{
    static const uint8_t want[] = { 0xF5, 0xDA, 0xA5, 0xFE, 0xC4, 0xB7, 0 };
    uint32_t t0 = fw_millis, k = 0;
    while (!fw_usb_configuration && fw_millis - t0 < USB_WAIT_MS) { }
    if (!fw_usb_configuration) return 0;
    t0 = fw_millis;
    while (fw_millis - t0 < SAFE_MS) {
        uint8_t c;
        if (!fw_rx_available || fw_serial_read(&c, 1) != 1) continue;
        k = c == want[k] ? k + 1 : c == want[0];
        if (!want[k]) return 1;
    }
    return 0;
}

void core_load(void)
{
    uint16_t orders[SLOTS];
    char *const status = (char *)SCRATCH;
    char *o = status;
    uint32_t had_mods = ram->sig == RAM_SIG ? ram->nmods : 0;   /* from the boot before, if it was a reset */

    ram->sig = RAM_SIG;
    ram->booted = 0;
    ram->song_pending = 0;
    ram->page_mode = 0;
    ram->npages = ram->ndata = ram->nsettings = 0;
    ram->cur_page = 0;
    ram->midi_head = ram->midi_tail = 0;
    ram->armed = 0;
    ram->song[0] = 0;
    ram->usb_last = 0xFFu;
    ram->loaded = 1;
    ram->nmods = 0;
    ram->nboot = 0;
    ram->next = AREA_START;
    flash_hooks(orders);
    if (!FW_SD_MOUNTED())
        return;

    o = put(o, "dirtyloader core 0.5\nmods area ");
    o = put_dec(o, AREA_END - AREA_START);
    o = put(o, " bytes at ");
    o = put_hex(o, AREA_START);
    o = put(o, "\n");

    int skip = SKIP_NONE;
    uint32_t guard = read_guard();
    int host_skip = safe_boot_asked();
    zero(ram->crash, sizeof ram->crash);
    if (crashed())
        for (uint32_t i = 0; i < 8; i++) ram->crash[i] = fw_fault_info[i];
    if (crashed() && had_mods) {
        o = put(o, "crash guard: the last boot with mods crashed (pc ");
        o = put_hex(o, fw_fault_info[6]);
        o = put(o, "), so no mods were loaded.\n");
        write_file(GUARD_PATH, "SKIP", 4);
        skip = SKIP_CRASH;
    } else if (host_skip) {
        o = put(o, "safe boot: the host asked (python -m dirtyloader.unit safe), so no mods were loaded.\n");
        write_file(GUARD_PATH, "SKIP", 4);
        skip = SKIP_HOST;
    } else if (guard == G_ARMD) {
        o = put(o, "crash guard: the last boot with mods did not run 10 s (a hang, or the power went), so no mods "
                   "were loaded.\n");
        write_file(GUARD_PATH, "SKIP", 4);
        skip = SKIP_HANG;
    } else if (guard == G_SKIP) {
        o = put(o, "crash guard: guard says SKIP, so no mods were loaded.\n");
        skip = SKIP_GUARD;
    }
    if (crashed() && ram->sig == RAM_SIG && ram->fault_handled) {
        o = put(o, "ev_crash: the mods' handlers ran in the fault (pc ");
        o = put_hex(o, ram->fault_pc);
        o = put(o, ")\n");
    }
    ram->fault_handled = 0;
    if (crashed()) forget_crash();
    ram->skipped = (uint32_t)skip;
    if (skip)
        o = put(o, "RESTART on the MODS page, or python -m dirtyloader.unit good, loads them again.\n");

    if (!skip) {
        struct fw_file f;
        char *const list = (char *)(SCRATCH + STATUS_SIZE);
        int n = 0;
        if (f_open(&f, "/dirtyloader/active.txt", FW_O_READ)) {
            n = f_read(&f, list, LIST_SIZE - 1);
            fw_file_close(&f);
        }
        if (n < 0) n = 0;
        list[n] = 0;
        for (char *q = list; *q; q++)                 /* a set to load: arm the guard until it has run 10 s */
            if (*q != '\n' && *q != '\r' && *q != ' ') {
                if (*q != '#') { write_file(GUARD_PATH, "ARMD", 4); ram->armed = 1; break; }
                while (*q && *q != '\n') q++;
                if (!*q) break;
            }
        char *p = list;
        while (*p && o < status + STATUS_SIZE - 120) {
            char *line = p;
            while (*p && *p != '\n' && *p != '\r') p++;
            if (*p) *p++ = 0;
            while (*line == ' ') line++;
            if (!*line || *line == '#') continue;
            const struct dl_mod *m = 0;
            uint32_t at = ram->next;
            int err = load_one(line, orders, &m);
            if (ram->nboot < MAX_MODS) {
                char *d = ram->boot[ram->nboot].name;
                uint32_t i = 0;
                for (; line[i] && i < NAME_MAX - 1; i++) d[i] = line[i];
                d[i] = 0;
                ram->boot[ram->nboot++].err = err;
            }
            o = put(o, line);
            if (err) {
                o = put(o, ": E");
                o = put_dec(o, err);
                o = put(o, " ");
                o = put(o, ERRORS[err]);
            } else {
                o = put(o, ": loaded ");
                o = put(o, m->id);
                o = put(o, " ");
                o = put(o, m->version);
                o = put(o, " at ");
                o = put_hex(o, at);
                o = put(o, ", ");
                o = put_dec(o, ram->next - at);
                o = put(o, " bytes, ");
                o = put_dec(o, m->nsubs);
                o = put(o, " hooks");
            }
            o = put(o, "\n");
        }
    }
    /* ev_card_ready: the card is up and the firmware has not used it; mods are loaded, ev_boot comes later. The
       dispatcher does not use ram->table yet (no magic), so core calls the handlers itself. */
    for (uint32_t i = 0; i < ram->count; i++)
        if (ram->table[i].event == 0x0002u && (ram->table[i].flags & FLAG_ENABLED))
            ((void (*)(int))ram->table[i].fn)(1);
    o = put(o, "hooks ");
    o = put_dec(o, ram->count);
    o = put(o, "\n");
    write_file("/dirtyloader/status.txt", status, (uint32_t)(o - status));
}

void core_boot(void)
{
    if (!ram->loaded) {                             /* setup() never reached core_load: flash hooks only */
        uint16_t orders[SLOTS];
        ram->nmods = 0;
        flash_hooks(orders);
    }
    if (!fw_views[FW_VIEW_FREE]) {                  /* the MODS page takes the firmware's free view slot */
        zero(&ram->page_view, sizeof ram->page_view);
        ram->page_view.vt = page_vt;
        fw_views[FW_VIEW_FREE] = &ram->page_view;
    }
    if (FW_VECTORS[FW_AUDIO_VECTOR] != ((uint32_t)core_audio | 1)) {   /* ev_render_in / ev_render_out */
        ram->audio_orig = FW_VECTORS[FW_AUDIO_VECTOR];
        __asm volatile("dsb" ::: "memory");
        FW_VECTORS[FW_AUDIO_VECTOR] = (uint32_t)core_audio | 1;
    }
    {                                               /* ev_audio_out */
        volatile uint32_t *vt = *(volatile uint32_t **)(fw_audio_engine + FW_AUDIO_TAP);
        ram->audio_subs = 0;
        for (uint32_t i = 0; i < ram->count; i++) if (ram->table[i].event == 0x0032u) ram->audio_subs = 1;
        if (vt && vt[0] != ((uint32_t)core_tap | 1)) {
            ram->tap_orig = vt[0];
            vt[0] = (uint32_t)core_tap | 1;
        }
    }
    ram->track_subs = has_subs(EV_TRACK_AUDIO_W);   /* the graph's objects: wrapped only for a subscriber */
    ram->fx_subs = has_subs(EV_FX_AUDIO_W & 0xFFFFu);
    ram->params_subs = has_subs(EV_PARAMS_W);
    if (ram->track_subs) wrap_slot(FW_SLOT_TRACK, &ram->track_orig, (uint32_t)core_track);
    if (ram->fx_subs) {
        wrap_slot(FW_SLOT_MFX, &ram->mfx_orig, (uint32_t)core_mfx);
        wrap_slot(FW_SLOT_DELAY, &ram->delay_orig, (uint32_t)core_delay);
        wrap_slot(FW_SLOT_REVERB, &ram->reverb_orig, (uint32_t)core_reverb);
    }
    if (ram->params_subs) wrap_slot(FW_SLOT_CLOCK, &ram->clock_orig, (uint32_t)core_clock);
    if (has_subs(EV_STEP_EDIT_W)) {                 /* bulk phrase edits */
        ram->snap_phrase = 0xFFFFFFFFu;
        wrap_slot(FW_SLOT_PHRASE_BULK, &ram->bulk_orig, (uint32_t)core_phrase_bulk);
        wrap_slot(FW_SLOT_PHRASE_CELL, &ram->cell_orig, (uint32_t)core_phrase_cell);
    }
    if (FW_VECTORS[3] != ((uint32_t)core_fault | 1)) {   /* ev_crash: HardFault .. UsageFault */
        ram->fault_orig = FW_VECTORS[3];
        ram->in_fault = 0;
        for (int v = 3; v <= 6; v++) FW_VECTORS[v] = (uint32_t)core_fault | 1;
    }
    if (fw_sysex_handler != (uint32_t)core_sysex) {   /* ev_sysex */
        ram->sysex_orig = fw_sysex_handler;
        fw_sysex_handler = (uint32_t)core_sysex;
    }
    ram->booted = 1;                                /* song loads from here on are the user's */
    ram->armed_at = fw_millis;
    ram->api = &api;
    __asm volatile("dsb\n isb" ::: "memory");
    ram->magic = RAM_MAGIC;
}
