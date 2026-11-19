/* SPDX-License-Identifier: GPL-2.0-or-later */
/* lfo-sends: four more modulation destinations in every sound engine's list: DRY, MFX SEND, DEL SEND and REV SEND,
 * the instrument's mixer levels, which no engine offers as a destination.
 *
 * They show in INST. MODS > DEST after the stock ones and are picked like them. The stock lists already use 14 or
 * 15 of the 4 bits an instrument keeps a destination in, so this needs core 0.6's extended destinations
 * (docs/MOD-DESTS.md): core keeps the real destination with the song and the instrument, and mod_dest_of gives it.
 *
 * As the stock does for its own destinations, the modulator's output x amount is added to the level, where the
 * full range (00..FF) is 1: an LFO at amount FF sweeps the whole range, from the level the instrument sets. Two
 * modulators on the same level add up. When nothing modulates a level any more it goes back to the instrument's.
 *
 * How: ev_mod_apply sees the modulators on these destinations (audio thread, while the track renders) and keeps
 * their values; ev_track_audio, right after the track rendered and before its strips run, sets the strips' gains
 * the way the firmware's setter does, ramped over the block. Headless 6.6.4A and Model:02 6.6.2A (fw_track_gain
 * finds each track's gain nodes: inside the voice on headless, separate arrays on the Model:02). The page
 * (SYSTEM SETTINGS > MODS (TELOS), RIGHT on its row) shows where the destinations went. */
#include "dl/mod.h"
#include "m8-headless/fw.h"
#include "dl/core.h"

enum { T_DRY, T_MFX, T_DELAY, T_REVERB, TARGETS };
static const char *const dest_names[TARGETS] = { "DRY", "MFX SEND", "DEL SEND", "REV SEND" };
static const uint8_t gain_of_target[TARGETS] = { FW_GAIN_DRY, FW_GAIN_MFX, FW_GAIN_DELAY, FW_GAIN_REVERB };
static const int engines[] = { FW_ENGINE_WAV, FW_ENGINE_MACRO, FW_ENGINE_SAMPLER, FW_ENGINE_FM, FW_ENGINE_HYPER,
                               FW_ENGINE_EXTERNAL };
static const char *const engine_names[FW_ENGINES] = { "FMSYNTH", "HYPERSYNTH", "MACROSYNTH", "SAMPLER", "WAVSYNTH",
                                                      "EXTERNAL", "MIDI OUT" };

static const struct dl_core *core;
static int first_dest[FW_ENGINES];     /* DRY's index in each engine's list (the others follow), 0: not added */
static int added[FW_ENGINES];          /* how many of the four that engine took */

/* audio thread */
static float mod_val[8][4];            /* the last output x amount of each track's modulators on these */
static uint8_t mod_target[8][4];       /* and which level each one moves */
static volatile uint32_t seen[8];      /* which of them reported in this block */
static uint32_t on[8];                 /* the levels this mod moved last block (a bit per target) */
static float base_gain[8][TARGETS];    /* the gain the firmware set */
static float base_v[8][TARGETS];       /* the same as a level, 0..255 */
static float written[8][TARGETS];      /* what this mod wrote last; anything else came from the firmware */
static uint32_t applied;               /* blocks this mod changed a gain in (the page shows it) */

/* the firmware's curve: gain(v) = 0.05797 x 1.02797^(v - 0x80) for the sends, x0.8696 for the main strip; 0 off */
static float curve[256];
#define SEND_MAX 0.97705f
#define DRY_SCALE 0.8696f
#define DRY_MAX 1.67168f

static void curve_init(void)
{
    float g = 0.05797f;
    curve[128] = g;
    for (int v = 129; v < 256; v++) curve[v] = curve[v - 1] * 1.0279734f;
    for (int v = 127; v >= 1; v--) curve[v] = curve[v + 1] / 1.0279734f;
    curve[0] = 0.0f;
}

static float gain_of(float v, int target)
{
    float g;
    if (v <= 0.0f) return 0.0f;
    if (v >= 255.0f) g = curve[255];
    else {
        int i = (int)v;
        float f = v - (float)i;
        g = i ? curve[i] + (curve[i + 1] - curve[i]) * f : curve[1] * f;   /* fades out below level 01 */
    }
    if (target == T_DRY) { g *= DRY_SCALE; return g > DRY_MAX ? DRY_MAX : g; }
    return g > SEND_MAX ? SEND_MAX : g;
}

static float level_of(float g, int target)
{
    if (target == T_DRY) g /= DRY_SCALE;
    if (g <= 0.0f) return 0.0f;
    if (g < curve[1]) return g / curve[1];
    int lo = 1, hi = 255;                           /* curve rises: the last entry <= g */
    while (lo < hi) {
        int mid = (lo + hi + 1) >> 1;
        if (curve[mid] <= g) lo = mid; else hi = mid - 1;
    }
    if (lo >= 255) return 255.0f;
    return (float)lo + (g - curve[lo]) / (curve[lo + 1] - curve[lo]);
}

/* audio thread, while a track renders: a modulator on one of this mod's destinations */
static int on_mod_apply(int d, void *modulator, void *target, int engine)
{
    (void)target;
    if (engine < 0 || engine >= FW_ENGINES || !first_dest[engine]) return 0;
    int j = core->mod_dest_of(modulator, d) - first_dest[engine];
    if (j < 0 || j >= added[engine]) return 0;
    uint8_t *m = (uint8_t *)modulator;
    uint8_t *first = *(uint8_t **)(m + FW_MODULATOR_FIRST);
    uint32_t t = (uint32_t)(first - fw_modulators) / FW_MODULATOR_TRACK;
    uint32_t k = (uint32_t)(m - first) / FW_MODULATOR_SIZE;
    if (first < fw_modulators || t >= 8 || k >= 4) return 1;
    mod_val[t][k] = FW_MOD_OUTPUT(m) * FW_MOD_AMOUNT(m);
    mod_target[t][k] = (uint8_t)j;
    seen[t] |= 1u << k;
    return 1;                                       /* nothing for the stock to do with it */
}

/* audio thread, after track t rendered and before its strips run */
static void on_track_audio(float *left, float *right, int t)
{
    (void)left; (void)right;
    if (t < 0 || t >= 8) return;
    uint32_t s = seen[t];
    seen[t] = 0;
    if (!s && !on[t]) return;
    if (!fw_track_gain(t, FW_GAIN_DRY)) return;     /* not the voice this firmware has there: touch nothing */
    float sum[TARGETS] = { 0 };
    uint32_t now = 0;
    for (uint32_t k = 0; k < 4; k++)
        if (s & (1u << k)) {
            uint32_t j = mod_target[t][k];
            if (j < TARGETS) { sum[j] += mod_val[t][k]; now |= 1u << j; }
        }
    for (int j = 0; j < TARGETS; j++) {
        uint32_t bit = 1u << j;
        if (!((now | on[t]) & bit)) continue;
        uint8_t *node = fw_track_gain(t, gain_of_target[j]);
        float fw = *(volatile float *)(node + 0x38);
        if (!(on[t] & bit) || fw != written[t][j]) {     /* first block, or the firmware set a new level */
            base_gain[t][j] = fw;
            base_v[t][j] = level_of(fw, j);
        }
        float g = (now & bit) ? gain_of(base_v[t][j] + sum[j] * 255.0f, j) : base_gain[t][j];
        fw_gain_set(node, g);
        written[t][j] = g;
    }
    on[t] = now;
    if (now) applied++;
}

/* ---- the page (UI thread): where the destinations went ------------------------------------------------- */
static char *put(char *o, const char *s) { while (*s) *o++ = *s++; return o; }
static char *hex2(char *o, uint32_t v) { *o++ = "0123456789ABCDEF"[v >> 4 & 15]; *o++ = "0123456789ABCDEF"[v & 15]; return o; }
static char *dec(char *o, uint32_t v)
{
    char t[10];
    int n = 0;
    do t[n++] = (char)('0' + v % 10); while (v /= 10);
    while (n) *o++ = t[--n];
    return o;
}
static void line(int r, char *b, char *o)
{
    while (o < b + 34) *o++ = ' ';                  /* columns 34 on are the firmware's */
    *o = 0;
    fw_text(fw_grid, 0, r, b);
}

static void draw(void)
{
    char b[48], *o;
    o = put(b, " IN INST. MODS > DEST:");
    line(5, b, o);
    o = put(b, " DRY, MFX/DEL/REV SEND");
    line(6, b, o);
    o = put(b, " ENGINE        DEST");
    line(8, b, o);
    for (unsigned i = 0; i < sizeof engines / sizeof engines[0]; i++) {
        int e = engines[i];
        o = put(b, " ");
        char *col = o;
        o = put(o, engine_names[e]);
        while (o < col + 14) *o++ = ' ';
        if (added[e] == TARGETS) { o = hex2(o, (uint32_t)first_dest[e]); *o++ = '-'; o = hex2(o, (uint32_t)first_dest[e] + 3); }
        else if (!core || core->version < 0x600) o = put(o, "NEEDS CORE 0.6");
        else { o = put(o, "ADDED "); o = dec(o, (uint32_t)added[e]); o = put(o, " OF 4"); }
        line(9 + (int)i, b, o);
    }
    o = put(b, " BLOCKS MODULATED ");
    o = dec(o, applied);
    line(16, b, o);
    o = put(b, " OPT BACK");
    line(22, b, o);
}

static const struct dl_page page = { "lfo-sends", "LFO SENDS", 0, draw, 0 };

static void on_boot(void)
{
    curve_init();
    core = dl_core();
    if (!core) return;
    core->page_add(&page);
    if (core->version < 0x600) return;              /* four more need core 0.6's extended destinations */
    for (unsigned i = 0; i < sizeof engines / sizeof engines[0]; i++) {
        int e = engines[i];
        for (int j = 0; j < TARGETS; j++) {
            int d = core->mod_dest_add(e, dest_names[j]);
            if (!d) break;
            if (!j) first_dest[e] = d;
            added[e]++;
        }
    }
}

DL_MOD("lfo-sends", "0.2.0", "LFO SENDS: DRY, MFX, DEL and REV SEND as modulation destinations",
       DL_ON(EV_BOOT, 50, on_boot), DL_ON(EV_MOD_APPLY, 50, on_mod_apply), DL_ON(EV_TRACK_AUDIO, 50, on_track_audio));
