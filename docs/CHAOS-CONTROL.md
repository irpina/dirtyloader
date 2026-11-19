[dirtyloader docs](../README.md) › CHAOS CONTROL

# CHAOS CONTROL

CHAOS CONTROL is an X/Y performance pad on the M8's master output, in the spirit of a modern Kaoss pad.

- **Source:** [examples/chaos-control/chaos.c](../examples/chaos-control/chaos.c).
- **Needs:** core 0.6, for `ram_claim` (and on the Model:02, `ev_vis_draw` for the overlay).
- **Builds for:**
  - headless 6.6.4A, where every effect is tested on hardware;
  - the Model:02 6.6.2A, with the touch screen: tested on a Model:02 (CHAOS mode, touch, FILTER heard through the
    speaker and recorded over USB; see [the Model:02 results](#hardware-results-model02-662a)).

## The effects

You play one effect at a time, and each has two axes. Touching the pad engages the effect and lifting releases
it, with a 6 ms fade either way. With **HOLD** on, lifting keeps it engaged until the next touch.

| effect | X | Y | notes |
|---|---|---|---|
| FILTER | cutoff: left of centre low-pass (80 Hz–20 kHz), right high-pass (20 Hz–8 kHz), centre off | resonance (Q 0.6–14.6) | TPT state-variable filter |
| REPEAT | slice length: 1/4, 1/8, 1/16, 1/32 or 1/64 beat, tempo-synced | repeat speed: half to double (centre: as recorded) | repeats the last slice before the touch; the history freezes while it repeats |
| TAPE STOP | stop time, 80–460 ms | how far it slows: to a stop, or to half speed | the read head falls behind the live audio; a full stop fades to silence |
| CRUSH | sample rate, 44.1 kHz down to ~900 Hz (sample and hold) | bits, 12 down to 2 | quantises against the music's own peak, so it bites at any level |
| GATE | rate: 1, 2, 4, 8 or 16 a beat, synced to the sequencer | depth | ~1 ms edges |
| ECHO | time: 1/8, 1/4, 3/8 or 1/2 beat (halved until it fits 223 ms) | feedback (up to 0.92) | ping-pong, damped; lifting off stops the send and lets the tail ring out |
| JET | flanger delay, 0.3–9.4 ms (manual sweep) | feedback | |
| PITCH | −12 … +12 semitones (whole steps) | mix | two crossfaded read heads over a 46 ms window |

**Four more that react to the finger's movement**, not only where it is. The mod tracks the finger's speed in pad
widths a second: it rises fast and falls over ~30 ms. The page shows it as a 10-step MOTION meter.

| effect | X | Y | movement |
|---|---|---|---|
| SCRATCH | the platter: where the read head is in the last ~220 ms | the crossfader (the bottom tenth cuts) | the read head follows the finger sample by sample, so dragging scrubs the audio back and forth at the finger's speed; a still finger is silence (a DC blocker removes the held sample) |
| GRAIN | where the grains come from in the frozen audio | grain size, 10–100 ms | two overlapping grains; the faster the finger moves, the more each new grain's place (up to half the field) and pitch (up to ±0.75 octave) scatter |
| SWIRL | left / right of your head | front / back: the bottom half is behind you and duller | each ear hears the sound late by its distance, so moving towards or away bends the pitch (Doppler), and softer with distance (ears at 0.15 and 0.85 of the pad) |
| WHOOSH | the noise band, 150 Hz–15 kHz | resonance | band-passed noise whose level is the finger's speed (squared), scaled to the music's peak; the music ducks up to 6 dB under it |

**Timing:**
- The tempo is the firmware's own (`fw_bpm`).
- Beats come from the sequencer's ticks: 192 a beat, measured at 384 a second at 120 BPM. When the sequencer isn't
  ticking, the beat runs free at the tempo.

**The history:**
- REPEAT, TAPE STOP, ECHO, JET, PITCH, SCRATCH, GRAIN and SWIRL share one buffer: 9,856 stereo frames (223 ms) of 16-bit audio, from core's
  `ram_claim`.
- It comes from 40 KB of DTCM between the firmware's `.bss` (which ends at `0x200415E0`) and its stack. On hardware,
  after a day of saves, loads and playback, that area still held power-up noise up to `0x2004EE00`. So the stack has
  never gone deeper than about 4.6 KB, and core keeps 14 KB clear of it.
- The firmware's heap in OCRAM is fully claimed (`__brkval` = `0x20280000`), so it is not an option.

## CHAOS mode: all four directions

CHAOS mode is the M8's visualizer: press **UP, DOWN, LEFT and RIGHT at once** (the input action `0xE4`). The pad
only plays in CHAOS mode. Touch, MIDI and HOLD engage nothing outside it, and leaving it releases everything.

- **Model:02 6.6.2A:**
  - The visualizer is the firmware's own. The input router (`0x6004C6C8`, `ev_key`'s target) handles `0xE4` by
    toggling the byte at `ui + 0` (`0x20015458`, `FW_UI_VISUALIZER`), except on some screens (a mask over the view
    id, plus SAMPLE RECORD).
  - CHAOS is live while that byte is set, and the touch screen is the pad.
  - On a Model:02, the four direction keys pressed together set the byte to 1, and pressing them again clears it.
  - All four sent over USB (m8c's key command) open it too, but only once the display stream is on (`E`); before
    that the firmware ignores USB keys.
- **Headless 6.6.4A:**
  - The firmware has no visualizer. Its router (`0x6004ADEC`) has no `0xE4` case, and the whole image has no other
    compare with `0xE4` on an input path.
  - So CHAOS CONTROL takes `0xE4` itself (`ev_key`): all four directions open its screen, and again (or OPT)
    close it. That screen is CHAOS mode.

## Playing it

**CHAOS CONTROL's screen** (all four directions on headless; on any unit also SYSTEM SETTINGS > MODS (TELOS),
RIGHT on its row, or the Mod Menu):
- The arrows move the cursor over a 32 × 14 pad.
- EDIT engages and releases.
- SHIFT+LEFT / SHIFT+RIGHT change the effect.
- SHIFT+UP turns HOLD on and off.
- OPT, or all four directions, leaves.

**MIDI**, in CHAOS mode (any channel):

| CC | does |
|---|---|
| 12 | X (0–127) |
| 13 | Y (0–127) |
| 14 | touch: 64 and up is down |
| 15 | the effect: 0–127 across the twelve, about 10.7 each |

**The Model:02's touch screen:**
- In the visualizer (and on CHAOS CONTROL's screen), the whole screen is the pad while **CHAOS TOUCH** is ON (the
  Mod Menu).
- The firmware doesn't see those touches.
- Set CHAOS TOUCH to OFF to keep the firmware's own touch there. Outside CHAOS mode, touch is always the
  firmware's.

**Settings** (the Mod Menu, kept in `settings.txt`): CHAOS FX, CHAOS HOLD and, on the Model:02, CHAOS TOUCH,
CHAOS OVERLAY, CHAOS VIS FPS and CHAOS VIS.

**CHAOS VIS FPS** (60, 30 or 20; 30 by default) caps the Model:02's visualizer in CHAOS mode:
- With every track playing, the firmware's scopes take 11–21 ms a frame, and it starts one every 15 ms. So the UI
  loop, which reads the touch screen and the keys, hardly ran: that was the lag ([PERF-MON.md](PERF-MON.md)).
- The frame refresh draws only when `fw_millis` is more than 15 ms past the last frame's time (`0x2001B4DC`,
  `fw_frame_last`). CHAOS CONTROL's `ev_draw` handler runs just before it: it sets that time to now to skip a frame,
  and to now − 16 to let one through.

## The touch screen (Model:02 6.6.2A, static)

The touch engine `0x600A5E60` runs every loop:
1. It polls the controller over I²C (`0x6007B6B4`, only after the touch interrupt has set `0x200416B1`).
2. It asks `0x6007BB20` whether a gesture happened, which returns the object's `+0x52`.
3. It dispatches by view.

The poll fills the touch object `0x200177D4`:

| field | |
|---|---|
| `+0x40`, `+0x44` | x, y: the raw point over the panel size, calibrated (x: (v − 0.05) × 1.111; y: (v − 0.1) × 1.333) and clamped to 0..1; y counts from the bottom (measured on a unit) |
| `+0x38`, `+0x3C` | where the finger came down |
| `+0x30`, `+0x34` | the movement since then |
| `+0x58` | the time the finger came down; 0 once it lifts, and x and y go to 0 too |
| `+0x52` | a gesture happened (what the engine checks) |
| `+0x53` | mode |

Core's `ev_touch` is a `call_pre` on the `bl 0x6007BB20` at `0x600A5E88`:
- Handlers get the polled object.
- A handler that takes the event makes it read as "no gesture", so the engine dispatches nothing that frame.

CHAOS CONTROL takes the frame in CHAOS mode:
- The finger is down while `+0x58` is nonzero. With the song playing it reads 0 now and then for a moment, so a lift
  counts only after 60 ms; until then the pad stays where it was.
- X is `+0x40`, and Y is `+0x44`.

On a Model:02, logged every 100 ms while a finger moved, `+0x58` was nonzero while it was down, and x and y followed
it across 0..1. **y counts from the bottom**, not from the top as first read from the disassembly: the overlay's
marker showed it mirrored. The momentary 0s ended the effect and hid the marker on beats until the 60 ms rule.

## FXPAD: CHAOS CONTROL's own visualizer (Model:02)

**CHAOS VIS** (Mod Menu, or the mod's OPTIONS page in the MOD LOADER): STOCK, SWIRL (the default), RIPPLE or BARS.
Any style but STOCK makes CHAOS mode skip the firmware's eight scopes (core's `ev_vis_scope`) and draws the FXPAD
screen instead, after the concept art:
- **Header:** CHAOS on a striped purple tab, `{ A:<effect> }` with arrows that step the effect, and the tempo.
- **Left column:** five effect-family icons (wave, stack, cube, dots, rings). The selected family is framed; tapping
  one jumps to its first effect.
- **The pad:** a 38 × 38 grid of 5 px LED cells in 6 px steps (228 px square; until 2026-11-18 it was 12 × 12 cells
  of 19 px, which made the swirl break up into blocks), corner brackets, and a crosshair at the finger (cream while
  engaged). The field is closed-form math, one value per cell, worked out in a 12 × 12 unit square so the finer
  cells only smooth the bands' edges, and banded into 8 colours:
  - SWIRL: `2·turns + twist·½·log2(r²) − t`, a log spiral around the eased finger;
  - RIPPLE: `√r²·0.18 − 1.5t`, rings running out from the finger;
  - BARS: a 3-cell column per track, as tall as the track's peak (`ev_track_audio`).
- **Memory:** the cells' last colours (1,444 bytes) come from core's `ram_claim`, not ITCM. The sound history shrank
  from 10,240 to 9,856 frames to make room in the 40 KB core hands out. Without the claim (an older core), CHAOS VIS
  acts as STOCK.
- **Right column:** the effect's X and Y parameter names with bars, MOTION and WET, the MODE pill (tap its arrows to
  cycle SWIRL/RIPPLE/BARS) and the HOLD box (tap to toggle).
- **Footer:** an XY pill with the finger's position (every 8th frame), and a scrolling level trace of the output
  (one column a frame, in dB).

**Cost:** each frame redraws the static parts only when they change and the cells within a 5000-pixel budget (each
rect also pays 8 pixels for its window set-up), in a scattered order (index `scan·37 mod 1444`), so the field
shimmers across the pad over a few frames. Measured on a Model:02 with the 12 × 12 pad, a song playing and the pad
being dragged: **3.8–5.4 ms a frame** (worst about 6.2 ms) at 30 fps, against the stock scopes' 11–21 ms with every
track playing. The UI loop kept 82–96 k passes a second (`docs/PERF-MON.md`). The 38 × 38 pad changes about as
many pixels a frame (a desktop model of the maths: 2.7–4.0 k against 2.0–4.3 k), in more, smaller rects, under
the same budget; **not yet measured on the Model:02**.

![The pad's maths at 12 × 12 (left) and 38 × 38 (right), SWIRL above, RIPPLE below: a desktop render, not the unit](../shots/core07/fxpad-resolution.png)

**m8c sees it too.** The visualizer pauses m8c's screen stream (the m8c sender `0x200159A4`, `+0x19`, set on entry).
That's probably so the stock scopes don't flood USB. With FXPAD, CHAOS CONTROL lifts the pause, so m8c, and
dirtyloader's screenshots, show CHAOS mode.

**MIDI CC 16** (64 and up) opens or closes the visualizer: CHAOS CONTROL passes the four-direction action to the
firmware's input router (`0x6004C6C8`). While the visualizer is open, the firmware ignores m8c's keys, so this is
the way out from a computer.

**Leaving:** any key closes the visualizer. CHAOS CONTROL takes `ev_key` first, so it erases the whole screen before
the firmware acts on the key, and the firmware's own exit then restores its screen.

On the Model:02, with the 12 × 12 pad (before 2026-11-18):

| SWIRL | RIPPLE | BARS |
|---|---|---|
| ![FXPAD, SWIRL](../shots/core07/fxpad-swirl.png) | ![FXPAD, RIPPLE](../shots/core07/fxpad-ripple.png) | ![FXPAD, BARS](../shots/core07/fxpad-bars.png) |

Not done from the concept: the header's second slot shows the tempo, not a second effect (`B:VERB`), and there's no
SYNC box.

## The overlay on the Model:02's visualizer

In CHAOS mode the visualizer shows:
- a panel at the top left with the effect's name, the 10-step MOTION meter, and HOLD when it is on. The stripe down
  its left edge is cyan while the pad is engaged, orange while held, and grey otherwise;
- a square where the finger is, while the pad is engaged (orange while held).

**CHAOS OVERLAY** in the Mod Menu turns it off.

How it draws:
- The visualizer's frame path never reaches `ev_draw`'s site. In it, the frame refresh `0x6004B514` draws eight
  scopes (`0x6004A64A` each), then pushes the frame with a tail call. Core 0.6 adds `ev_vis_draw`, a `flash_mid` at
  `0x6004B620`, between the two. It runs while the firmware's clip column (`grid + 0x12EA`) is still 0.
- It draws with the firmware's fill-rect `0x60078C34` (`fw_rect`), the one the scopes use. It takes RGB565 on the
  480 × 320 screen, and also sends m8c the rectangle when the display stream is on. Text is a 5 × 7 font in the mod,
  one rect for each run of lit pixels.
- Nothing clears the visualizer's frame: the scopes repaint only the pixels that change. So the marker erases itself
  when it moves. The panel is blanked only when what it says changes; blanking it every frame flickered.
- **Each fill-rect costs about 0.1 ms** of the UI thread, more while the audio is busy. Redrawing the whole overlay
  each frame (~80 rects) took 9–17 ms of a 16 ms frame. So a frame draws only what changed:
  - the motion bar's changed part;
  - the marker when it moves;
  - the stripe down the panel's left edge when the pad engages (cyan), holds (orange) or releases (grey);
  - the whole panel only when the effect or HOLD changes.
- Scope traces that cross the overlay are mended slowly: every 12 frames, one of its three parts is drawn again.
- On leaving, the firmware puts the screen's text back but repaints only cells that change from blank. So the mod
  erases its drawing in `ev_draw` on the first normal frame, before the text is drawn, with the clip column lifted.

## Hardware results (headless 6.6.4A, spare Teensy)

All of these were driven over USB MIDI from the PC, with the M8's USB audio recorded. The source was a held WAVSYNTH
tone at 120 BPM.

| effect | test | result |
|---|---|---|
| FILTER | low-pass at X 10, high-pass at X 118 | spectral centroid 3.7 kHz → 278 Hz, and → 7.7 kHz |
| REPEAT | X 64: 1/16 beat = 1,378 frames | correlation at 1,378 frames 0.9999 (dry: 0.76) |
| TAPE STOP | X 64, Y 0 | level falls to ~0 (1.5e-5) within 0.5 s |
| CRUSH | X 100, Y 100 | held runs 24.6 samples (expected ~21); 661 → 77 levels; same loudness |
| GATE | X 64: 4 a beat; Y 127 | envelope at 8.06 Hz (expected 8.0); minimum ≈ 0 |
| ECHO | X 40: 1/4 beat; Y 110, then the song stopped | repeats every 125 ms, alternating L, R, L, R, each ~0.7× the last; still ringing 1 s on |
| JET | X swept | centroid moves 1.7 → 3.8 kHz across the sweep |
| PITCH | X 127, X 0 | 131 Hz → 260 Hz, and → 66 Hz |
| HOLD | tap and lift, then tap again | still filtered after lifting (centroid 270 Hz); dry after the second tap |
| SCRATCH | finger still; dragging X (0.5 s strokes); dragging with the fader at the bottom | 1.5e-5 (silence); 0.0175; 1.5e-5 |
| GRAIN | finger still; then moving (0.25 s strokes) | a steady drone (0.032, dry 0.041); the spectral change between frames doubles (0.23 → 0.46) |
| SWIRL | finger far left; far right; bottom; top; moving towards / away | L 0.037 / R 0.010; L 0.010 / R 0.037 (11 dB); centroid 1.1 kHz behind, 2.5 kHz in front; the 131 Hz note moves 125–136 Hz |
| WHOOSH | finger still; moving fast | level unchanged (0.0405 vs dry 0.0404); 0.060, centroid 3.6 → 7.8 kHz |
| CHAOS mode | MIDI touch on the project screen; all four directions; MIDI touch; all four again with the finger still down | nothing (3,550 Hz); CHAOS CONTROL's screen opened; filtered (270 Hz); back to the project screen, dry (3,548 Hz) |

The page:
- The cursor moves.
- EDIT engages, and the cursor shows `#` with crosshair lines.
- SHIFT+LEFT/RIGHT changed the effect, and SHIFT+UP toggled HOLD.

**Demos:**
- One WAV per effect in `shots/chaos/`: 0.8 s dry, then X swept across the pad while engaged, then released.
- TAPE STOP's is three stops of different lengths.
- The motion effects are played with gestures instead:
  - SCRATCH: slow, then fast scratches.
  - GRAIN: a second held still, then scattering.
  - SWIRL: one circle around your head a second.
  - WHOOSH: flicks across the pad that speed up.

**Where the effects are heard:** core's `ev_audio_out` first wrapped the node that feeds USB. On both models that node
shares its input with the I2S branch (speaker, headphones, line out), which copies the blocks before it runs. So the
effects reached USB, and every recording above, but never the headphone jack. Core now wraps the soft clip, the last
node before the split ([CORE-EVENTS.md](CORE-EVENTS.md)). On a Model:02, FILTER was then heard through the
speaker. On headless, the USB audio still gets FILTER after the move (centroid 3.1 → 10.3 kHz at the pad's right edge).

## Hardware results (Model:02 6.6.2A)

Core 0.6 and CHAOS CONTROL on a Model:02 (upgraded from 6.5.1), with the owner's own song and fingers:

| test | result |
|---|---|
| flash (TyTools, a `.hex` made from the patched `.bin` in the same layout as Dirtywave's own TyUploader `.hex`) | boots 6.6.2 with core 0.6; the song in memory survived |
| `unit add`, `restart`, `status` | chaos-control 0.1.0 loaded, 9,464 bytes, 7 hooks |
| all four directions on the device | `FW_UI_VISUALIZER` 0 → 1, the visualizer opens; again → 0 |
| touch, logged every 100 ms | the finger's x / y and down state reach the mod; engaged only in the visualizer |
| FILTER, finger right, before the fix | USB: centroid ~4.8 → ~10 kHz; the speaker: no change |
| FILTER, after the fix | heard through the speaker, following the finger |
| the overlay (0.2.0) | shown in the visualizer, `0x200137FC` (the frame refresh's branch) following `ui + 0`; ~66 frames a second, ~35–50 with the song playing |
| first overlay build | flickered, its marker mirrored top to bottom, pieces left after closing; the marker and the effect dropped out on beats |
| after the fixes | the marker under the finger through beats (1 dropout bridged in a session), no flicker, 3 closes erased cleanly, no reboot in 12 minutes |
| lag with every track playing (PERF MON) | the overlay drawing everything each frame, then the firmware's scopes at 60 fps. After drawing only changes and the 30 fps cap: "smooth now"; 30 frames a second measured |

## Limits

- **A black screen, once (Model:02):** with the first overlay build, the display went black in the visualizer while
  the keys still worked; the unit was then power-cycled. The fault record had nothing, and it didn't happen again with
  the fixed build. A likely cause, found later: core 0.6 wrote its fault and audio handlers into the Model:02 firmware's
  own data at `0x2000B80C..18` (headless's vector table address; fixed, see [PERF-MON.md](PERF-MON.md)). If it does
  happen, set CHAOS OVERLAY to OFF.
- **The scopes draw through the overlay** where their traces cross it, until its next frame.
- **USB while the visualizer is open (Model:02):** core stopped answering USB commands once the display stream had
  been asked for (`E`) while the visualizer was open, and answered again when it closed. Before that, a read with the
  stream off worked. Tools should read state outside the visualizer, or before asking for the screen.
- **Only FILTER was played on the Model:02.** The other eleven run the same code, tested on headless.

- **History:** 223 ms. REPEAT's longest slice and ECHO's time halve until they fit: at 120 BPM, 1/4 beat is the
  longest REPEAT slice, and 1/2 beat echoes become 1/4.
- **One effect at a time.** There's no chaining yet.
- **Motion over MIDI is coarser** than a finger on the screen: CC steps are 1/127, and the speed comes from how far
  the position moves each block.
- **The master output only.** Per-track sends to the pad aren't hooked.
- **The Model:02:** the tempo address is from the disassembly. The spare RAM range ran without trouble, but the
  stack depth there is assumed to be like headless, not measured.

