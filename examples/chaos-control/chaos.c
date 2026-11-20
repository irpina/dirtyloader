/* SPDX-License-Identifier: GPL-2.0-or-later */
/* CHAOS CONTROL: an X/Y performance pad on the M8's master output, in the spirit of a modern Kaoss pad.
 *
 * Eight effects, one at a time, each with two axes:
 *   FILTER     X cutoff (left of centre low-pass, right of centre high-pass, centre off)   Y resonance
 *   REPEAT     X slice length (1/4 .. 1/64 beat, tempo-synced)  Y pitch of the repeats (half to double speed)
 *   TAPE STOP  X stop time                                       Y how far it slows (stop .. half speed)
 *   CRUSH      X sample rate (44.1 kHz .. ~900 Hz)               Y bit depth (12 .. 2, against the music's peak)
 *   GATE       X rate (1 .. 1/16 beat, tempo-synced)              Y depth
 *   ECHO       X time (tempo-synced, ping-pong)                  Y feedback; lifting off lets the tail ring out
 *   JET        X flanger sweep (manual)                          Y feedback
 *   PITCH      X -12 .. +12 semitones                            Y mix
 * and four that follow the finger's movement, not only where it is:
 *   SCRATCH    the pad is a record: X is the platter, so dragging scrubs the last 223 ms back and forth at the
 *              finger's speed (still: silence); Y the crossfader (bottom: cut)
 *   GRAIN      the audio freezes into grains: X where in it, Y grain size (10 .. 100 ms); moving faster scatters
 *              the grains' place and pitch (still: a smooth frozen drone)
 *   SWIRL      the finger is where the sound sits around your head: left / right pans it, the bottom half is
 *              behind you (duller), and moving towards or away bends its pitch (Doppler)
 *   WHOOSH     a noise sweep played by motion: how fast the finger moves is how loud it is; X its band, Y the
 *              resonance; the music ducks under it
 *
 * CHAOS mode is the M8's visualizer. On the Model:02 core's MOD LOADER opens it (all four directions, then EDIT on
 * this mod's card; core took the chord for the MOD LOADER). On the Model:02 that is the firmware's own
 * visualizer (it toggles ui + 0); CHAOS is live while it shows, and the touch screen is the pad. Headless firmware
 * has no visualizer: there, all four directions open CHAOS CONTROL's own screen (and close it again). Outside CHAOS
 * mode nothing engages: touching, MIDI and HOLD only play the pad while it is on, and leaving it releases them.
 *
 * Touching the pad engages the effect; letting go releases it (HOLD keeps it engaged until the next touch). The
 * effect fades in and out over a few milliseconds, so engaging never clicks.
 *
 * Ways to play it, in CHAOS mode:
 *   - the Model:02's touch screen (core's ev_touch): the whole visualizer is the pad while CHAOS TOUCH is ON, with
 *     an overlay on it (core's ev_vis_draw): the effect, the motion meter, HOLD and the finger (CHAOS OVERLAY)
 *   - CHAOS CONTROL's screen (all four directions on headless; on any unit also SYSTEM SETTINGS > MODS (TELOS),
 *     RIGHT on its row, or the Mod Menu): arrows move the cursor over the pad, EDIT engages / releases,
 *     SHIFT+LEFT / SHIFT+RIGHT change the effect, SHIFT+UP turns HOLD on / off, OPT (or all four directions) leaves
 *   - MIDI: CC 12 X, CC 13 Y, CC 14 touch (64 and up: on), CC 15 the effect (0-127 across the eight), any channel
 *
 * The audio runs in ev_audio_out on the master output (64-frame float blocks): what USB and the headphones hear.
 * REPEAT, TAPE STOP, ECHO, JET and PITCH need a buffer: 9856 stereo frames (223 ms) of 16-bit audio from core's
 * ram_claim (core 0.6). Tempo comes from the firmware (fw_bpm) and beat position from the sequencer's ticks
 * (192 a beat). Headless 6.6.4A (m8-headless/fw.h). */
#include "dl/mod.h"
#include "m8-headless/fw.h"
#include "dl/core.h"
#include "dl/pixui.h"

#define FS          44100.0f
/* stereo frames of history: 9,856 (223 ms), or less where core's spare RAM can't hold that and FXPAD's cells too
   (whole 64-frame steps; ram_claim rounds to 8). The Model:02's 6.6.4A has 512 bytes less than 6.6.2A: 9,728,
   221 ms. Before this, its ring took the room and FXPAD's cells didn't fit: no FXPAD, and m8c's stream stayed
   paused in the visualizer. */
#if defined(fw_rect) && defined(FW_SPARE_RAM)
#define RING_FIT    ((((FW_SPARE_RAM_END - FW_SPARE_RAM) - 8u - 38u * 38u) / 4u) & ~63u)
#define RING        (RING_FIT < 9856u ? RING_FIT : 9856u)
#else
#define RING        9856u
#endif
#define TPB         192u                    /* sequencer ticks a beat (measured: 384 a second at 120 BPM) */

enum { FX_FILTER, FX_REPEAT, FX_TAPE, FX_CRUSH, FX_GATE, FX_ECHO, FX_JET, FX_PITCH,
       FX_SCRATCH, FX_GRAIN, FX_SWIRL, FX_WHOOSH, NFX };
static const char *const fx_names[NFX] = { "FILTER", "REPEAT", "TAPE STOP", "CRUSH", "GATE", "ECHO", "JET", "PITCH",
                                           "SCRATCH", "GRAIN", "SWIRL", "WHOOSH" };
static const char *const x_names[NFX] = { "CUTOFF", "LENGTH", "TIME", "RATE", "RATE", "TIME", "SWEEP", "PITCH",
                                          "PLATTER", "PLACE", "PAN", "BAND" };
static const char *const y_names[NFX] = { "RESO", "PITCH", "DEPTH", "BITS", "DEPTH", "FEEDBACK", "FEEDBACK", "MIX",
                                          "FADER", "SIZE", "FRONT", "RESO" };

/* ---- controls (UI thread and MIDI write, the audio thread reads) ----------------------------------------- */
static volatile float ctl_x = 0.5f, ctl_y = 0.5f;
static volatile uint8_t touch_keys, touch_midi, touch_screen;   /* each source's "finger down" */
static volatile uint8_t latched;                                  /* HOLD: engaged after the finger lifted */
static uint8_t fx_sel;                                            /* a setting: kept in settings.txt */
static uint8_t hold;
#ifdef fw_touch
static uint8_t touch_on = 1;                                      /* the touch screen plays the pad (Model:02) */
#endif
static const char *const off_on[] = { "OFF", "ON" };
static const struct dl_setting set_fx = { "CHAOS FX", &fx_sel, 0, NFX - 1, fx_names, 0 };
static const struct dl_setting set_hold = { "CHAOS HOLD", &hold, 0, 1, off_on, 0 };
#ifdef fw_touch
static const struct dl_setting set_touch = { "CHAOS TOUCH", &touch_on, 0, 1, off_on, 0 };
#endif
#ifdef fw_rect
static uint8_t overlay_on = 1;                                    /* draw over the Model:02's visualizer */
static const struct dl_setting set_overlay = { "CHAOS OVERLAY", &overlay_on, 0, 1, off_on, 0 };
/* The visualizer's frame rate in CHAOS mode. With every track playing its eight scopes take 11-21 ms a frame
 * (PERF MON), and the firmware starts one every 15 ms, so the UI loop (the touch screen, the keys) barely runs. */
static uint8_t vis_rate = 1;
static const char *const rate_names[] = { "60", "30", "20" };
static const uint8_t rate_ms[] = { 0, 33, 50 };
static const struct dl_setting set_rate = { "CHAOS VIS FPS", &vis_rate, 0, 2, rate_names, 0 };
/* CHAOS VIS: what the visualizer shows in CHAOS mode. STOCK is the firmware's eight scopes (11-21 ms a frame with
 * every track playing); METERS skips them (core's ev_vis_scope) and draws a level bar per track, only the part
 * that moved. */
static uint8_t vis_style = 1;
static uint8_t *fp_cell;                            /* each cell's colour as drawn: FP_CELLS bytes from core's
                                                       ram_claim (no ITCM); 0: none, and CHAOS VIS acts as STOCK */
#define FXPAD_ON (vis_style && fp_cell)
#define VIS_STYLES 4
static const char *const style_names[VIS_STYLES] = { "STOCK", "SWIRL", "RIPPLE", "BARS" };
static const struct dl_setting set_style = { "CHAOS VIS", &vis_style, 0, VIS_STYLES - 1, style_names, 0 };
static int fxpad_touch(float tx, float ty, int down);   /* the FXPAD screen's own touch handling (below) */
static volatile uint8_t fp_full_req;                /* FULLSCREEN on / off on FXPAD's next frame (its button, CC 17) */
static volatile float out_peak;                     /* the master's peak since FXPAD's last frame (audio thread) */
#endif
static const struct dl_core *core;

static volatile uint8_t page_shown;                 /* CHAOS CONTROL's own screen is up */
#ifdef fw_input_router
static volatile uint8_t vis_toggle;                 /* MIDI CC 16 asked for the visualizer on / off */
#endif
#define ACTION_ALL_FOUR 0xE4                            /* UP + DOWN + LEFT + RIGHT: the visualizer */
/* CHAOS mode: the firmware's visualizer (Model:02), or this mod's screen */
static int chaos_mode(void)
{
#ifdef FW_UI_VISUALIZER
    if (fw_ui[FW_UI_VISUALIZER]) return 1;
#endif
    return page_shown;
}
static int engaged(void) { return chaos_mode() && (touch_keys || touch_midi || touch_screen || latched); }
/* a finger came down (any source): with HOLD a second tap releases */
static void finger(volatile uint8_t *src, int down)
{
    int was = engaged();
    if (down && hold && latched) { latched = 0; *src = 0; return; }   /* tap again: release */
    *src = (uint8_t)down;
    if (!down && hold && was) latched = 1;
}

/* ---- small maths, no libm -------------------------------------------------------------------------------- */
static float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }
static float absf(float v) { return v < 0 ? -v : v; }
static float floorf_(float v) { int i = (int)v; return (float)(v < (float)i ? i - 1 : i); }
static float exp2f_(float v)                        /* 2^v, ~1e-4 relative */
{
    float fl = floorf_(v), f = v - fl;
    float p = 1.0f + f * (0.6931472f + f * (0.2402265f + f * (0.0555041f + f * (0.0096181f + f * 0.0013334f))));
    int e = (int)fl;
    union { float f; uint32_t u; } r = { p };
    r.u += (uint32_t)e << 23;
    return r.f;
}
static float sqrtf_(float x) { float r; __asm__("vsqrt.f32 %0, %1" : "=t"(r) : "t"(x)); return r; }
__attribute__((unused)) static float log2f_(float x)   /* x > 0; ~0.01 */
{
    union { float f; uint32_t u; } v = { x };
    float e = (float)((int)(v.u >> 23 & 0xFF) - 127);
    v.u = (v.u & 0x7FFFFFu) | 0x3F800000u;           /* the mantissa, 1..2 */
    return e - 1.674873f + v.f * (2.024658f - 0.344845f * v.f);
}
static uint32_t rng = 0x12345678u;
static float rand01(void) { rng = rng * 1664525u + 1013904223u; return (float)(rng >> 8) * (1.0f / 16777216.0f); }
static float tanf_(float x)                         /* Pade, good to ~1.4 rad (16.6 kHz at 44.1) */
{
    float x2 = x * x;
    return x * (135135.0f - x2 * (17325.0f - x2 * (378.0f - x2))) / (135135.0f - x2 * (62370.0f - x2 * (3150.0f - 28.0f * x2)));
}

/* ---- the history ring: 16-bit stereo ----------------------------------------------------------------------- */
static int16_t (*ring)[2];                          /* RING frames, from core's ram_claim; 0: none */
static uint32_t widx;                               /* frames written (wraps mod RING by masking with % ) */
static int16_t to16(float v) { v = clampf(v, -1.0f, 1.0f) * 32767.0f; return (int16_t)(v < 0 ? v - 0.5f : v + 0.5f); }
static void put_frame(float l, float r)
{
    uint32_t i = widx % RING;
    ring[i][0] = to16(l);
    ring[i][1] = to16(r);
    widx++;
}
/* the frame `back` frames before the newest (fractional: linear) */
static void get_back(float back, float *l, float *r)
{
    if (back < 1.0f) back = 1.0f;
    if (back > (float)(RING - 2)) back = (float)(RING - 2);
    float pos = (float)widx - back;
    int32_t i = (int32_t)floorf_(pos);
    float f = pos - (float)i;
    uint32_t a = (uint32_t)i % RING, b = (uint32_t)(i + 1) % RING;
    *l = ((float)ring[a][0] * (1.0f - f) + (float)ring[b][0] * f) * (1.0f / 32768.0f);
    *r = ((float)ring[a][1] * (1.0f - f) + (float)ring[b][1] * f) * (1.0f / 32768.0f);
}
static void ring_clear(void) { if (ring) for (uint32_t i = 0; i < RING; i++) ring[i][0] = ring[i][1] = 0; }

/* ---- timing ------------------------------------------------------------------------------------------------ */
static volatile uint32_t ticks;                     /* sequencer ticks since play */
static float beat;                                  /* beats, the audio thread's own count, re-synced on ticks */
static uint32_t ticks_seen;
static float bpm(void) { float b = fw_bpm; return b >= 20.0f && b <= 999.0f ? b : 120.0f; }
static float beat_frames(void) { return FS * 60.0f / bpm(); }
/* the longest of `beats` (a power-of-two fraction) that fits the ring */
static float synced_frames(float beats)
{
    float f = beat_frames() * beats;
    while (f > (float)(RING - 256)) f *= 0.5f;
    return f < 64.0f ? 64.0f : f;
}

/* ---- effect state -------------------------------------------------------------------------------------------- */
static uint8_t cur_fx = 0xFF;                       /* the effect the audio thread runs */
static float xs = 0.5f, ys = 0.5f;                  /* smoothed controls */
static float wet;                                   /* 0 dry .. 1 the effect */
static uint8_t was_on;
/* FILTER */
static float f_ic1[2], f_ic2[2];
/* REPEAT */
static uint32_t rp_freeze;                          /* widx when the slice froze */
static float rp_len, rp_ph;
/* TAPE STOP */
static float tp_back, tp_rate;
/* CRUSH */
static float cr_hold[2], cr_cnt, cr_peak = 0.01f;
/* GATE */
static float gt_gain = 1.0f;
/* ECHO */
static float ec_lp[2];
/* JET */
static float jt_d = 100.0f;
/* PITCH */
static float pt_ph;
/* the finger's movement: pad widths a second, smoothed */
static float mx_prev = 0.5f, my_prev = 0.5f, speed;
static uint32_t motion;                             /* the page's meter: 0..10 */
/* SCRATCH */
static float sc_back, sc_dc_x[2], sc_dc_y[2], sc_gain;
/* GRAIN */
static float gr_ph[2], gr_start[2], gr_rate[2];
/* SWIRL */
static float sw_px = 0.5f, sw_py = 0.5f, sw_lp[2];
/* WHOOSH */
static float wh_ic1[2], wh_ic2[2], wh_peak = 0.01f;

static void fx_reset(void)
{
    f_ic1[0] = f_ic1[1] = f_ic2[0] = f_ic2[1] = 0;
    rp_ph = 0;
    tp_back = 1.0f; tp_rate = 1.0f;
    cr_cnt = 0; cr_hold[0] = cr_hold[1] = 0; cr_peak = 0.01f;
    gt_gain = 1.0f;
    ec_lp[0] = ec_lp[1] = 0;
    pt_ph = 0;
    sc_dc_x[0] = sc_dc_x[1] = sc_dc_y[0] = sc_dc_y[1] = 0; sc_gain = 0;
    gr_ph[0] = 0; gr_ph[1] = 0; gr_start[0] = gr_start[1] = 1000; gr_rate[0] = gr_rate[1] = 1;
    sw_lp[0] = sw_lp[1] = 0;
    wh_ic1[0] = wh_ic1[1] = wh_ic2[0] = wh_ic2[1] = 0;
    ring_clear();
}

/* REPEAT's slice: 1/4 .. 1/64 beat from X (five steps) */
static float repeat_len(float x)
{
    static const float beats[5] = { 0.25f, 0.125f, 0.0625f, 0.03125f, 0.015625f };
    int i = (int)(x * 4.999f);
    return synced_frames(beats[i]);
}

/* ---- the audio: the master output, in place --------------------------------------------------------------- */
static uint32_t blocks_on;                          /* blocks the effect was audible in (the page shows it) */
static int on_audio_out(float *L, float *R, int n)
{
    uint8_t fx = fx_sel < NFX ? fx_sel : 0;
    int on = engaged();
    float tx = ctl_x, ty = ctl_y;
    xs += (tx - xs) * 0.25f;
    ys += (ty - ys) * 0.25f;
    if (fx != cur_fx) { cur_fx = fx; fx_reset(); wet = 0; }
    int needs_ring = fx == FX_REPEAT || fx == FX_TAPE || fx == FX_ECHO || fx == FX_JET || fx == FX_PITCH
                     || fx == FX_SCRATCH || fx == FX_GRAIN || fx == FX_SWIRL;
    int freezes = fx == FX_REPEAT || fx == FX_SCRATCH || fx == FX_GRAIN;   /* hold the history while engaged */

    /* the finger's movement this block, in pad widths a second */
    {
        float ddx = tx - mx_prev, ddy = ty - my_prev;
        mx_prev = tx; my_prev = ty;
        float v = sqrtf_(ddx * ddx + ddy * ddy) * (FS / (float)n);
        speed += (v - speed) * (v > speed ? 0.3f : 0.04f);   /* rises fast, falls over ~30 ms */
        float m = speed * 2.5f;
        motion = (uint32_t)(m > 10 ? 10 : m);
    }
    float speed01 = clampf(speed * 0.35f, 0, 1);
    if (needs_ring && !ring) return 0;

    /* timing: re-sync to the sequencer when it ticked, else run free at the tempo */
    uint32_t tk = ticks;
    if (tk != ticks_seen) { ticks_seen = tk; beat = (float)tk / (float)TPB; }
    float dbeat = bpm() / (60.0f * FS);

    /* engaging: per-effect starts */
    if (on && !was_on) {
        if (fx == FX_REPEAT) { rp_freeze = widx; rp_len = repeat_len(xs); rp_ph = 0; }
        if (fx == FX_TAPE) { tp_back = 1.0f; tp_rate = 1.0f; }
        if (fx == FX_SCRATCH) { sc_back = 64.0f + (1.0f - tx) * (float)(RING - 1024); sc_gain = 0; }
        if (fx == FX_GRAIN) { gr_ph[0] = 0; gr_ph[1] = 0.5f; gr_start[0] = gr_start[1] = 0; }
        if (freezes) rp_freeze = widx;
    }
    was_on = (uint8_t)on;
    float wet_to = on ? 1.0f : 0.0f;
    float wet_step = 1.0f / (0.006f * FS);          /* 6 ms fades */

    /* per-block parameters */
    float a1 = 0, a2 = 0, a3 = 0, k = 0;
    int f_mode = 0;                                 /* 0 off, 1 low-pass, 2 high-pass */
    if (fx == FX_FILTER) {
        float fc = 0;
        if (xs < 0.45f) { f_mode = 1; fc = 80.0f * exp2f_(xs / 0.45f * 7.966f); }          /* 80 Hz .. 20 kHz */
        else if (xs > 0.55f) { f_mode = 2; fc = 20.0f * exp2f_((xs - 0.55f) / 0.45f * 8.644f); }   /* 20 Hz .. 8 kHz */
        fc = clampf(fc, 20.0f, 16500.0f);
        float g = tanf_(3.14159265f * fc / FS), q = 0.6f + ys * ys * 14.0f;
        k = 1.0f / q;
        a1 = 1.0f / (1.0f + g * (g + k)); a2 = g * a1; a3 = g * a2;
    }
    float rp_rate = 1.0f;
    if (fx == FX_REPEAT) {
        float d = ys - 0.5f;
        rp_rate = absf(d) < 0.05f ? 1.0f : exp2f_(d * 2.0f);
        float want = repeat_len(xs);
        if (on && want != rp_len) { rp_len = want; if (rp_ph >= rp_len) rp_ph = 0; }
    }
    float tp_min = ys * 0.5f, tp_step = 0;
    if (fx == FX_TAPE) tp_step = (1.0f - tp_min) / ((0.08f + xs * 0.38f) * FS);
    float cr_n = 1.0f, cr_q = 32768.0f;
    if (fx == FX_CRUSH) { cr_n = exp2f_(xs * 5.6f); cr_q = exp2f_(11.0f - ys * 10.0f); }   /* 12 .. 2 bits */
    float gt_steps = 1.0f, gt_depth = 0;
    if (fx == FX_GATE) { static const float st[5] = { 1, 2, 4, 8, 16 }; gt_steps = st[(int)(xs * 4.999f)]; gt_depth = ys; }
    float ec_d = 0, ec_fb = 0;
    if (fx == FX_ECHO) {
        static const float bt[4] = { 0.125f, 0.25f, 0.375f, 0.5f };
        float b = bt[(int)(xs * 3.999f)];
        ec_d = beat_frames() * b;
        while (ec_d > (float)(RING - 8)) ec_d *= 0.5f;
        ec_fb = ys * 0.92f;
    }
    float jt_target = 0, jt_fb = 0;
    if (fx == FX_JET) { jt_target = 13.0f + xs * xs * 400.0f; jt_fb = ys * 0.9f; }   /* 0.3 .. 9.4 ms */
    float pt_rate = 1.0f, pt_mix = 0;
    if (fx == FX_PITCH) {
        int semis = (int)((xs - 0.5f) * 24.0f + (xs >= 0.5f ? 0.5f : -0.5f));
        pt_rate = exp2f_((float)semis / 12.0f);
        pt_mix = ys;
    }
    const float W = 2048.0f;                        /* PITCH's window: 46 ms */
    const float span = (float)(RING - 1024);        /* SCRATCH's platter and GRAIN's field */
    float sc_from = sc_back, sc_to = 64.0f + (1.0f - tx) * span;   /* the platter follows the finger itself */
    float sc_open = clampf((ty - 0.1f) * 4.0f, 0, 1);              /* the crossfader: the bottom tenth cuts */
    float gr_size = 441.0f + ys * 3969.0f;          /* 10 .. 100 ms */
    float sw_tx = tx, sw_ty = ty;
    float wh_a1 = 0, wh_a2 = 0, wh_a3 = 0, wh_k = 0, wh_lvl = 0;
    if (fx == FX_WHOOSH) {
        float fc = clampf(150.0f * exp2f_(xs * 6.7f), 60.0f, 16000.0f);   /* 150 Hz .. 15 kHz */
        float g = tanf_(3.14159265f * fc / FS);
        wh_k = 1.0f / (0.7f + ys * ys * 12.0f);
        wh_a1 = 1.0f / (1.0f + g * (g + wh_k)); wh_a2 = g * wh_a1; wh_a3 = g * wh_a2;
        wh_lvl = speed01 * speed01 * 3.0f;
    }

    for (int i = 0; i < n; i++) {
        float dl = L[i], dr = R[i], ol = dl, orr = dr;
        if (wet < wet_to) { wet += wet_step; if (wet > 1) wet = 1; }
        else if (wet > wet_to) { wet -= wet_step; if (wet < 0) wet = 0; }
        switch (fx) {
        case FX_FILTER:
            if (f_mode) {
                float in[2] = { dl, dr }, out[2];
                for (int c = 0; c < 2; c++) {
                    float v3 = in[c] - f_ic2[c];
                    float v1 = a1 * f_ic1[c] + a2 * v3;
                    float v2 = f_ic2[c] + a2 * f_ic1[c] + a3 * v3;
                    f_ic1[c] = 2 * v1 - f_ic1[c];
                    f_ic2[c] = 2 * v2 - f_ic2[c];
                    out[c] = f_mode == 1 ? v2 : in[c] - k * v1 - v2;
                }
                ol = out[0]; orr = out[1];
            }
            break;
        case FX_REPEAT:
            if (on || wet > 0) {
                /* the slice ends at the freeze point: play it from its start, again and again */
                float back = (float)(widx - rp_freeze) + rp_len - rp_ph;
                get_back(back, &ol, &orr);
                float edge = rp_ph < 64.0f ? rp_ph / 64.0f : (rp_len - rp_ph < 64.0f ? (rp_len - rp_ph) / 64.0f : 1.0f);
                ol *= edge; orr *= edge;
                rp_ph += rp_rate;
                if (rp_ph >= rp_len) rp_ph -= rp_len;
            }
            break;
        case FX_TAPE:
            if (on) {
                tp_rate -= tp_step;
                if (tp_rate < tp_min) tp_rate = tp_min;
                tp_back += 1.0f - tp_rate;          /* the read head falls behind the live audio */
                get_back(tp_back, &ol, &orr);
                float lvl = tp_min > 0 ? 1.0f : tp_rate * 4.0f;   /* a full stop fades to silence, no DC */
                if (lvl > 1) lvl = 1;
                ol *= lvl; orr *= lvl;
            } else { tp_rate = 1.0f; tp_back = 1.0f; }
            break;
        case FX_CRUSH: {
            /* sample and hold, then quantise against the music's own peak: the bits bite at any level */
            float a = absf(dl) > absf(dr) ? absf(dl) : absf(dr);
            cr_peak = a > cr_peak ? a : cr_peak * 0.99995f;
            if (cr_peak < 0.001f) cr_peak = 0.001f;
            if (cr_cnt <= 0) { cr_hold[0] = dl; cr_hold[1] = dr; cr_cnt += cr_n; }
            cr_cnt -= 1.0f;
            float sc = cr_q / cr_peak;
            ol = floorf_(cr_hold[0] * sc + 0.5f) / sc;
            orr = floorf_(cr_hold[1] * sc + 0.5f) / sc;
            break;
        }
        case FX_GATE: {
            float ph = beat * gt_steps;
            ph -= floorf_(ph);
            float g = ph < 0.5f ? 1.0f : 1.0f - gt_depth;
            gt_gain += (g - gt_gain) * 0.02f;       /* ~1 ms edges */
            ol = dl * gt_gain; orr = dr * gt_gain;
            break;
        }
        case FX_ECHO: {
            /* ping-pong: the dry mono goes into the left line; each repeat crosses sides; damped */
            float el, er;
            get_back(ec_d, &el, &er);
            ec_lp[0] += (el - ec_lp[0]) * 0.45f;
            ec_lp[1] += (er - ec_lp[1]) * 0.45f;
            float send = wet;                       /* lifting off stops the send; the tail rings out */
            put_frame((dl + dr) * 0.5f * send + ec_lp[1] * ec_fb, ec_lp[0] * ec_fb);
            L[i] = dl + el * 0.8f; R[i] = dr + er * 0.8f;
            beat += dbeat;
            continue;                               /* the echo always plays: dry plus its tail */
        }
        case FX_JET: {
            jt_d += (jt_target - jt_d) * 0.002f;
            float el, er;
            get_back(jt_d, &el, &er);
            put_frame(dl + el * jt_fb, dr + er * jt_fb);
            ol = (dl + el) * 0.6f; orr = (dr + er) * 0.6f;
            L[i] = dl + (ol - dl) * wet; R[i] = dr + (orr - dr) * wet;
            beat += dbeat;
            continue;
        }
        case FX_SCRATCH: {
            /* the read head is the platter: where the finger is, sample by sample between blocks */
            float back = sc_from + (sc_to - sc_from) * (float)(i + 1) / (float)n;
            float sl, sr;
            get_back(back, &sl, &sr);
            float in[2] = { sl, sr }, out[2];
            for (int c = 0; c < 2; c++) {           /* a still platter holds one sample: block the DC */
                out[c] = in[c] - sc_dc_x[c] + 0.995f * sc_dc_y[c];
                sc_dc_x[c] = in[c]; sc_dc_y[c] = out[c];
            }
            sc_gain += (sc_open - sc_gain) * 0.01f;
            ol = out[0] * sc_gain; orr = out[1] * sc_gain;
            break;
        }
        case FX_GRAIN: {
            /* two grains half a grain apart, triangle windows that add to one; each new grain starts where the
               finger points, scattered (place and pitch) by how fast it moves */
            float gl = 0, gr = 0;
            for (int v = 0; v < 2; v++) {
                if (gr_ph[v] >= 1.0f || gr_start[v] <= 0) {
                    if (gr_ph[v] >= 1.0f) gr_ph[v] -= 1.0f;
                    float jit = (rand01() - 0.5f) * speed01 * span * 0.5f;
                    gr_start[v] = clampf(64.0f + (1.0f - xs) * span + gr_size * 2.0f + jit, gr_size * 2.5f, (float)(RING - 64));
                    gr_rate[v] = exp2f_((rand01() - 0.5f) * speed01 * 1.5f);
                }
                float w = 1.0f - absf(2.0f * gr_ph[v] - 1.0f);
                float l, r;
                get_back(gr_start[v] - gr_ph[v] * gr_size * gr_rate[v], &l, &r);
                gl += l * w; gr += r * w;
                gr_ph[v] += 1.0f / gr_size;
            }
            ol = gl; orr = gr;
            break;
        }
        case FX_SWIRL: {
            /* a source at the finger, ears either side of the centre: each ear hears it late by its distance
               (moving gives Doppler) and softer with distance; behind (the bottom half) is duller */
            sw_px += (sw_tx - sw_px) * 0.0015f;
            sw_py += (sw_ty - sw_py) * 0.0015f;
            float ex[2] = { 0.15f, 0.85f };            /* ears wide apart: a strong pan */
            float mono[2];
            for (int c = 0; c < 2; c++) {
                float ddx = sw_px - ex[c], ddy = sw_py - 0.5f;
                float dist = sqrtf_(ddx * ddx + ddy * ddy);
                float l, r;
                get_back(2.0f + dist * 700.0f, &l, &r);
                float s = (l + r) * 0.5f / (1.0f + dist * dist * 9.0f);
                float behind = clampf((0.5f - sw_py) * 2.0f, 0, 1);
                sw_lp[c] += (s - sw_lp[c]) * (1.0f - behind * 0.85f);
                mono[c] = sw_lp[c] * 2.2f;
            }
            ol = mono[0]; orr = mono[1];
            break;
        }
        case FX_WHOOSH: {
            float a = absf(dl) > absf(dr) ? absf(dl) : absf(dr);
            wh_peak = a > wh_peak ? a : wh_peak * 0.99995f;
            if (wh_peak < 0.005f) wh_peak = 0.005f;
            float nz[2] = { rand01() * 2.0f - 1.0f, rand01() * 2.0f - 1.0f };
            float bp[2];
            for (int c = 0; c < 2; c++) {
                float v3 = nz[c] - wh_ic2[c];
                float v1 = wh_a1 * wh_ic1[c] + wh_a2 * v3;
                float v2 = wh_ic2[c] + wh_a2 * wh_ic1[c] + wh_a3 * v3;
                wh_ic1[c] = 2 * v1 - wh_ic1[c];
                wh_ic2[c] = 2 * v2 - wh_ic2[c];
                bp[c] = v1 * wh_k;                  /* unity gain at the centre */
            }
            float duck = 1.0f - 0.5f * speed01;
            ol = dl * duck + bp[0] * wh_lvl * wh_peak;
            orr = dr * duck + bp[1] * wh_lvl * wh_peak;
            break;
        }
        case FX_PITCH: {
            float d1 = pt_ph, d2 = pt_ph + W * 0.5f;
            if (d2 >= W) d2 -= W;
            float w1 = 1.0f - absf(2.0f * d1 / W - 1.0f), w2 = 1.0f - w1;
            float l1, r1, l2, r2;
            get_back(d1 + 2.0f, &l1, &r1);
            get_back(d2 + 2.0f, &l2, &r2);
            float pl = l1 * w1 + l2 * w2, pr = r1 * w1 + r2 * w2;
            ol = dl + (pl - dl) * pt_mix; orr = dr + (pr - dr) * pt_mix;
            pt_ph -= pt_rate - 1.0f;
            if (pt_ph < 0) pt_ph += W; else if (pt_ph >= W) pt_ph -= W;
            break;
        }
        }
        /* history for the effects that read it (REPEAT freezes it while it repeats) */
        if (ring && fx != FX_ECHO && fx != FX_JET && !(freezes && (on || wet > 0))) put_frame(dl, dr);
        L[i] = dl + (ol - dl) * wet;
        R[i] = dr + (orr - dr) * wet;
        beat += dbeat;
    }
    sc_back = sc_to;
    if (wet > 0) blocks_on++;
#ifdef fw_rect
    if (FXPAD_ON && chaos_mode()) {                 /* FXPAD's footer: the output's peak */
        float pk = out_peak;
        for (int i = 0; i < n; i++) { float a = absf(L[i]); if (a > pk) pk = a; }
        out_peak = pk;
    }
#endif
    return 0;                                       /* processed in place: USB, the recorder and I2S hear it */
}

/* ---- the touch screen (Model:02): ev_touch, each loop, with the polled touch object ----------------------- */
#ifdef fw_touch
static uint32_t touch_frames, touch_dropouts;
static uint32_t up_since;                           /* fw_millis when the finger seemed to lift; 0: down */
#define LIFT_MS 60u                                 /* the touch object reads "up" for a moment now and then (on a
                                                       Model:02, with the song playing): a lift counts after this */
static int on_touch(void *t)
{
    const uint8_t *o = (const uint8_t *)t;
    if (!touch_on || !chaos_mode()) {               /* CHAOS mode only: elsewhere touch is the firmware's */
        if (touch_screen) finger(&touch_screen, 0);
        up_since = 0;
        return 0;
    }
    int down = *(const uint32_t *)(o + FW_TOUCH_DOWN) != 0;
    if (!down && touch_screen) {
        uint32_t now = fw_millis | 1u;
        if (!up_since) up_since = now;
        if (now - up_since < LIFT_MS) return 1;     /* not lifted yet: keep playing where it was */
    }
    if (down && up_since) { if (fw_millis - up_since < LIFT_MS) touch_dropouts++; up_since = 0; }
    if (!down) up_since = 0;
#ifdef fw_rect
    if (FXPAD_ON) {                                 /* FXPAD: the pad plays, the controls around it are buttons */
        if (down) touch_frames++;
        fxpad_touch(*(const float *)(o + FW_TOUCH_X), *(const float *)(o + FW_TOUCH_Y), down);
        return 1;
    }
#endif
    if (down) {
        ctl_x = clampf(*(const float *)(o + FW_TOUCH_X), 0, 1);
        ctl_y = clampf(*(const float *)(o + FW_TOUCH_Y), 0, 1);   /* y counts from the bottom (measured) */
        touch_frames++;
    }
    if (down != touch_screen) finger(&touch_screen, down);
    return 1;                                       /* the firmware sees no gesture */
}
#endif

static uint8_t mode_was;
static void on_tick(void)
{
    uint8_t now = (uint8_t)chaos_mode();
    if (mode_was && !now) { touch_keys = touch_midi = touch_screen = latched = 0; }
    mode_was = now;
}

#ifndef FW_UI_VISUALIZER
/* headless: no visualizer in the firmware, so all four directions open (and close) CHAOS CONTROL's screen */
static const struct dl_page page;
static int on_key(void *ui, int action)
{
    (void)ui;
    if (action != ACTION_ALL_FOUR || !core) return 0;
    if (page_shown) { page_shown = 0; core->page_close(); }
    else core->page_open(&page);
    return 1;
}
#endif

static int on_seq_tick(void *engine) { (void)engine; ticks++; return 0; }
static int on_play(void *seq, int mode) { (void)seq; (void)mode; ticks = 0; return 0; }

/* ---- MIDI: CC 12 X, CC 13 Y, CC 14 touch, CC 15 effect --------------------------------------------------- */
static uint32_t midi_seen;
static int on_midi(uint32_t p)
{
    if ((DL_MIDI_STATUS(p) & 0xF0) != 0xB0) return 0;
    uint32_t cc = DL_MIDI_D1(p), v = DL_MIDI_D2(p);
    if (cc == 12) ctl_x = (float)v / 127.0f;
    else if (cc == 13) ctl_y = (float)v / 127.0f;
    else if (cc == 14) finger(&touch_midi, v >= 64);
    else if (cc == 15) fx_sel = (uint8_t)(v * NFX / 128);
#ifdef fw_input_router
    else if (cc == 16) { if (v >= 64) vis_toggle = 1; }   /* the visualizer on / off (m8c's keys can't close it) */
#endif
#ifdef fw_rect
    else if (cc == 17) { if (v >= 64) fp_full_req = 1; }  /* FXPAD's FULLSCREEN on / off */
#endif
    else return 0;
    midi_seen++;
    return 1;                                       /* ours: the firmware does not see it */
}

/* ---- the page ------------------------------------------------------------------------------------------------ */
#define PAD_W 32
#define PAD_H 14
#define PAD_TOP 6

static char *put(char *o, const char *s) { while (*s) *o++ = *s++; return o; }
static char *num2(char *o, float v)                 /* 0.00 .. 1.00 as "0.62" */
{
    int c = (int)(v * 100.0f + 0.5f);
    *o++ = (char)('0' + c / 100); *o++ = '.'; *o++ = (char)('0' + c / 10 % 10); *o++ = (char)('0' + c % 10);
    return o;
}
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
    uint8_t fx = fx_sel < NFX ? fx_sel : 0;
    o = put(b, " FX < ");
    o = put(o, fx_names[fx]);
    o = put(o, " >");
    if (engaged()) o = put(o, hold && latched ? "   HELD" : "   ON");
    else o = put(o, "   CHAOS");
    line(4, b, o);
    int cx = (int)(ctl_x * (PAD_W - 1) + 0.5f), cy = (int)((1.0f - ctl_y) * (PAD_H - 1) + 0.5f);
    for (int r = 0; r < PAD_H; r++) {
        o = b;
        *o++ = ' ';
        *o++ = r == 0 || r == PAD_H - 1 ? '+' : ':';     /* the font has 0x20..0x7A: no '|' */
        for (int c = 0; c < PAD_W; c++) {
            char ch = (r == PAD_H / 2 || c == PAD_W / 2) ? '.' : ' ';
            if (r == cy && c == cx) ch = engaged() ? '#' : 'O';
            else if (r == cy || c == cx) ch = engaged() ? '-' : ch;
            if (r == cy && c == cx) ch = engaged() ? '#' : 'O';
            *o++ = ch;
        }
        line(PAD_TOP + r, b, o);
    }
    o = put(b, " X ");
    o = put(o, x_names[fx]); *o++ = ' '; o = num2(o, ctl_x);
    o = put(o, "  Y ");
    o = put(o, y_names[fx]); *o++ = ' '; o = num2(o, ctl_y);
    line(PAD_TOP + PAD_H, b, o);
    o = put(b, " HOLD ");
    o = put(o, off_on[hold & 1]);
    o = put(o, "  ");
    o = dec(o, (uint32_t)(bpm() + 0.5f));
    o = put(o, " BPM  ");
    for (uint32_t k = 0; k < 10; k++) *o++ = k < motion ? '#' : '.';
    if (!ring) o = put(o, "  NO BUFFER");
    line(PAD_TOP + PAD_H + 1, b, o);
    o = put(b, " ARROWS XY  EDIT TOUCH  OPT OUT");
    line(22, b, o);
    o = put(b, " SHIFT+</> FX  SHIFT+UP HOLD");
    line(23, b, o);
}

static int key(int action)
{
    const float sx = 1.0f / (PAD_W - 1), sy = 1.0f / (PAD_H - 1);
    if (action == ACTION_ALL_FOUR) {                /* all four directions again: leave CHAOS mode */
        touch_keys = 0; latched = 0; page_shown = 0;
        if (core) core->page_close();
        return 1;
    }
    if (action & FW_KEY_SHIFT) {                    /* SHIFT chords: the effect, HOLD */
        if (action & FW_KEY_LEFT) { fx_sel = (uint8_t)((fx_sel + NFX - 1) % NFX); return 1; }
        if (action & FW_KEY_RIGHT) { fx_sel = (uint8_t)((fx_sel + 1) % NFX); return 1; }
        if (action & FW_KEY_UP) { hold ^= 1; latched = 0; return 1; }
        return 1;                                   /* SHIFT alone, or with anything else: ours */
    }
    if (action & (FW_KEY_LEFT | FW_KEY_RIGHT | FW_KEY_UP | FW_KEY_DOWN)) {
        float x = ctl_x, y = ctl_y;
        if (action & FW_KEY_LEFT) x -= sx;
        if (action & FW_KEY_RIGHT) x += sx;
        if (action & FW_KEY_UP) y += sy;
        if (action & FW_KEY_DOWN) y -= sy;
        ctl_x = clampf(x, 0, 1); ctl_y = clampf(y, 0, 1);
        return 1;
    }
    if (action == FW_KEY_EDIT) { finger(&touch_keys, !touch_keys); return 1; }
    if (action == FW_KEY_OPT) { touch_keys = 0; latched = 0; page_shown = 0; return 0; }   /* core closes it */
    return 0;
}

/* ---- the overlay on the Model:02's visualizer (core's ev_vis_draw, fw_rect) ---------------------------------
 * The visualizer is eight oscilloscopes that repaint only the pixels that change; nothing clears the frame. So the
 * overlay sits on a small panel of its own, top left (the effect, the motion meter, HOLD), and the finger's marker
 * erases where it was before it moves. What it draws is pushed with the visualizer's frame. */
#ifdef fw_rect
#define OV_BG       FW_RGB(0, 0, 0)
#define OV_DIM      FW_RGB(110, 110, 130)
#define OV_TEXT     FW_RGB(255, 255, 255)
#define OV_ACCENT   FW_RGB(0, 220, 255)
#define OV_HELD     FW_RGB(255, 170, 0)
#define OV_PANEL_X  6
#define OV_PANEL_Y  6
#define OV_PANEL_W  186
#define OV_PANEL_H  58
#define OV_MARK     9                               /* the marker's half size */
/* 5 x 7 capitals, a row a byte (bit 4 leftmost) */
static const uint8_t font57[26][7] = {
    {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11}, {0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E}, {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E},
    {0x1E,0x11,0x11,0x11,0x11,0x11,0x1E}, {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F}, {0x1F,0x10,0x10,0x1E,0x10,0x10,0x10},
    {0x0E,0x11,0x10,0x17,0x11,0x11,0x0F}, {0x11,0x11,0x11,0x1F,0x11,0x11,0x11}, {0x0E,0x04,0x04,0x04,0x04,0x04,0x0E},
    {0x07,0x02,0x02,0x02,0x02,0x12,0x0C}, {0x11,0x12,0x14,0x18,0x14,0x12,0x11}, {0x10,0x10,0x10,0x10,0x10,0x10,0x1F},
    {0x11,0x1B,0x15,0x15,0x11,0x11,0x11}, {0x11,0x11,0x19,0x15,0x13,0x11,0x11}, {0x0E,0x11,0x11,0x11,0x11,0x11,0x0E},
    {0x1E,0x11,0x11,0x1E,0x10,0x10,0x10}, {0x0E,0x11,0x11,0x11,0x15,0x12,0x0D}, {0x1E,0x11,0x11,0x1E,0x14,0x12,0x11},
    {0x0F,0x10,0x10,0x0E,0x01,0x01,0x1E}, {0x1F,0x04,0x04,0x04,0x04,0x04,0x04}, {0x11,0x11,0x11,0x11,0x11,0x11,0x0E},
    {0x11,0x11,0x11,0x11,0x11,0x0A,0x04}, {0x11,0x11,0x11,0x15,0x15,0x15,0x0A}, {0x11,0x11,0x0A,0x04,0x0A,0x11,0x11},
    {0x11,0x11,0x11,0x0A,0x04,0x04,0x04}, {0x1F,0x01,0x02,0x04,0x08,0x10,0x1F},
};
static void *ov_grid;
static void rect(int x, int y, int w, int h, uint16_t c)
{
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > FW_SCREEN_W) w = FW_SCREEN_W - x;
    if (y + h > FW_SCREEN_H) h = FW_SCREEN_H - y;
    if (w > 0 && h > 0) fw_rect(ov_grid, x, y, w, h, c);
}
/* text at scale s: each row's runs of lit pixels are one rect each */
static void text_px(int x, int y, const char *s, int sc, uint16_t c)
{
    for (; *s; s++, x += 6 * sc) {
        if (*s < 'A' || *s > 'Z') continue;
        const uint8_t *g = font57[*s - 'A'];
        for (int r = 0; r < 7; r++)
            for (int b = 4; b >= 0; b--) {
                if (!(g[r] >> b & 1)) continue;
                int n = 1;
                while (b - n >= 0 && (g[r] >> (b - n) & 1)) n++;
                rect(x + (4 - b) * sc, y + r * sc, n * sc, sc, c);
                b -= n - 1;
            }
    }
}
static int16_t mk_x = -1, mk_y;                     /* where the marker is drawn; -1: nowhere */
static uint16_t mk_c;                               /* its colour */
static void marker(int x, int y, uint16_t ring, uint16_t dot)
{
    rect(x - OV_MARK, y - OV_MARK, 2 * OV_MARK + 1, 2, ring);
    rect(x - OV_MARK, y + OV_MARK - 1, 2 * OV_MARK + 1, 2, ring);
    rect(x - OV_MARK, y - OV_MARK, 2, 2 * OV_MARK + 1, ring);
    rect(x + OV_MARK - 1, y - OV_MARK, 2, 2 * OV_MARK + 1, ring);
    rect(x - 2, y - 2, 5, 5, dot);
}
/* Each fill-rect costs the UI thread ~0.1 ms (PERF MON: drawing the whole overlay every frame took 9-17 ms of each
 * 16 ms frame, and the UI loop fell from ~300,000 to ~10,000 a second with every track playing). So only what
 * changed is drawn: the panel when what it says changes, the motion bar's changed part, the marker when it moves.
 * Scope traces that cross the overlay are mended slowly: every MEND frames, one of its three parts again. */
#define MEND 12
static uint32_t vis_frames, ov_erased;
static uint8_t ov_shown;                            /* something of ours is on the screen */
static uint32_t panel_key = 0xFFFFFFFFu;            /* what the panel shows */
static int bar_drawn = -1;                          /* the motion bar's lit width as drawn */
static uint16_t acc_drawn;                          /* the accent stripe's colour as drawn */
/* The stripe down the panel's left edge says engaged (cyan), held (orange) or idle (grey): touching changes one
   rect. The name doesn't change colour: redrawing it took ~60 rects (~10 ms with every track playing) a touch. */
static uint16_t accent(int on) { return latched ? OV_HELD : on ? OV_ACCENT : OV_DIM; }
static void panel_text(int fx, int on)
{
    rect(OV_PANEL_X, OV_PANEL_Y, 3, OV_PANEL_H, acc_drawn = accent(on));
    text_px(OV_PANEL_X + 10, OV_PANEL_Y + 6, fx_names[fx], 3, OV_TEXT);
    if (hold) text_px(OV_PANEL_X + 10, OV_PANEL_Y + 43, "HOLD", 1, OV_DIM);
}
static void bar(int from, int to, uint16_t c) { if (to > from) rect(OV_PANEL_X + 10 + from, OV_PANEL_Y + 34, to - from, 4, c); }
#define OV_BAR_OFF FW_RGB(40, 40, 50)

/* ---- FXPAD: CHAOS CONTROL's own screen in the visualizer (CHAOS VIS: SWIRL, RIPPLE, BARS) -------------------------
 * Laid out after the FXPAD concept art, on the whole 480 x 320 screen, with the firmware's eight scopes skipped (core's
 * ev_vis_scope):
 *   header   CHAOS (purple, striped) | < A:effect > | the tempo
 *   left     five effect families (wave, stack, cube, grains, rings); the current one boxed; tap one to go to it
 *   centre   the pad: 38 x 38 LED cells of 6 px (5 lit, a 1 px gap), over a 12 x 12 unit square the maths works in.
 *            SWIRL colours each by a spiral round the finger (2 arms; angle plus log-radius, minus time), RIPPLE by
 *            rings out of it, BARS by the tracks' levels. A cream crosshair is the
 *            finger. The finger's speed twists the spiral; the effect's wet speeds it up.
 *   right    the effect's X and Y, MOTION and WET as bars; MODE < name > and HOLD, both tappable
 *   FULLSCREEN the button at the pad's top right (or CC 17): the pad alone, on the whole screen; OPT goes back
 *   footer   XY | X and Y | the master output, a column a frame like a scope's sweep
 * Cheap: each frame every cell's colour is worked out (a few us), but only the cells that changed are drawn, at most
 * FP_BUDGET rects a frame with everything else; the sweep starts where the last frame stopped, in a scattered
 * order, so a busy picture refreshes over a few frames instead of costing more. The frame, labels and header are drawn
 * once (one part a frame on entry) and again only when what they show changes. */
#define FP_X0     70                                /* the pad's cells */
#define FP_Y0     52
#define FP_U      19                                /* px a unit of the pad's maths (12 units across) */
#define FP_UN     12
#define FP_C      6                                 /* px a cell: FP_LIT lit, the rest a black gap */
#define FP_LIT    5
#define FP_N      38                                /* cells across: 38 x 6 = 228 = 12 x 19 */
#define FP_SPAN   (FP_N * FP_C)
#define FP_CELLS  (FP_N * FP_N)
#define FP_BUDGET 5000                              /* pixels a frame: fill-rect costs ~0.55 us a pixel (SPI) */
/* FULLSCREEN (the button at the pad's top right, or MIDI CC 17; OPT goes back): the same 38 x 38 cells (the buffer is
   all the RAM there is), 12 x 8 px each, over 456 x 304; the maths widens to 18 x 12 units so the swirl stays round */
#define FPF_X0     12
#define FPF_Y0     8
#define FPF_BUDGET 12000
#define FP_BTN_X   280                              /* the FULLSCREEN button over the pad's top-right corner */
#define FP_BTN_Y   46
#define FP_BTN     24
static uint8_t fp_full, fp_full_drawn;
static int fp_x0 = FP_X0, fp_y0 = FP_Y0, fp_cw = FP_C, fp_ch = FP_C, fp_lw = FP_LIT, fp_lh = FP_LIT;
static float fp_ux = FP_UN;                         /* units across (12, or 18 full screen); down is FP_UN */
static void fp_layout(void)
{
    fp_x0 = fp_full ? FPF_X0 : FP_X0; fp_y0 = fp_full ? FPF_Y0 : FP_Y0;
    fp_cw = fp_full ? 12 : FP_C;      fp_ch = fp_full ? 8 : FP_C;
    fp_lw = fp_cw - 1;                fp_lh = fp_ch - 1;
    fp_ux = fp_full ? 18.0f : (float)FP_UN;
}
/* the cells the FULLSCREEN button covers (not full screen) */
#define FP_UNDER_BTN(i, j) (!fp_full && (i) >= 35 && (j) <= 2)
static volatile float trk_peak[8];
static float fp_lv[8];
static uint8_t mt_shown;                            /* FXPAD is on the screen */
static uint16_t fp_dirty, fp_scan;
static int fp_budget;
static float fp_t, fp_cx = 6.0f, fp_cy = 6.0f, fp_twist = 1.2f;   /* the centre in units (0..FP_UN) */
static int16_t fp_bar[4], fp_xh_x = -1, fp_xh_y;
static uint8_t fp_wave, fp_drawn_fx = 0xFF, fp_drawn_style = 0xFF, fp_drawn_hold = 0xFF, fp_xh_mend, fp_finger;
static int fp_drawn_bpm = -1;
static uint32_t fp_xy_key = 0xFFFFFFFFu, fp_frames;
enum { FPD_FRAME = 1, FPD_HEAD = 2, FPD_FX = 4, FPD_ICONS = 8, FPD_LABELS = 16, FPD_MODE = 32, FPD_HOLD = 64,
       FPD_FOOT = 128, FPD_BPM = 256, FPD_ALL = 511 };
static const uint8_t fx_group[NFX] = { 0, 1, 2, 2, 1, 1, 0, 0, 3, 3, 4, 4 };
static const uint8_t group_icon[5] = { PUI_I_WAVE, PUI_I_STACK, PUI_I_CUBE, PUI_I_DOTS, PUI_I_RINGS };
static const uint16_t fp_pal[16] = {                /* 0-7 the spiral's bands, 8-15 the tracks */
    PUI_BG, PUI_DPURPLE, PUI_BLUE, PUI_CYAN, PUI_BG, PUI_PURPLE, PUI_MAGENTA, PUI_ORANGE,
    PUI_RGB(0, 200, 255), PUI_RGB(80, 120, 255), PUI_RGB(170, 90, 255), PUI_RGB(255, 70, 200),
    PUI_RGB(255, 90, 90), PUI_RGB(255, 160, 40), PUI_RGB(200, 230, 40), PUI_RGB(60, 230, 140) };
/* a rect's window set-up over SPI costs about as much as 8 pixels: small cells pay for it */
static void fr(int x, int y, int w, int h, uint16_t c) { fp_budget -= w * h + 8; rect(x, y, w, h, c); }

static float turns(float y, float x)                /* atan2 in turns, 0..1; ~0.001 */
{
    float ax = absf(x), ay = absf(y);
    if (ax + ay == 0.0f) return 0.0f;
    float a = ax > ay ? ay / ax : ax / ay, s = a * a;
    float r = ((-0.0464964749f * s + 0.15931422f) * s - 0.327622764f) * s * a + a;
    if (ay > ax) r = 1.57079637f - r;
    if (x < 0) r = 3.14159274f - r;
    if (y < 0) r = -r;
    r *= 0.159154943f;
    return r < 0 ? r + 1.0f : r;
}
static uint8_t fp_value(int i, int j, uint8_t style)
{
    if (style == 3) {                               /* BARS: a track every 4 cells from the 3rd, 3 lit; level from below */
        int t = (i - 3) >> 2;
        if (i < 3 || t > 7 || ((i - 3) & 3) == 3) return 0;
        return (FP_N - 1 - j) < (int)(fp_lv[t] * FP_N) ? (uint8_t)(8 + t) : 0;
    }
    const float kx = fp_ux / FP_N, ky = (float)FP_UN / FP_N;   /* cells to units */
    float dx = ((float)i + 0.5f) * kx - fp_cx, dy = ((float)j + 0.5f) * ky - fp_cy, r2 = dx * dx + dy * dy + 0.05f;
    /* a band is 1/8 of a cycle; the maths is in units, so finer cells only smooth the bands' edges */
    float f = style == 2 ? sqrtf_(r2) * 0.18f - fp_t * 1.5f                       /* RIPPLE: a ring every 5.5 units */
                         : 2.0f * turns(dy, dx) + fp_twist * 0.5f * log2f_(r2) - fp_t;   /* SWIRL: two arms */
    f -= floorf_(f);
    return (uint8_t)((int)(f * 8.0f) & 7);
}
static void fp_text_c(int x0, int x1, int y, const char *s, int sc, uint16_t c)   /* centred in x0..x1 */
{
    pui_text(fr, x0 + (x1 - x0 - pui_width(s, sc)) / 2, y, s, sc, c);
}
static void fp_static(int part)
{
    char b[24], *o;
    uint8_t fx = fx_sel < NFX ? fx_sel : 0;
    switch (part) {
    case FPD_FRAME:
        pui_box(fr, 62, 44, 244, 244, 2, PUI_CREAM);
        pui_brackets(fr, 65, 47, 238, 238, 16, 3, PUI_CREAM);
        fr(FP_BTN_X, FP_BTN_Y, FP_BTN, FP_BTN, PUI_BG);            /* FULLSCREEN: four corners pointing out */
        pui_box(fr, FP_BTN_X, FP_BTN_Y, FP_BTN, FP_BTN, 2, PUI_CREAM);
        pui_brackets(fr, FP_BTN_X + 5, FP_BTN_Y + 5, FP_BTN - 10, FP_BTN - 10, 5, 2, PUI_CREAM);
        break;
    case FPD_HEAD:
        pui_fill(fr, 4, 4, 150, 34, PUI_PURPLE);
        pui_text(fr, 14, 11, "CHAOS", 3, PUI_BG);
        pui_stripes(fr, 108, 4, 32, 3, 12, PUI_BG);
        break;
    case FPD_FX:
        fr(162, 6, 208, 30, PUI_BG);
        pui_box(fr, 160, 4, 212, 34, 2, PUI_CREAM);
        pui_text(fr, 170, 14, "{", 2, PUI_CREAM);
        pui_text(fr, 352, 14, "}", 2, PUI_CREAM);
        o = b; *o++ = 'A'; *o++ = ':';
        for (const char *n = fx_names[fx]; *n && o < b + 11; n++) *o++ = *n;
        *o = 0;
        fp_text_c(184, 350, 14, b, 2, PUI_CREAM);
        fp_drawn_fx = fx;
        break;
    case FPD_BPM: {
        int v = (int)(bpm() + 0.5f);
        fr(380, 6, 94, 30, PUI_BG);
        pui_box(fr, 378, 4, 98, 34, 2, PUI_CREAM);
        o = b; *o++ = (char)('0' + v / 100 % 10); *o++ = (char)('0' + v / 10 % 10); *o++ = (char)('0' + v % 10);
        *o++ = 'B'; *o++ = 'P'; *o++ = 'M'; *o = 0;
        fp_text_c(380, 474, 14, v >= 100 ? b : b + 1, 2, PUI_CREAM);
        fp_drawn_bpm = v;
        break; }
    case FPD_ICONS:
        fr(4, 44, 54, 246, PUI_BG);
        for (int k = 0; k < 5; k++) {
            int y = 44 + k * 49;
            if (k == fx_group[fx]) { pui_fill(fr, 6, y, 50, 46, PUI_DPURPLE); pui_box(fr, 6, y, 50, 46, 3, PUI_PURPLE); }
            pui_icon(fr, 11, y + 3, group_icon[k], 4);
        }
        break;
    case FPD_LABELS:
        fr(314, 44, 164, 154, PUI_BG);
        for (int k = 0; k < 4; k++) {
            int y = 44 + k * 39;
            pui_text(fr, 316, y, k == 0 ? x_names[fx] : k == 1 ? y_names[fx] : k == 2 ? "MOTION" : "WET", 2, PUI_CREAM);
            pui_box(fr, 316, y + 18, 160, 16, 2, PUI_PURPLE);
            fp_bar[k] = 0;
        }
        break;
    case FPD_MODE:
        fr(314, 200, 164, 48, PUI_BG);
        pui_text(fr, 316, 202, "MODE", 2, PUI_CREAM);
        pui_text(fr, 316, 226, "{", 2, PUI_CREAM);
        pui_fill(fr, 332, 220, 128, 24, PUI_PURPLE);
        fp_text_c(332, 460, 225, style_names[vis_style < VIS_STYLES ? vis_style : 1], 2, PUI_BG);
        pui_text(fr, 464, 226, "}", 2, PUI_CREAM);
        fp_drawn_style = vis_style;
        break;
    case FPD_HOLD:
        fr(314, 254, 164, 30, PUI_BG);
        pui_text(fr, 316, 260, "HOLD", 2, PUI_CREAM);
        pui_box(fr, 450, 256, 24, 24, 3, PUI_CREAM);
        if (hold) fr(456, 262, 12, 12, latched ? PUI_ORANGE : PUI_PURPLE);
        fp_drawn_hold = (uint8_t)(hold | latched << 1);
        break;
    case FPD_FOOT:
        pui_box(fr, 4, 292, 472, 27, 2, PUI_CREAM);
        pui_fill(fr, 10, 296, 46, 19, PUI_PURPLE);
        pui_text(fr, 22, 299, "XY", 2, PUI_BG);
        fr(272, 296, 2, 19, PUI_CREAM);
        fp_xy_key = 0xFFFFFFFFu;
        break;
    }
}
static void fp_cells(uint8_t style)
{
    const int n = FP_CELLS;
    for (int k = 0; k < n && fp_budget > 0; k++) {
        int idx = (fp_scan * 37) % n;               /* 37 and 1444 share no factor: every cell, scattered */
        fp_scan = (uint16_t)((fp_scan + 1) % n);
        int i = idx % FP_N, j = idx / FP_N;
        uint8_t v = fp_value(i, j, style);
        if (fp_cell[idx] == v || FP_UNDER_BTN(i, j)) continue;
        fp_cell[idx] = v;
        int x = fp_x0 + i * fp_cw, y = fp_y0 + j * fp_ch;
        fr(x, y, fp_lw, fp_lh, fp_pal[v]);          /* LED cells: the 1 px gaps stay black */
        if (fp_xh_x >= 0 && fp_xh_x + 8 > x && fp_xh_x - 8 < x + fp_cw && fp_xh_y + 8 > y && fp_xh_y - 8 < y + fp_ch)
            fp_xh_mend = 1;
    }
}
static void fp_unmark(int px, int py, uint8_t style)   /* the cells under the old crosshair: draw them now */
{
    fr(px - 7, py - 1, 15, 3, PUI_BG);              /* the gaps between cells too */
    fr(px - 1, py - 7, 3, 15, PUI_BG);
    for (int j = (py - 8 - fp_y0) / fp_ch; j <= (py + 8 - fp_y0) / fp_ch; j++)
        for (int i = (px - 8 - fp_x0) / fp_cw; i <= (px + 8 - fp_x0) / fp_cw; i++)
            if (i >= 0 && j >= 0 && i < FP_N && j < FP_N && !FP_UNDER_BTN(i, j)) {
                uint8_t v = fp_value(i, j, style);
                fp_cell[j * FP_N + i] = v;
                fr(fp_x0 + i * fp_cw, fp_y0 + j * fp_ch, fp_lw, fp_lh, fp_pal[v]);
            }
}
static void fxpad_frame(void)
{
    fp_frames++;
    if (fp_full_req) { fp_full_req = 0; fp_full ^= 1; }
    if (!mt_shown || fp_full != fp_full_drawn) {    /* just opened (its screen is clear), or FULLSCREEN on / off */
        if (mt_shown) rect(0, 0, FW_SCREEN_W, FW_SCREEN_H, PUI_BG);
        fp_full_drawn = fp_full;
        fp_layout();
        for (int i = 0; i < FP_CELLS; i++) fp_cell[i] = 0;
        fp_dirty = fp_full ? 0 : FPD_ALL;
        fp_xh_x = -1;
        mt_shown = 1;
    }
    fp_budget = fp_full ? FPF_BUDGET : FP_BUDGET;
    uint8_t fx = fx_sel < NFX ? fx_sel : 0;
    if (fx != fp_drawn_fx) fp_dirty |= FPD_FX | FPD_ICONS | FPD_LABELS;
    if (vis_style != fp_drawn_style) { fp_dirty |= FPD_MODE; for (int i = 0; i < FP_CELLS; i++) fp_cell[i] = 0xFF; }
    if ((uint8_t)(hold | latched << 1) != fp_drawn_hold) fp_dirty |= FPD_HOLD;
    if ((int)(bpm() + 0.5f) != fp_drawn_bpm) fp_dirty |= FPD_BPM;
    if (fp_full) fp_dirty = 0;                      /* FULLSCREEN: only the pad (they draw again on the way back) */
    for (int p = 1; p <= FPD_BPM; p <<= 1)          /* one static part a frame */
        if (fp_dirty & p) { fp_dirty &= (uint16_t)~p; fp_static(p); break; }
    /* the visual: where it centres, how fast it turns */
    int on = engaged();
    float tx = on ? ctl_x * fp_ux : fp_ux * 0.5f, ty = on ? (1.0f - ctl_y) * FP_UN : FP_UN * 0.5f;
    fp_cx += (tx - fp_cx) * (on ? 0.25f : 0.05f);
    fp_cy += (ty - fp_cy) * (on ? 0.25f : 0.05f);
    fp_twist = 0.3f + (float)motion * 0.05f;        /* the finger's speed winds it tighter */
    fp_t += 0.005f + wet * 0.008f + (float)motion * 0.0015f;   /* slow: only the bands' edges change a frame */
    if (fp_t > 1000.0f) fp_t -= 1000.0f;
    if (vis_style == 3)
        for (int t = 0; t < 8; t++) {
            float p = trk_peak[t];
            trk_peak[t] = 0;
            float lv = p > 0.0004f ? clampf((6.0206f * log2f_(p) + 48.0f) * (1.0f / 48.0f), 0, 1) : 0.0f;
            fp_lv[t] = lv >= fp_lv[t] ? lv : clampf(fp_lv[t] - 0.04f, lv, 1);
        }
    /* the right panel's bars: only the part that moved */
    if (!fp_full && !(fp_dirty & FPD_LABELS)) {
        float v[4] = { ctl_x, ctl_y, (float)motion * 0.1f, wet };
        for (int k = 0; k < 4; k++) {
            int w = (int)(clampf(v[k], 0, 1) * 152.0f), d = fp_bar[k], y = 44 + k * 39 + 22;
            if (w > d) fr(320 + d, y, w - d, 8, PUI_PURPLE);
            else if (w < d) fr(320 + w, y, d - w, 8, PUI_BG);
            fp_bar[k] = (int16_t)w;
        }
    }
    /* the footer: X and Y when they change (every 4th frame at most), and one column of the output a frame */
    if (!fp_full && !(fp_dirty & FPD_FOOT)) {
        uint32_t key = (uint32_t)(ctl_x * 100.0f + 0.5f) | (uint32_t)(ctl_y * 100.0f + 0.5f) << 8;
        if (key != fp_xy_key && !(fp_frames & 7)) {
            char b[16], *o = b;
            uint32_t xs = key & 0xFF, ys = key >> 8;
            *o++ = 'X'; *o++ = ':'; *o++ = (char)('0' + xs / 100); *o++ = '.'; *o++ = (char)('0' + xs / 10 % 10); *o++ = (char)('0' + xs % 10);
            *o++ = ' '; *o++ = 'Y'; *o++ = ':'; *o++ = (char)('0' + ys / 100); *o++ = '.'; *o++ = (char)('0' + ys / 10 % 10); *o++ = (char)('0' + ys % 10);
            *o = 0;
            fr(66, 299, pui_width(b, 2), 14, PUI_BG);
            pui_text(fr, 66, 299, b, 2, PUI_CREAM);
            fp_xy_key = key;
        }
        float p = out_peak;
        out_peak = 0;
        float db = p > 0.008f ? (6.0206f * log2f_(p) + 42.0f) * (1.0f / 42.0f) : 0.0f;   /* -42..0 dB */
        int h = (int)(clampf(db, 0, 1) * 18.0f + 0.5f), x = 282 + fp_wave * 5;
        fr(x, 296, 4, 19, PUI_BG);
        if (h) fr(x, 315 - h, 4, h, PUI_MAGENTA);
        fp_wave = (uint8_t)((fp_wave + 1) % 38);
    }
    /* the pad, then the crosshair over it */
    int px = fp_x0 + (int)(fp_cx * (float)(fp_cw * FP_N) / fp_ux), py = fp_y0 + (int)(fp_cy * (float)(fp_ch * FP_N) / FP_UN);
    if (px != fp_xh_x || py != fp_xh_y || on != fp_finger) {
        if (fp_xh_x >= 0 && !(fp_dirty & FPD_FRAME)) fp_unmark(fp_xh_x, fp_xh_y, vis_style);
        fp_xh_mend = 1;
    }
    if (!(fp_dirty & FPD_FRAME)) fp_cells(vis_style);
    if (fp_xh_mend) {
        uint16_t c = on ? PUI_CREAM : PUI_DIM;
        rect(px - 7, py - 1, 15, 3, c);
        rect(px - 1, py - 7, 3, 15, c);
        fp_xh_x = (int16_t)px; fp_xh_y = (int16_t)py; fp_finger = (uint8_t)on; fp_xh_mend = 0;
    }
}
/* the touch screen on FXPAD: a finger that comes down on the pad plays it; one that comes down elsewhere taps the
   control there (the effect's arrows, a family's icon, MODE's arrows, HOLD) */
static int fxpad_touch(float tx, float ty, int down)
{
    static uint8_t was;
    int sx = (int)(clampf(tx, 0, 1) * FW_SCREEN_W), sy = (int)((1.0f - clampf(ty, 0, 1)) * FW_SCREEN_H);
    if (down && !was) {
        fp_finger = 0xFF;                           /* (redraw the crosshair) */
        if (!fp_full && sx >= FP_BTN_X - 4 && sx < FP_BTN_X + FP_BTN + 4 && sy >= FP_BTN_Y - 4 && sy < FP_BTN_Y + FP_BTN + 4) {
            was = 1;                                /* FULLSCREEN */
            fp_full_req = 1;
        } else if (fp_full || (sx >= FP_X0 && sx < FP_X0 + FP_SPAN && sy >= FP_Y0 && sy < FP_Y0 + FP_SPAN)) {
            was = 2;
            finger(&touch_screen, 1);
        } else {
            was = 1;
            if (sy < 40 && sx >= 160 && sx < 372) fx_sel = (uint8_t)((fx_sel + (sx < 266 ? NFX - 1 : 1)) % NFX);
            else if (sx < 60 && sy >= 44 && sy < 289) {
                int g = (sy - 44) / 49, f = fx_sel;
                for (int k = 1; k <= NFX; k++)      /* the next effect of that family */
                    if (fx_group[(f + k) % NFX] == g) { fx_sel = (uint8_t)((f + k) % NFX); break; }
            } else if (sx >= 314 && sy >= 216 && sy < 250)
                vis_style = (uint8_t)(1 + (vis_style - 1 + (sx < 396 ? VIS_STYLES - 2 : 1)) % (VIS_STYLES - 1));
            else if (sx >= 314 && sy >= 252 && sy < 286) { hold ^= 1; latched = 0; }
        }
    }
    if (down && was == 2) {
        ctl_x = clampf((float)(sx - fp_x0) / (float)(fp_cw * FP_N), 0, 1);
        ctl_y = clampf(1.0f - (float)(sy - fp_y0) / (float)(fp_ch * FP_N), 0, 1);
    }
    if (!down && was) {
        if (was == 2) finger(&touch_screen, 0);
        was = 0;
    }
    return 1;
}
static void on_track_peak(float *l, float *r, int t)
{
    if ((unsigned)t >= 8 || !FXPAD_ON || !chaos_mode()) return;
    float p = trk_peak[t];
    for (int i = 0; i < FW_AUDIO_FRAMES; i++) {
        float a = absf(l[i]), b = absf(r[i]);
        if (a > p) p = a;
        if (b > p) p = b;
    }
    trk_peak[t] = p;
}
static int on_vis_scope(void *scope) { (void)scope; return chaos_mode() && FXPAD_ON; }   /* skip the stock scope */

/* ---- ripples: square rings that grow from the finger and fade --------------------------------------------------
 * Spawned where the finger is when it comes down and every few frames while it stays; the faster it moves, the
 * faster they grow. Each frame a ring is erased where it was and drawn one step out: 8 rects. Whatever it crossed
 * (bars, the marker) is drawn again. */
#define RINGS 3
static struct { int16_t x, y, r, dr; } rip[RINGS];   /* r 0: free */
static uint32_t ring_spawn;
static void ring_px(int x, int y, int r, uint16_t c)
{
    int s = 2 * r + 1;
    int k[4][4] = { { x - r, y - r, s, 2 }, { x - r, y + r - 1, s, 2 }, { x - r, y - r, 2, s }, { x + r - 1, y - r, 2, s } };
    for (int i = 0; i < 4; i++) {                   /* leave the panel alone */
        if (k[i][0] < OV_PANEL_X + OV_PANEL_W && k[i][1] < OV_PANEL_Y + OV_PANEL_H) continue;
        rect(k[i][0], k[i][1], k[i][2], k[i][3], c);
    }
}
static uint16_t ring_col(int r) { int v = 255 - r * 2; if (v < 40) v = 40; return FW_RGB(v / 3, v * 3 / 4, v); }
static int rings(int x, int y, int on, uint32_t f)  /* 1 if a ring crossed the marker */
{
    int hit = 0;
    if (on && (!ring_spawn || f - ring_spawn >= 9)) {
        for (int i = 0; i < RINGS; i++)
            if (!rip[i].r) {
                rip[i].x = (int16_t)x; rip[i].y = (int16_t)y; rip[i].r = 10;
                rip[i].dr = (int16_t)(3 + motion);   /* motion 0..10 */
                ring_spawn = f | 1u;
                break;
            }
    }
    if (!on) ring_spawn = 0;
    for (int i = 0; i < RINGS; i++) {
        if (!rip[i].r) continue;
        int rx = rip[i].x, ry = rip[i].y, r = rip[i].r;
        ring_px(rx, ry, r, OV_BG);
        r += rip[i].dr;
        if (r > 110) { rip[i].r = 0; continue; }
        rip[i].r = (int16_t)r;
        ring_px(rx, ry, r, ring_col(r));
        if (mk_x >= 0 && mk_x + OV_MARK >= rx - r && mk_x - OV_MARK <= rx + r && mk_y + OV_MARK >= ry - r && mk_y - OV_MARK <= ry + r) hit = 1;
    }
    return hit;
}

static void on_vis_draw(void *grid)
{
    ov_grid = grid;
    if (!chaos_mode()) return;                      /* the frame after the visualizer closed: ev_draw erases */
    if (FXPAD_ON) {                                 /* FXPAD: the whole screen */
#ifdef fw_remote
        fw_remote[FW_REMOTE_PAUSED] = 0;            /* it's cheap: let m8c see CHAOS mode too */
#endif
        fxpad_frame();
        return;
    }
    if (!overlay_on) return;
    uint32_t f = vis_frames++;
    int on = engaged();
    uint8_t fx = fx_sel < NFX ? fx_sel : 0;
    /* the panel: the effect, the motion meter, HOLD */
    uint32_t key = fx | (uint32_t)hold << 9;
    int mw = (int)motion * 16;                      /* 10 steps of 16 px */
    if (ov_shown && key == panel_key && accent(on) != acc_drawn)
        rect(OV_PANEL_X, OV_PANEL_Y, 3, OV_PANEL_H, acc_drawn = accent(on));
    if (key != panel_key || !ov_shown) {
        rect(OV_PANEL_X, OV_PANEL_Y, OV_PANEL_W, OV_PANEL_H, OV_BG);
        panel_text(fx, on);
        bar(0, mw, OV_ACCENT); bar(mw, 160, OV_BAR_OFF);
        panel_key = key; bar_drawn = mw; ov_shown = 1;
    } else if (mw != bar_drawn) {
        if (mw > bar_drawn) bar(bar_drawn, mw, OV_ACCENT); else bar(mw, bar_drawn, OV_BAR_OFF);
        bar_drawn = mw;
    } else if (f % MEND == 0) {
        switch (f / MEND % 3) {
        case 0: panel_text(fx, on); break;
        case 1: bar(0, mw, OV_ACCENT); bar(mw, 160, OV_BAR_OFF); break;
        default: if (mk_x >= 0) marker(mk_x, mk_y, mk_c, OV_TEXT); break;
        }
    }
    /* the ripples, then the marker: only when it moves or changes colour, or a ripple crossed it */
    int x = (int)(ctl_x * (FW_SCREEN_W - 1) + 0.5f), y = (int)((1.0f - ctl_y) * (FW_SCREEN_H - 1) + 0.5f);
    int hit = rings(x, y, on, f);
    uint16_t c = latched ? OV_HELD : OV_ACCENT;
    if (mk_x >= 0 && (!on || x != mk_x || y != mk_y || c != mk_c)) {
        marker(mk_x, mk_y, OV_BG, OV_BG);
        mk_x = -1;
    }
    if (on && (mk_x < 0 || hit)) { marker(x, y, c, OV_TEXT); mk_x = (int16_t)x; mk_y = (int16_t)y; mk_c = c; }
}

/* Erase everything this mod drew (the clip column lifted: outside the visualizer it is set). */
static void ov_erase_all(void)
{
    volatile uint16_t *clip = (volatile uint16_t *)(fw_grid + 0x12EA);
    uint16_t was = *clip;
    *clip = 0;
    ov_grid = fw_grid;
    if (mt_shown) rect(0, 0, FW_SCREEN_W, FW_SCREEN_H, OV_BG);   /* METERS: the whole screen is ours */
    else {
        rect(OV_PANEL_X, OV_PANEL_Y, OV_PANEL_W, OV_PANEL_H, OV_BG);
        if (mk_x >= 0) marker(mk_x, mk_y, OV_BG, OV_BG);
        for (int i = 0; i < RINGS; i++) if (rip[i].r) ring_px(rip[i].x, rip[i].y, rip[i].r, OV_BG);
    }
    *clip = was;
    for (int i = 0; i < RINGS; i++) rip[i].r = 0;
    mk_x = -1; ov_shown = 0; mt_shown = 0; ov_erased++;
    fp_full = 0; fp_full_req = 0;                   /* the visualizer opens on the pad's own screen next time */
}
/* Any key closes the visualizer. ev_key comes before the firmware acts on it: erase now, and the firmware's own
 * exit puts its screen back over a clean one. (If the key doesn't close it, the next frame draws everything again.) */
static int on_key_vis(void *ui, int action)
{
    (void)ui;
    if (fw_ui[FW_UI_VISUALIZER] && mt_shown && fp_full && action == FW_KEY_OPT) {
        fp_full_req = 1;                            /* OPT in FULLSCREEN: back to the pad's own screen, not out */
        return 1;
    }
    if (fw_ui[FW_UI_VISUALIZER] && (ov_shown || mt_shown)) ov_erase_all();
    return 0;
}
/* Leaving the visualizer, the firmware puts its screen's text back but repaints only the cells that change from
 * blank, so the overlay would stay on the others. ev_draw runs before each frame refresh, after the screen has
 * written its text: blank what the overlay drew there, and the refresh then draws the text over it. The clip
 * column (grid + 0x12EA) is set outside the visualizer: lift it while erasing. */
static uint32_t draw_frames, vis_last;
static void on_draw(void *ui)
{
    (void)ui;
    draw_frames++;
#ifdef fw_input_router
    if (vis_toggle) {                               /* CC 16: as all four directions, through the firmware's router */
        vis_toggle = 0;
        if (fw_ui[FW_UI_VISUALIZER] && (ov_shown || mt_shown)) ov_erase_all();
        fw_input_router(fw_ui, ACTION_ALL_FOUR);
    }
#endif
#ifdef fw_frame_last
    /* CHAOS VIS FPS: hold the frame refresh's gate shut between the frames we allow */
    uint32_t period = rate_ms[vis_rate % 3];
    if (period && chaos_mode()) {
        uint32_t now = fw_millis;
        if (now - vis_last >= period) { fw_frame_last = now - 16; vis_last = now; }
        else fw_frame_last = now;
    }
#endif
    int in = chaos_mode();
    if ((ov_shown && !(in && overlay_on)) || (mt_shown && !(in && FXPAD_ON))) ov_erase_all();
}
#endif

static void open_page(void) { page_shown = 1; }
static const struct dl_page page = { "chaos-control", "CHAOS CONTROL", open_page, draw, key };

static void on_boot(void)
{
    core = dl_core();
    if (!core) return;
    core->page_add(&page);
    if (core->version >= 0x500) {
        core->setting_add(&set_fx);
        core->setting_add(&set_hold);
#ifdef fw_touch
        core->setting_add(&set_touch);
#endif
#ifdef fw_rect
        core->setting_add(&set_overlay);
        core->setting_add(&set_rate);
        core->setting_add(&set_style);
#endif
    }
    if (core->version >= 0x600) ring = (int16_t (*)[2])core->ram_claim(RING * 4);
#ifdef fw_rect
    if (core->version >= 0x600) fp_cell = (uint8_t *)core->ram_claim(FP_CELLS);
#endif
    if (ring) ring_clear();
}

#ifdef fw_touch
#define TOUCH_HOOK , DL_ON(EV_TOUCH, 40, on_touch)
#else
#define TOUCH_HOOK
#endif
#ifndef FW_UI_VISUALIZER
#define KEY_HOOK , DL_ON(EV_KEY, 40, on_key)
#else
#define KEY_HOOK
#endif
#ifdef fw_rect
#define VIS_HOOK , DL_ON(EV_VIS_DRAW, 50, on_vis_draw), DL_ON(EV_DRAW, 50, on_draw), \
                 DL_ON(EV_VIS_SCOPE, 50, on_vis_scope), DL_ON(EV_TRACK_AUDIO, 50, on_track_peak), \
                 DL_ON(EV_KEY, 20, on_key_vis)
#else
#define VIS_HOOK
#endif
DL_MOD("chaos-control", "0.3.1", "CHAOS CONTROL: an X/Y effects pad on the master output",
       DL_INFO("dirtyloader", "An X/Y effects pad on the master output: twelve effects, from filter and repeat to "
                              "tape stop, scratch and swirl. Play it on the touch screen, with the keys or MIDI CC "
                              "12-15. EDIT on its card opens the pad."),
       DL_ON(EV_BOOT, 50, on_boot), DL_ON(EV_AUDIO_OUT, 50, on_audio_out), DL_ON(EV_SEQ_TICK, 50, on_seq_tick),
       DL_ON(EV_PLAY, 50, on_play), DL_ON(EV_MIDI, 40, on_midi), DL_ON(EV_TICK, 50, on_tick)
       TOUCH_HOOK KEY_HOOK VIS_HOOK);
