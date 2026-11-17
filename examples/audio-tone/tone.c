/* SPDX-License-Identifier: GPL-2.0-or-later */
/* audio-tone: exclusive audio (ev_audio_out) in its smallest form. While loaded, the M8's output is a 440 Hz sine
 * at -14 dBFS on both channels, whatever the song plays: the handler writes the blocks and takes the event, so no
 * later handler runs. An insert effect would read the blocks and write them back processed instead. */
#include "dl/mod.h"
#include "m8-headless/fw.h"

static float s, c = 0.2f;                       /* a rotating vector: sin and cos of the phase, amplitude 0.2 */
static uint32_t blocks;

static int on_audio_out(float *left, float *right, int frames)
{
    const float k = 0.0626502f, kc = 0.9980355f; /* sin and cos of 2 pi 440 / 44100 */
    for (int i = 0; i < frames; i++) {
        float ns = s * kc + c * k, nc = c * kc - s * k;
        s = ns; c = nc;
        left[i] = right[i] = s;
    }
    if (++blocks % 1024 == 0) {                  /* keep the amplitude from drifting */
        float m = s * s + c * c, g = 1.5f - m / (2 * 0.04f);
        s *= g; c *= g;
    }
    return 1;
}

DL_MOD("audio-tone", "0.1.0", "440 Hz tone (exclusive audio)", DL_ON(EV_AUDIO_OUT, 50, on_audio_out));
