/* SPDX-License-Identifier: GPL-2.0-or-later */
/* load-gen: a controllable CPU load, to measure headroom with PERF MON.
 *
 *   CC 20 (any channel): busy-wait this many x 10 us in the audio thread, each block (ev_audio_out)
 *   CC 21:               busy-wait this many x 10 us in the UI loop, each iteration (ev_tick)
 *   CC 22 > 0:           both back to 0
 *
 * With the song playing, raise CC 20 until PERF MON shows audio blocks dropping (the block period growing, or
 * fewer blocks a second): what the audio thread had left is then the load-gen time just below that. Nothing
 * else: it doesn't touch the sound. Its waits use the CPU's cycle counter, so they are real time. */
#include "dl/mod.h"
#include "m8-headless/fw.h"
#include "dl/core.h"                                /* DL_MIDI_* */

#define CYCCNT (*(volatile uint32_t *)0xE0001004u)
static volatile uint32_t audio_us, ui_us;
static volatile uint32_t cyc_per_us;               /* measured each second against fw_millis; 0 until then */
static uint32_t win_cyc, win_ms;

static void wait_us(uint32_t us)
{
    uint32_t c = cyc_per_us;
    uint32_t t0 = CYCCNT, n = us * (c >= 100 && c <= 2000 ? c : 600u);
    while (CYCCNT - t0 < n) { }
}
static int on_audio(float *l, float *r, int n) { (void)l; (void)r; (void)n; if (audio_us) wait_us(audio_us); return 0; }
static void on_tick(void)
{
    if (ui_us) wait_us(ui_us);
    uint32_t ms = fw_millis, now = CYCCNT;
    if (!win_ms) { win_ms = ms | 1u; win_cyc = now; return; }
    if (ms - win_ms >= 1000) {                      /* the clock, from the last second */
        cyc_per_us = (now - win_cyc) / ((ms - win_ms) * 1000u);
        win_ms = ms | 1u; win_cyc = now;
    }
}
static int on_midi(uint32_t p)
{
    if ((DL_MIDI_STATUS(p) & 0xF0) != 0xB0) return 0;
    uint32_t cc = DL_MIDI_D1(p), v = DL_MIDI_D2(p);
    if (cc == 20) audio_us = v * 10u;
    else if (cc == 21) ui_us = v * 10u;
    else if (cc == 22 && v) audio_us = ui_us = 0;
    else return 0;
    return 1;
}
DL_MOD("load-gen", "0.1.1", "load-gen: a CPU load for headroom tests (CC 20 audio, CC 21 UI)",
       DL_ON(EV_AUDIO_OUT, 10, on_audio), DL_ON(EV_TICK, 60, on_tick), DL_ON(EV_MIDI, 30, on_midi));
