# The dirtyloader Core

> **The event design — the hook bus's events, prototypes, sites, tables and firmware locations, modelled on
> Elekloader's — is [CORE-EVENTS.md](CORE-EVENTS.md).** This file is the Core's mechanism.

The **Core** is injected firmware infrastructure that lets several mods hook the
same piece of M8 firmware without fighting over the bytes. It is the direct
analogue of Elekloader's *core mod + event bus*: instead of each mod overwriting
a call site (and the last one winning), mods **register handlers** against named
**events**, and the Core's **dispatcher** runs every registered handler at each
hooked site.

In dirtyloader terms the Core ships as a special mod with `id: "core"`; other
mods set `requires: ["core"]` (the linker already enforces that).

```
   stock call site                 Core dispatcher (in a code cave)
   ───────────────                 ────────────────────────────────
   ... bl original  ──patched──►   save context
                                   for each entry in hook table where
                                       entry.event == THIS_EVENT and enabled:
                                       call entry.handler
                                   run the relocated original instruction(s)
                                   restore context, return
```

## What we already know (6.6.2A Model02)

Established by the RE pass (`dirtyloader.re.boot`, `dirtyloader.re.caves`):

| Fact | Value | Why it matters for the Core |
|---|---|---|
| Integrity | two zlib **CRC-32s only**, no signature | the loader recomputes them, so a Core-patched image boots |
| Image | flat FlexSPI image @ `0x60000000`, Thumb | standard Cortex-M7; capstone/Ghidra analyze it cleanly |
| Entry | `0x60001649` (ResetHandler) | the `BOOT` event hooks late in startup, after init |
| HAB `csf` | points at `0x601EA400`, which is **all zeros** | no real signature present; unsigned image (confirm on HW) |
| Biggest cave | `0x60000200`, **3584 B** of `0xFF` (FCFB page tail) | home for the dispatcher + handler table |
| Spare caves | `0x6000102C` (980 B), `0x601EA400` (3072 B) | overflow / per-mod trampolines |
| Total free | ~12 KB across 12 caves ≥256 B | **tight** — code budget is the main constraint |

The provisional memory layout and event ids are in
[`dirtyloader/core/abi.py`](../dirtyloader/core/abi.py).

## Hook map (6.6.2A Model02)

Ghidra mapped 1630 functions but the image is **stripped** (no symbols) and UI
strings are reached by computed index (no static xref), so hook points are found
structurally by following the deterministic reset path with
[`dirtyloader.re.trace`](../dirtyloader/re/trace.py) (capstone, no Ghidra needed):

```
IVT.entry 0x60001649 → startup 0x60001430 → main 0x600AE04C
main(): setup(); while (1) { loop(); yield(); }
```

| Symbol | Address | Role | Core event |
|---|---|---|---|
| `setup` | `0x60082374` | one-time init | **BOOT** |
| `loop`  | `0x60081BD4` | whole M8 application frame | **TICK** (→ RENDER/INPUT) |
| `yield` | `0x600B4DC0` | Teensy USB/event service (a veneer) | — |

First hook sites (in `main`): patch `bl loop` at **`0x600AE052`** for a per-frame
TICK, or `bl setup` at **`0x600AE04E`** for a one-time BOOT. Addresses for this
exact build are recorded in
[`dirtyloader/core/bindings/m8_6.6.2A_model02.json`](../dirtyloader/core/bindings/m8_6.6.2A_model02.json);
RENDER/AUDIO/INPUT events require descending into `loop()`'s ~15 per-frame
subsystem calls in Ghidra (the next RE step).

## Design

### 1. Reserved region & table
The Core occupies `CORE_REGION_ADDR` (`0x60000200`). Layout:

```
+0x000  CORE_MAGIC  "DLCORE\0\1"      (detect + version)
+0x008  table_count : u16
+0x00A  dispatcher_addr : u32         (so mods can call it / verify)
+0x010  hook table: MAX_HOOKS × { event_id:u16, flags:u16, handler:u32 }
...     dispatcher code (Thumb)
```

### 2. Hooking mechanism (detour + trampoline)
At a chosen site we overwrite one 32-bit Thumb instruction (typically a `BL`/
`B.W`) with a branch to a per-site **trampoline** in a cave. The trampoline:
1. branches into the shared dispatcher with the event id,
2. the dispatcher calls each registered handler,
3. executes the **relocated** original instruction (fixed up for its new PC),
4. returns to just after the patched site.

Thumb specifics the Core builder must handle: 2- vs 4-byte instruction
boundaries, PC-relative operands in the relocated instruction, and preserving
`lr` across the detour. `B.W`/`BL` reach ±16 MB — easily enough to reach the
caves from anywhere in the 2 MB image.

### 3. Events & registration
`abi.Event` fixes the numeric event ids (stable ABI). The *addresses* each event
hooks are **bound per firmware** after Ghidra identifies the functions (main
loop, display render, audio block, input) and recorded in the Core mod's own
manifest — not hard-coded in the library. A mod registers by adding a hook-table
entry (event id + its handler address); the Core mod installs the dispatcher and
the empty table.

### 4. Loader integration
- The Core is a normal `.m8mod` (`id: "core"`) pinned to a stock sha256.
- Mods depend on it via `requires: ["core"]`.
- The linker's overlap/conflict/expect checks already prevent two mods from
  corrupting the table or the same trampoline slot.
- A future `core`-aware step assigns handler-table slots so mods don't collide.

## Build order

1. **Function map & hook points** — *done.* 1630 functions via Ghidra
   (`dirtyloader.re.ghidra_export`); `main`/`setup`/`loop`/`yield` pinned via
   `dirtyloader.re.trace`. See the hook map above.
2. **First hook + dispatcher** — *done.* `dirtyloader.core.builder` assembles the
   dispatcher + trampoline + event table (keystone) into `0x60000200`, detours
   the `TICK` site at `0x600AE052`, and emits `mods/core.m8mod`. CRCs recompute
   via `m8fw`; `dirtyloader.core.test_core` disassembles the installed bytes to
   confirm every instruction. Ships a bundled no-op demo handler on TICK.
3. **Validate on a spare Teensy 4.1 + M8 Headless firmware** — *done for core 0.2's
   BOOT and TICK sites (see "Core 0.2" below).* Never on a real M8 until proven. Re-run `re.trace` on the Headless
   build for its addresses (the Model02 `.bin` expects full M8 hardware and will
   stall on a bare board). The HalfKay bootloader is untouched, so stock recovers.
4. **A real handler** — replace the no-op demo with a visible effect (e.g. draw
   to the display via a `loop()` subsystem) once hooks there are mapped.
5. **Generalise** — *slot allocation is done:* a mod declares `hooks: [{event,
   handler}]` and the linker auto-assigns a free Core table slot per hook, so
   several mods share one event (`dirtyloader.core.test_hooks` proves 3 handlers on
   TICK). `requires: ["core"]` is enforced. Remaining: a mod-author macro for
   "register handler for event X", and resizable images for larger mods.

## Core 0.2 (first build: M8 Headless 6.6.4A)

`builder.build_core02(fw, bindings)` assembles the hook bus of [CORE-EVENTS.md](CORE-EVENTS.md) from a
firmware's `bindings/<fw>.json` `"core"` block. Region layout at `0x60000200`: magic `DLCORE\0\1`, u16 layout
`2`, u16 slots `64`, u32 dispatcher address (Thumb), the 64-slot table (empty: the linker fills it in
`(order, mod id)` order, so table order is call order), then the code.

| piece | what it does |
|---|---|
| dispatcher | `ip` = event id \| `0x10000` if takeable; passes r0–r3 and s0 to every enabled handler of that event, in table order; for a takeable event, stops at the first nonzero return and returns it, else 0. Frames are 8-byte multiples |
| `call_pre` site | a `bl target` → `bl stub`: handlers first, then `b.w target` (or return 0 if taken). TICK |
| `call_post` site | a `bl target` → `bl stub`: `target()`, then the handlers. BOOT |
| `entry` site | a function's first ≥ 4 bytes → `b.w stub`: handlers, then the **relocated prologue** and `b.w fn+n`. `relocate_prologue` copies plain instructions, turns `ldr rX,[pc,#imm]` into `movw/movt` of the literal, and refuses branches, other pc reads, and any branch back into the replaced bytes. TEMPO |

The headless build is not the Model:02 6.6.2A build: `main` is at `0x600A28F8` (BOOT `bl setup` at
`0x600A28FA`, TICK `bl loop` at `0x600A28FE`), and the clock is no longer a fixed global. `set_tempo` is
`0x60090978`, which keeps bpm at `+0x3C0` of an object reached through the pointer at `0x2001E5C4`. Its
bindings, including `millis` (`0x20040264`, from the SysTick ISR), are in
[`bindings/m8_6.6.4A_headless.json`](../dirtyloader/core/bindings/m8_6.6.4A_headless.json). The headless
firmware ships as Intel HEX: [`dirtyloader/ihex.py`](../dirtyloader/ihex.py) reads it into a flat image
(model 0, device `m8-headless`) and writes a patched one back, including bytes in caves the stock file skipped.

**Smoke test.** `python -m dirtyloader.core.build_headless <M8_V6_6_4A_HEADLESS.hex> <out>` builds
`core.m8mod`, `led-heartbeat.m8mod` and a linked `.hex` (844 bytes changed). The LED mod lives in the
`0x6000102C` cave: its `ev_boot` handler makes pin 13 (the onboard LED, GPIO7 bit 3, which this firmware does
not use) an output and lights it, and its `ev_tick` handler double-blinks it from `millis` (two 128 ms flashes
every 1.024 s). Reading the LED:

- **heartbeat:** BOOT and TICK both work
- **solid on:** BOOT ran but TICK did not
- **dark:** the core never ran

A Teensy fresh from the factory runs a plain 1 Hz blink sketch, so only the double-blink counts as a pass.
`tests/test_core02.py` checks the three site kinds, the relocation and the handler order on a synthetic image.

**Passed on hardware (2026-11-16, spare Teensy 4.1).** The board was flashed with tycmd 0.9.9: stock 6.6.4A
first, then the linked `.hex`. The patched firmware enumerates as M8 (serial, audio, MIDI). On `E`, it streams
display frames over serial, and its system-info packet reports headless 6.6.4. Pin 13 double-blinks, so BOOT
and TICK both run. TEMPO (`entry` site) has no visible handler yet and is not exercised.

## Core 0.3: mods from the SD card

Core 0.3 adds a loader: mods are `.m8x` files on the SD card, uploaded over USB and loaded into free ITCM at
boot, with a crash guard. Built and run on a headless Teensy 4.1. Everything about it is in
[LOADER.md](LOADER.md).

## ITCM hook sites need a different detour

About 174 KB of the firmware — the whole audio graph and the sequencer, including the FX-command executor — is
ITCM code: it sits in flash at `0x60001680..0x6002CF50` but is copied at boot to and *runs at*
`0x00000000..0x0002B8D0` ([FIRMWARE-MAP.md](FIRMWARE-MAP.md) §1). Two consequences for the Core:

- A patched instruction there executes at its **run** address, so a `bl` must be encoded relative to the run
  address, and from `0x0002xxxx` the flash cave at `0x60000200` is **out of `bl` range** (±16 MB). Use the
  linker's own long-branch form — `ldr.w pc, [pc, #-0]` + a literal (8 bytes) — or place hook code in **free
  ITCM** (~18 KB above `0x2B8D0`), which needs copying at boot (extend the startup copy, or copy from a flash
  cave in BOOT before the audio graph starts).
- That code runs **inside the audio interrupt** (IRQ 70): handlers there must be fast and must not call UI code.

The existing BOOT/TICK sites (`0x600AE04E`/`0x600AE052`, in `main`) are flash code and unaffected.

## Open risks
- **Code budget.** ~12 KB of caves total; the dispatcher must be compact and
  per-mod code has to fit. Resizable images (growing the payload) are a possible
  future escape hatch but change the container length field.
- **Hook-point stability.** Addresses move every firmware release; the Core mod
  is pinned per build and must be re-derived each version.
- **Thumb relocation correctness** of the displaced original instruction.
- **Hardware enforcement** of HAB/csf — believed inert on open Teensy; must be
  confirmed by actually flashing.
