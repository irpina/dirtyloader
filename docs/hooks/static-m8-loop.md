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
| every frame | **`0x600A5E60`** | 558 | **the main engine — 24 subsystem calls, unconditional each loop.** TICK-rate work: sequencer / transport / voice-follow. Subtree unmapped | S2 |
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
- It runs a **loop of 8** (tracks/columns) and, per item, calls a **view object's vtable slot `+0xA0`**
  (`(**(code **)(*(int *)*puVar5 + 0xa0))()`), plus vtable `+0x1c` / `+0x18` on the active view — a per-view
  **draw dispatch**.
- Gated at ~15 ms (`0xf < elapsed`) → the frame timer.

**Hook (primitive #4):** detour the `bl 0x6004B514` in `loop()` for a whole-frame RENDER event, or wrap the
**view vtable `+0xA0`** for a per-view draw hook (the cleaner surface for a mod that draws its own UI).

## INPUT / view-update — `0x6004C6C8` (candidate)

Runs immediately before the flush: takes `(param_1 = UI context, param_2 = event code)`, tests
`param_2 == 0xE4`, reads a key/state field at `param_1[0x15]`, and gates on a **bitmask lookup**
`(_DAT_6004c8f4 >> key) << 0x1f` ("is this key/state in a set"), then dispatches through a jump table. This is
the **event → view-update** stage and the best INPUT candidate.

**Open:** whether `0x6004C6C8` is input *routing* (key → action) or the view *build* that consumes an already
-decoded key is not yet certain — the raw key/encoder read (expected to touch GPIO, `0x401xxxxx`) is not among
`loop()`'s direct callees, so it is deeper or interrupt-driven. Decompiling `0x6004C6C8`'s jump-table arms and
`0x60081A90`'s six callees is the next step to pin INPUT and the transport/row-fire events.

## What this unlocks

| event | site | status |
|---|---|---|
| RENDER (frame) | `bl 0x6004B514` in `loop()` | S2 — ready to bind |
| RENDER (per view) | view vtable `+0xA0` | S2 — needs the view-object layout |
| INPUT / view event | `bl 0x6004C6C8` in `loop()` | S3 — confirm input vs. build |
| TICK engine (transport, row-fire, groove) | `0x600A5E60` subtree (24 calls) | S3 — subtree unmapped |

Nothing here has run on hardware; the vtable offsets and the input/build question need a confirming pass (or
the Teensy). But RENDER now has a concrete, evidence-backed site.
