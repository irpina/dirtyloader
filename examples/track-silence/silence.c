/* SPDX-License-Identifier: GPL-2.0-or-later */
/* track-silence: ev_track_audio in its smallest form. Track 1's audio is zeroed in place after it renders, before
 * its mixer strip and its reverb, delay and MFX sends read it: track 1 goes silent everywhere. A real mod would
 * process the blocks instead (a per-track effect). */
#include "dl/mod.h"
#include "m8-headless/fw.h"

static void on_track_audio(float *left, float *right, int track)
{
    if (track != 0) return;
    for (int i = 0; i < FW_AUDIO_FRAMES; i++) left[i] = right[i] = 0.0f;
}

DL_MOD("track-silence", "0.1.1", "Silence track 1 (ev_track_audio)",
       DL_INFO("dirtyloader", "Silences track 1: an example of ev_track_audio, which hands a mod each track's audio."),
       DL_ON(EV_TRACK_AUDIO, 50, on_track_audio));
