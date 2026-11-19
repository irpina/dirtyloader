/* SPDX-License-Identifier: GPL-2.0-or-later */
/* PERF MON: where the M8's time goes, measured with the CPU's cycle counter (DWT CYCCNT).
 *
 *   AUDIO   the audio interrupt (ev_render_in .. ev_render_out) as a share of the block period: the last
 *           second's average, its worst block, and the worst since EDIT
 *   FX OUT  the ev_audio_out handlers (other mods' master-bus DSP, CHAOS CONTROL's say): this mod brackets them
 *           with a handler that runs first (order 0) and one that runs last (order 255)
 *   LOOP    the UI loop: iterations a second, and the longest gap between two (the audio interrupt included):
 *           what a key, the screen and the touch screen wait for
 *   VIS     (Model:02) the visualizer's frames a second, and the time its ev_vis_draw handlers take (the overlay)
 *
 * The page (SYSTEM SETTINGS > MODS, RIGHT on its row, or the Mod Menu) shows them; EDIT clears the worsts. The
 * worsts keep counting while the page is closed: play, then come back and read them. Everything is also in
 * `perf` for a PEEK. The ITCM a mod may use is small next to CHAOS CONTROL on a Model:02, so this stays lean:
 * text on its page only. */
#include "dl/mod.h"
#include "m8-headless/fw.h"                 /* the Model:02 build maps this to m8-model02/fw.h */
#include "dl/core.h"                        /* after fw.h: dl_core() needs its DL_CORE_PTR */

#define CYCCNT (*(volatile uint32_t *)0xE0001004u)

/* the last full second, and the worst since EDIT (cycles unless said) */
static struct {
    uint32_t hz;                        /* cycles a second, measured against fw_millis */
    uint32_t block;                     /* cycles between audio blocks */
    uint32_t load, load_peak, load_max; /* audio interrupt: average %, the worst block %, worst since EDIT */
    uint32_t fx, fx_peak, fx_max;       /* ev_audio_out handlers a block: average, worst, worst since EDIT */
    uint32_t loops, gap, gap_max;       /* UI loops a second; the longest gap; worst since EDIT */
    uint32_t vis, vis_draw, vis_max;    /* visualizer frames a second; the longest ev_vis_draw; worst since EDIT */
    uint32_t scope, vis_avg;            /* a visualizer frame's firmware drawing (from ev_draw, before the frame
                                           refresh, to ev_vis_draw: the eight scopes), and its ev_vis_draw: averages */
} perf;

/* running sums for the second in progress (the audio interrupt adds, the UI thread rolls them up) */
static volatile uint32_t a_in, a_last, a_busy, a_period, a_peak, a_blocks;
static volatile uint32_t f_in, f_sum, f_peak;
static uint32_t t_last, loops, gap, vis_n, v_peak, s_sum, v_sum, sec_cyc, sec_ms;

static void render_in(void)
{
    uint32_t now = CYCCNT;
    if (a_last) a_period += now - a_last;
    a_last = a_in = now;
}
static void render_out(void)
{
    uint32_t busy = CYCCNT - a_in;
    a_busy += busy;
    if (busy > a_peak) a_peak = busy;
    a_blocks++;
}
static int fx_first(float *l, float *r, int n) { (void)l; (void)r; (void)n; f_in = CYCCNT; return 0; }
static int fx_last(float *l, float *r, int n)
{
    (void)l; (void)r; (void)n;
    uint32_t d = CYCCNT - f_in;
    f_sum += d;
    if (d > f_peak) f_peak = d;
    return 0;
}

static uint32_t max_(uint32_t a, uint32_t b) { return a > b ? a : b; }
static void tick(void)
{
    uint32_t now = CYCCNT;
    if (t_last && now - t_last > gap) gap = now - t_last;
    t_last = now;
    loops++;
    uint32_t ms = fw_millis;
    if (ms - sec_ms < 1000) return;
    /* a second: roll it up */
    perf.hz = (now - sec_cyc) / (ms - sec_ms) * 1000u;
    sec_cyc = now; sec_ms = ms;
    uint32_t n = a_blocks, busy = a_busy, period = a_period, peak = a_peak, fs = f_sum, fp = f_peak;
    a_blocks = a_busy = a_period = a_peak = f_sum = f_peak = 0;
    if (n > 1 && period) {
        perf.block = period / (n - 1);
        perf.load = busy / (period / 100u + 1);
        perf.load_peak = peak / (perf.block / 100u + 1);
        perf.fx = fs / n;
    }
    perf.fx_peak = fp;
    perf.loops = loops; perf.gap = gap;
    perf.vis = vis_n; perf.vis_draw = v_peak;
    perf.scope = vis_n ? s_sum / vis_n : 0; perf.vis_avg = vis_n ? v_sum / vis_n : 0;
    loops = gap = vis_n = v_peak = s_sum = v_sum = 0;
    perf.load_max = max_(perf.load_max, perf.load_peak);
    perf.fx_max = max_(perf.fx_max, perf.fx_peak);
    perf.gap_max = max_(perf.gap_max, perf.gap);
    perf.vis_max = max_(perf.vis_max, perf.vis_draw);
}

#ifdef fw_rect
static uint32_t v_in, t_draw;
static void draw_start(void *ui) { (void)ui; t_draw = CYCCNT; }    /* ev_draw: just before each frame refresh */
static void vis_first(void *g) { (void)g; v_in = CYCCNT; vis_n++; s_sum += v_in - t_draw; }
static void vis_last(void *g) { (void)g; uint32_t d = CYCCNT - v_in; v_sum += d; if (d > v_peak) v_peak = d; }
#endif

/* ---- the page ------------------------------------------------------------------------------------------- */
static char *put(char *o, const char *s) { while (*s) *o++ = *s++; return o; }
static char *dec(char *o, uint32_t v)
{
    char t[10];
    int n = 0;
    do t[n++] = (char)('0' + v % 10); while (v /= 10);
    while (n) *o++ = t[--n];
    return o;
}
static uint32_t us(uint32_t cyc) { uint32_t m = perf.hz / 1000000u; return m ? cyc / m : 0; }
/* a row: label, then (value, unit) pairs; columns 34 on are the firmware's */
static void row(int r, const char *label, const uint32_t *v, const char *const *units, int n)
{
    char b[48], *o = put(b, label);
    for (int i = 0; i < n; i++) { *o++ = ' '; o = dec(o, v[i]); o = put(o, units[i]); }
    while (o < b + 34) *o++ = ' ';
    b[34] = 0;
    fw_text(fw_grid, 0, r, b);
}
static const char *const u_load[] = { "% NOW", "% PEAK", "% MAX" };
static const char *const u_us[] = { "US NOW", "US MAX" };
static const char *const u_loop[] = { "/S", "US GAP", "US MAX" };
#ifdef fw_rect
static const char *const u_vis[] = { "/S", "US SCOPE", "US OVL" };
#endif
static void draw(void)
{
    uint32_t v[3];
    v[0] = perf.load; v[1] = perf.load_peak; v[2] = perf.load_max;  row(5, " AUDIO ", v, u_load, 3);
    v[0] = us(perf.fx); v[1] = us(perf.fx_max);                      row(6, " FX OUT", v, u_us, 2);
    v[0] = perf.loops; v[1] = us(perf.gap); v[2] = us(perf.gap_max);  row(7, " LOOP  ", v, u_loop, 3);
#ifdef fw_rect
    v[0] = perf.vis; v[1] = us(perf.scope); v[2] = us(perf.vis_avg);  row(8, " VIS", v, u_vis, 3);
#endif
    fw_text(fw_grid, 0, 10, " EDIT CLEARS MAX");
}
static int key(int action)
{
    if (action != FW_KEY_EDIT) return 0;
    perf.load_max = perf.fx_max = perf.gap_max = perf.vis_max = 0;
    return 1;
}
static const struct dl_page page = { "perf-mon", "PERF MON", 0, draw, key };
static void boot(void)
{
    const struct dl_core *c = dl_core();
    if (c) c->page_add(&page);
    sec_cyc = CYCCNT; sec_ms = fw_millis;
}

#ifdef fw_rect
#define VIS_SUBS , DL_ON(EV_VIS_DRAW, 0, vis_first), DL_ON(EV_VIS_DRAW, 255, vis_last), \
                 DL_ON(EV_DRAW, 255, draw_start)
#else
#define VIS_SUBS
#endif
DL_MOD("perf-mon", "0.1.1", "PERF MON: timings",
       DL_ON(EV_BOOT, 50, boot), DL_ON(EV_TICK, 0, tick), DL_ON(EV_RENDER_IN, 0, render_in),
       DL_ON(EV_RENDER_OUT, 255, render_out), DL_ON(EV_AUDIO_OUT, 0, fx_first), DL_ON(EV_AUDIO_OUT, 255, fx_last)
       VIS_SUBS);
