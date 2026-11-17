/* SPDX-License-Identifier: GPL-2.0-or-later */
/* core 0.3: load mods from the SD card at boot (docs/LOADER.md).
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

/* ---- layout, shared with dirtyloader/core/builder.py (build_core03_mod) -------------------------------- */
#ifndef CORE_RAM
#error "CORE_RAM, CORE_RAM_END, CORE_FLASH_TABLE, CORE_FLASH_SLOTS come from the builder"
#endif
#define RAM_MAGIC    0x33524C44u       /* "DLR3": the dispatcher uses ram->table only when this is set */
#define RAM_SIG      0x47495344u       /* "DSIG": ram->nmods is from a previous boot of this core */
#define SLOTS        64
#define MAX_MODS     16
#define FLAG_ENABLED 1u

struct hook { uint16_t event, flags; void *fn; };

struct core_ram {
    uint32_t magic;
    uint32_t count;
    struct hook table[SLOTS];
    uint32_t sig;                /* RAM_SIG once core_load has run; ITCM survives a reset, not a power cycle */
    uint32_t loaded;             /* core_load ran this boot */
    uint32_t next;               /* next free byte of the mods' area */
    uint32_t nmods;
    const struct dl_mod *mods[MAX_MODS];
};
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

static int write_file(const char *path, const char *text, uint32_t n)
{
    struct fw_file f;
    if (!f_open(&f, path, FW_O_RDWR | FW_O_CREAT | FW_O_TRUNC)) return 0;
    int ok = f_write(&f, text, n) == (int)n;
    fw_file_close(&f);
    return ok;
}

/* ---- the crash guard ------------------------------------------------------------------------------------------
 * /dirtyloader/guard holds SKIP once a boot with mods crashed; while it does, nothing is loaded. Anything else
 * (or no file) means load. Writing GOOD there (dirtyloader sd does) re-enables the mods. */
#define GUARD_PATH "/dirtyloader/guard"
#define G_SKIP 0x50494B53u   /* "SKIP" */
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

/* Teensyduino's fault handler leaves a record (len = 44, then the fault registers) in RAM and reboots. */
static int crashed(void) { return fw_fault_info[0] == 44u && (fw_fault_info[2] | fw_fault_info[3]); }
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
enum { C_INFO = 1, C_LIST, C_PUT, C_CHECK, C_GET, C_MKDIRS, C_RESTART };
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
static int dl_path(char *out, const uint8_t *name, uint32_t n)
{
    if (!n || n > 63 || name[0] == '/') return 0;
    char *o = put(out, "/dirtyloader/");
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

static int f_seek(struct fw_file *f, uint32_t pos)
{
    if (f->fat) return fw_fat_seek(f->fat, pos);
    if (f->exfat) return fw_exfat_seek(f->exfat, 0, pos);
    return 0;
}

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
        reply(cmd, seq, S_OK, 0, 0);
        uint32_t t = fw_millis;
        while (fw_millis - t < 50) { }                  /* let the reply leave */
        *(volatile uint32_t *)0xE000ED0Cu = 0x05FA0004u;  /* SCB_AIRCR: SYSRESETREQ */
        for (;;) { }
    }
    if (cmd == C_INFO) {
        char *o = (char *)out;
        o = put(o, "dirtyloader core 0.3\nfirmware ");
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
    if (!FW_SD_MOUNTED()) { reply(cmd, seq, S_NOCARD, 0, 0); return; }
    if (cmd == C_MKDIRS) {
        reply(cmd, seq, mkdirs("/dirtyloader/mods") ? S_OK : S_IO, 0, 0);
        return;
    }
    if (cmd == C_LIST) {                                /* names in /dirtyloader/<payload>, one per line */
        struct fw_file dir;
        if (!dl_path(path, p, len) || !f_open(&dir, path, FW_O_READ)) { reply(cmd, seq, S_PATH, 0, 0); return; }
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
        if (len < 5 || len < 5u + p[4] || !dl_path(path, p + 5, p[4])) { reply(cmd, seq, S_PATH, 0, 0); return; }
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
        if (!dl_path(path, p, len) || !f_open(&f, path, FW_O_READ)) { reply(cmd, seq, S_PATH, 0, 0); return; }
        uint32_t size = 0, crc = 0;
        int k;
        while ((k = f_read(&f, out, 512)) > 0) { crc = crc32(crc, out, (uint32_t)k); size += (uint32_t)k; }
        fw_file_close(&f);
        put32(out, size);
        put32(out + 4, crc);
        reply(cmd, seq, k < 0 ? S_IO : S_OK, out, 8);
        return;
    }
    if (cmd == C_GET) {                                 /* offset u32, max u16, name len u8, name -> data */
        if (len < 7 || len < 7u + p[6] || !dl_path(path, p + 7, p[6])) { reply(cmd, seq, S_PATH, 0, 0); return; }
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

static void itcm_writable(void)
{
    volatile uint32_t *rnr = (uint32_t *)0xE000ED98u, *rasr = (uint32_t *)0xE000EDA0u;
    *rnr = 1;                                       /* MPU region 1 = ITCM: read-only -> read/write */
    *rasr = (*rasr & ~(7u << 24)) | (3u << 24);
    __asm volatile("dsb; isb" ::: "memory");
}

void core_early(void)
{
    itcm_writable();
    ram->magic = 0;
    ram->loaded = 0;
}


void core_load(void)
{
    uint16_t orders[SLOTS];
    char *const status = (char *)SCRATCH;
    char *o = status;
    uint32_t had_mods = ram->sig == RAM_SIG ? ram->nmods : 0;   /* from the boot before, if it was a reset */

    ram->sig = RAM_SIG;
    ram->loaded = 1;
    ram->nmods = 0;
    ram->next = AREA_START;
    flash_hooks(orders);
    if (!FW_SD_MOUNTED())
        return;

    o = put(o, "dirtyloader core 0.3\nmods area ");
    o = put_dec(o, AREA_END - AREA_START);
    o = put(o, " bytes at ");
    o = put_hex(o, AREA_START);
    o = put(o, "\n");

    int skip = 0;
    if (crashed() && had_mods) {
        o = put(o, "crash guard: the last boot with mods crashed (pc ");
        o = put_hex(o, fw_fault_info[6]);
        o = put(o, "), so no mods were loaded.\n");
        write_file(GUARD_PATH, "SKIP", 4);
        skip = 1;
    } else if (read_guard() == G_SKIP) {
        o = put(o, "crash guard: guard says SKIP, so no mods were loaded.\n");
        skip = 1;
    }
    if (crashed()) forget_crash();
    if (skip)
        o = put(o, "Write GOOD to /dirtyloader/guard to load them again (dirtyloader sd does it).\n");

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
    __asm volatile("dsb\n isb" ::: "memory");
    ram->magic = RAM_MAGIC;
}
