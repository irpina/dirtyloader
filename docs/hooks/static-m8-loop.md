# The per-frame `loop()` and its subsystems (static hunt, M8 6.6.2A Model02)

Decomposing `loop()` is the single highest-leverage mapping step: it gates RENDER, INPUT, transport, row-fire
and tick ([MAPPING.md](MAPPING.md), primitives 3/4/7). Addresses are flash addresses (base `0x60000000`);
file offset = address − `0x60000000` + `0x200`. Found by decompiling `main`/`loop` and every direct callee
and tagging peripheral-register and table refs (`dirtyloader.re`, in-process Ghidra).

**`main()` confirmed** (`0x600AE04C`, 16 bytes): `setup(); while (1) { loop(); yield(); }` — calls exactly
`0x60082374`, `0x60081BD4`, `0x600B4DC0`. The Core's BOOT/TICK sites (`0x600AE04E`/`0x600AE052`) are correct.

## `loop()` is a cooperative scheduler, not a flat list

`loop()` (`0x60081BD4`, 338 bytes) runs subsystem groups at different rates behind timing gates
(`now − last > N`, where the `_DAT_60081dXX` globals are RAM timer pointers):

| order | call | size | what it is | conf |
|---|---|---|---|---|
| µs gate | `0x6007BBB4` (+`0x6007C6C0`) | 26 / 342 | a micros()/elapsed read (1 peripheral ref) + its user | S2 |
| every frame | `0x60081A90` | 78 | ~5 ms service group: 6 subsystems (`0x6007CBFC`, `0x6007D23C`, `0x6007C9E4`, `0x6007BFB8`, `0x60079A7C`, `0x60039964`) | S2 |
| every frame | **`0x600A5E60`** | 558 | **the touch / gesture engine** — unconditional each loop; dispatches touch deltas and x/y to per-view handlers ([static-m8-ui.md](static-m8-ui.md)). *Corrected: first read as a sequencer engine.* | S2 |
| every frame | `0x60062944` | 64 | small 2-call service | S3 |
| UI gate | **`0x6008196C`** | 238 | returns a byte (`bVar ^ 1`) behind a ~10 ms gate; `loop()` uses it to decide the UI frame | S2 |
| UI frame | **`0x6004C6C8`** | 1142 | **UI event / view-update stage** (see below) | S2 |
| UI frame | `0x6004BFF0` | 32 | small pre-flush step | S3 |
| UI frame | **`0x6004B514`** | 490 | **the display driver / frame flush** (see below) | S2 |
| UI frame | `0x60030ECC` … | 56 | tail (a text/label build loop follows in `loop()`) | S3 |

The UI branch in `loop()` is, in order: `0x6004C6C8(_DAT_60081d48, …)` → `0x6004BFF0(_DAT_60081d48)` →
`0x6004B514(_DAT_60081d4c)` — i.e. **process events, then refresh the display**, both on the UI context
objects `_DAT_60081d48` / `_DAT_60081d4c`.

## RENDER — `0x6004B514` (display driver)

Strong evidence this is the screen refresh:

- It brackets its critical section with **NVIC registers**: reads `_DAT_e000e108` (NVIC ISER, `0xE000E100`),
  writes `_DAT_e000e188` (NVIC ICER, `0xE000E180`) to **mask IRQ #0x40 while touching the framebuffer**, then
  restores it — the classic "don't let the display DMA/SPI interrupt fire mid-draw" pattern.
- It runs a **loop of 8** (tracks/columns), queries the **active view's** vtable `+0x1C` / `+0x18`, and calls
  slot `+0xA0` on the object held at `DAT_6004b734`.
- Gated at ~15 ms (`0xf < elapsed`) → the frame timer.

*Correction:* that `+0xA0` is **not** a view method. The base `View` vtable has only 8 slots
([static-m8-ui.md](static-m8-ui.md)); `+0xA0` belongs to one of the large parameter-object classes (46–109
slots, likely the instrument engines / FX objects).

**Hook (primitive #4):** detour the `bl 0x6004B514` in `loop()` for a whole-frame RENDER event. For per-view
drawing, the view's own draw slot is `+0x0C` or `+0x10` (to confirm); text overlays can wrap `0x60030ECC`.

## INPUT / view-update — `0x6004C6C8` (candidate)

Runs immediately before the flush: takes `(param_1 = UI context, param_2 = event code)`, tests
`param_2 == 0xE4`, reads a key/state field at `param_1[0x15]`, and gates on a **bitmask lookup**
`(_DAT_6004c8f4 >> key) << 0x1f` ("is this key/state in a set"), then dispatches through a jump table. This is
the **event → view-update** stage and the best INPUT candidate.

**Resolved downstream:** the input action ends up at the **current view's vtable slot `+0x08`** — 19 per-view
input handlers are confirmed there ([static-m8-ui.md](static-m8-ui.md)). The raw key/encoder read (expected to
touch GPIO, `0x401xxxxx`) is still not among `loop()`'s direct callees, so it is deeper or interrupt-driven.

## What this unlocks

| event | site | status |
|---|---|---|
| RENDER (frame) | `bl 0x6004B514` in `loop()` | S2 — ready to bind |
| RENDER (per view) | view vtable `+0x0C` / `+0x10` | S3 — which slot to confirm |
| INPUT | router `0x6004C6C8`; per view vtable `+0x08` | S1 for `+0x08`, S2 router |
| VIEW_CHANGE | `set_view` `0x6004C13C` | S1 ([static-m8-ui.md](static-m8-ui.md)) |
| TOUCH | `0x600A5E60` | S2 |
| sequencer (row fire, tick) | not reached from `loop()` — most likely the audio-update interrupt | open |

Nothing here has run on hardware.
