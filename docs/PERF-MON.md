[dirtyloader docs](../README.md) › PERF MON

# PERF MON

PERF MON shows where the M8's time goes. It times everything with the CPU's cycle counter (DWT `CYCCNT`).

- **Source:** [examples/perf-mon/perf.c](../examples/perf-mon/perf.c).
- **Builds for:** headless 6.6.4A and the Model:02 6.6.2A.
- **Size:** 1.7 KB of ITCM. It fits beside CHAOS CONTROL on a Model:02 (12,248 of the 12,520 bytes) since core
  frees each mod's spent relocations ([LOADER.md](LOADER.md)).

## What it measures

| row | what | how |
|---|---|---|
| AUDIO | the audio interrupt, as a share of the time between audio blocks: the last second's average (NOW), its worst block (PEAK), and the worst block since EDIT (MAX) | cycles from `ev_render_in` to `ev_render_out`, against the cycles between two `ev_render_in`s |
| FX OUT | the `ev_audio_out` handlers: the master-bus DSP of other mods, such as CHAOS CONTROL's effects. The average per block, and the worst since EDIT | one handler at order 0 and one at order 255 bracket the others |
| LOOP | the UI loop: iterations a second, the longest gap between two in the last second, and the worst since EDIT. A key, the screen and the touch screen all wait for this loop | `ev_tick`. A gap includes the audio interrupt and whatever else ran |
| VIS | (Model:02) the visualizer's frames a second; the firmware's own drawing of a frame (its eight scopes, SCOPE); and the `ev_vis_draw` handlers (CHAOS CONTROL's overlay, OVL). Both are averages over the last second | SCOPE: from `ev_draw` (order 255, just before the frame refresh) to `ev_vis_draw`. OVL: `ev_vis_draw` at order 0 and 255 |

The worst values keep counting while the page is closed. Clear them with EDIT, play (in the visualizer, say),
then come back and read them.

**Where to find it:** SYSTEM SETTINGS > MODS, RIGHT on its row, or the Mod Menu.

**Over USB:** the numbers are in `perf`, in cycles, for a PEEK. The struct's offset in the mod is in the build's
symbols.

## What it found on a Model:02 (6.6.2A)

The visualizer was lagging in CHAOS mode, "mostly when all tracks are playing". The CPU runs at 768 MHz, and an
audio block is 727 µs (32 frames).

| | stopped | playing, visualizer | all tracks playing, visualizer |
|---|---|---|---|
| audio interrupt | 16% | 28–38% | 54–60% (worst block 70%) |
| CHAOS CONTROL's effects (FX OUT) | 7 µs a block | 10 µs | 10 µs |
| the firmware's scopes, a frame | — | 2–7 ms | **11–21 ms** |
| CHAOS CONTROL's overlay, a frame (first build) | — | 9.5–12 ms | 17.5 ms |
| CHAOS CONTROL's overlay, a frame (fixed) | — | 0.4–1.9 ms dragging | 0.05–0.15 ms still; 1–2 ms dragging |
| UI loop | 297,000/s | 95,000–200,000/s | 2,500–30,000/s, stalls of 25–35 ms |

What that showed:
- **Audio** had headroom throughout, and CHAOS CONTROL's DSP cost almost nothing (about 1% of a block).
- **The first overlay** redrew everything (~80 fill-rects) each frame: 9–17 ms of each 16 ms frame. Drawing only what
  changes brought it to well under 1 ms.
- **The firmware's own visualizer** is heavy when every track plays. Its scopes took 11–21 ms a frame, and it starts
  a frame every 15 ms, so the UI loop (the touch screen, the keys) hardly ran. CHAOS CONTROL now caps the
  visualizer at 30 fps in CHAOS mode (CHAOS VIS FPS), and it felt smooth after that.
- **FXPAD** (CHAOS CONTROL's own visualizer, which skips the stock scopes): 3.8–5.4 ms a frame (worst about 6.2 ms)
  with a song playing and the pad dragged over MIDI. The firmware's frame was then 30–48 µs, the UI loop 82–96 k
  passes a second with 5–6 ms gaps, and audio 34–41%. Its first build spent about 10 ms a frame: the display costs
  about 0.55 µs a pixel, so the cost follows area. A 5000-pixel budget a frame and smaller cells fixed it.

Earlier, perf-mon read 0% audio on the Model:02, which exposed a core bug: core hard-coded headless's RAM vector
table (`0x2000B800`). On the Model:02, that address is the firmware's data, so core wrote its audio and fault handlers
over two list heads there and never hooked the audio interrupt. The table is at `0x2000C000` there (startup's VTOR
store, `0x600014C4`). Each `fw.h` now names it (`FW_VECTORS`).

## Headroom (load-gen)

[examples/load-gen](../examples/load-gen/load_gen.c) adds a known load over MIDI:
- CC 20 busy-waits that many × 10 µs in the audio thread each block;
- CC 21 does the same in the UI loop each iteration;
- CC 22 clears both.

A sweep raises CC 20 in 50 µs steps with the song playing and reads PERF MON each step. It stops before a block
misses its deadline.

**Model:02, your song playing** (cursor where it was; 727 µs blocks, 768 MHz):

| extra load a block | audio (worst block) | UI loop | longest UI stall |
|---|---|---|---|
| 0 | 34% (46%) | 118,000/s | 5 ms |
| 100 µs | 48% (71%) | 91,000/s | 10 ms |
| 200 µs | 69% (79%) | 38,000/s | 12 ms |
| 250 µs | 77% (83%) | 10,000/s | 17 ms |
| 300 µs | 87% (95%) | 1,200/s | 36 ms |
| 350 µs | 93% (100%) | 14/s | 114 ms: frozen |

- **The UI runs out first.** Audio never dropped a block, but the UI loop is starved once the audio interrupt passes
  about 80%. So the useful limit is about 75% audio.
- That leaves about 200 µs a block (27%) here.
- Over the song's busiest part, where every track plays (54–60%), it leaves about 100–150 µs.

**Headless (Teensy), stopped:**
- 10% audio at the start; each 50 µs added 3.4%.
- The worst block reached 97% at +1,250 µs of 1,455.
- The UI loop fell from 289,000 to 7,000 a second.

**CHAOS CONTROL's own cost** (headless, 64-frame blocks, its screen open, each effect engaged; worst block in
brackets):

| | ITCM | flash |
|---|---|---|
| idle | 15 µs | 19 µs (56) |
| FILTER, GATE, REPEAT, SCRATCH | 15–20 µs | 19–34 µs (53–77) |
| CRUSH, ECHO, JET, TAPE STOP, WHOOSH | 27–30 µs | 19–34 µs (53–81) |
| GRAIN | 37 µs | 54 µs (101) |
| PITCH | 43 µs | 48 µs (105) |
| SWIRL | 52 µs | 57 µs (102) |

Dragging the finger costs next to nothing more. At its heaviest, CHAOS CONTROL is 4% of a block from ITCM, and
up to 7% in its worst blocks from flash.

**Memory left on the Model:02** (lfo-sends, perf-mon, load-gen in ITCM; CHAOS CONTROL's code in flash):
- ITCM: 6.3 KB of 12.5 KB.
- Mods' flash: 1,014 KB of 1,024.
- Spare DTCM: none; CHAOS CONTROL's history takes all 40 KB.

## First readings (headless 6.6.4A, spare Teensy)

With the four mods there: core-api-demo, lfo-sends, CHAOS CONTROL and PERF MON.

| | stopped | playing the test song |
|---|---|---|
| CPU clock (measured) | 756 MHz | 756 MHz |
| audio block | 1,453 µs (64 frames) | 1,453 µs |
| audio interrupt | 10% (worst block 11%) | 19–26% (worst block 34%) |
| `ev_audio_out` handlers (CHAOS CONTROL idle) | 14 µs | 14 µs |
| UI loop | ~240,000 a second; longest gap 0.45 ms | ~180,000 a second; longest gap 122 ms |

The 122 ms gaps while playing came with the display stream on (m8c's `E`, which the harness sent to press PLAY over
USB), so they may be the cost of sending the screen to m8c. Not yet separated.

## Limits

- Interrupts other than audio (USB, the display's DMA) show up only as LOOP gaps.
- Per-track and send-effect handlers (`ev_track_audio`, `ev_fx_audio`) aren't timed apart: they fall inside AUDIO.
- SCOPE assumes the frame refresh follows `ev_draw` in the same loop, which it does (`ev_draw` is its call's
  `call_pre`).
- The hook table holds 64 subscriptions in all, and PERF MON takes 9 (6 on headless). On the Teensy, the
  self-test mod's 39 left too few, so it was turned off there.
