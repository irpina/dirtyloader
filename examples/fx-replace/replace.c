/* SPDX-License-Identifier: GPL-2.0-or-later */
/* fx-replace: ev_fx_audio taken. The reverb no longer runs: its input (the tracks' reverb sends, the delay and MFX
 * returns) goes out in its place, dry and at a quarter of the level, as if the reverb were a plain gain. A real
 * mod would put its own reverb here. */
#include "dl/mod.h"
#include "m8-headless/fw.h"

static int on_fx_audio(int stage, float *left, float *right)
{
    if (stage != FW_FX_REVERB) return 0;
    for (int i = 0; i < FW_AUDIO_FRAMES; i++) { left[i] *= 0.25f; right[i] *= 0.25f; }
    return 1;
}

DL_MOD("fx-replace", "0.1.1", "Replace the reverb (ev_fx_audio)",
       DL_INFO("dirtyloader", "Replaces the reverb send effect with the mod's own: an example of ev_fx_audio, which "
                              "hands a mod a send effect's audio block."),
       DL_ON(EV_FX_AUDIO, 50, on_fx_audio));
