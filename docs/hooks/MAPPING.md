# Firmware mapping backlog (M8 6.6.2A Model02)

What is mapped, what is left, and in what order to attack it. **The whole-firmware picture is
[../FIRMWARE-MAP.md](../FIRMWARE-MAP.md)** — read that first; this file tracks hook-relevant progress against
[SITES.md](SITES.md) and [../manual-catalog/m8/SUMMARY.md](../manual-catalog/m8/SUMMARY.md) (the 600-target
manual catalog and its 7 high-value primitives). Addresses are load addresses in the flash image unless marked
"run". Re-derive per firmware version — every address here moves between releases.

## A. The skeleton — solid ground

The deterministic reset path is pinned and the Core rides on it:

```
entry 0x60001649 → startup 0x60001430 → main 0x600AE04C
main(): setup(); while (1) { loop(); yield(); }
         0x60082374        0x60081BD4   0x600B4DC0
```

Mapped: the M8FW container + CRCs, the code-cave survey, and the two Core hook sites — `bl setup` at
`0x600AE04E` (BOOT) and `bl loop` at `0x600AE052` (TICK). See [CORE.md](CORE.md). Everything below hangs off
`loop()`.

## B. The two walls

Every remaining target sits behind one of two walls, and which one decides whether it is tractable:

- **Structural wall — tractable, software-only.** Dispatch / switch code, found by following the call graph
  and table-branches (`tbh`/`tbb`). This is how the FX executor fell ([static-m8-fxcmd.md](static-m8-fxcmd.md)).
  Everything in the "ready now" list below lives here.
- ~~**Data-indirection wall — blocked.**~~ **Resolved: it was a relocation.** The parameter / label tables
  live in `.data`, which Teensy copies to DTCM at boot, so they are referenced only by `0x2000xxxx` run-time
  addresses; translated, they have ordinary references ([../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §1,
  [static-m8-params.md](static-m8-params.md)). The same mistake hid the ITCM code (the sequencer and audio
  graph run at `0x0000xxxx`). Lesson: get the run-time memory map right before concluding anything is
  unreachable.

## C. The 7 high-value primitives (catalog priority list)

| # | Primitive | Status | Anchor / lead | Unlocks | Wall |
|---|---|---|---|---|---|
| 1 | FX command dispatch | 🟢 executor **mapped** (`0x600287A4`, caller `0x60029270` confirmed); 2nd processor `0x60025ED4` | pitch helper `0x60029BDC`; mixer cmds not switch-dispatched | FX commands **69** | structural |
| 2 | Parameter descriptor table + change event | 🟢 **tables mapped** (8 tables, 254 params); change event open | [static-m8-params.md](static-m8-params.md); instrument interface `+0xBC` descriptor, `+0x108` default, `+0x10C` value | param tables 43, param edit 30 | structural |
| 3 | Key/input event + view context | 🟢 **mapped** | router `0x6004C6C8`; **per-view vtable `+0x08`** (19 handlers); `set_view` `0x6004C13C`; view id at `ui+0x15` | UI input 41, performance 12 | structural |
| 4 | Draw hook per view (RENDER) | 🟢 frame driver mapped; per-view slot open | `0x6004B514`; view `+0x0C`/`+0x10`; text `0x60030ECC`, values `0x600785C0` | screen 33, draw 33 | structural |
| 5 | Modulator dest table + apply | 🟢 **dest lists + counts mapped** (all 7 engines); apply step open | `+0x104` count, `+0x0F8` name table; modulators at data `+0x30..+0x47`; voices in ITCM | the **LFO mod**; voice render 34 | structural |
| 6 | Master-chain + touch-axis | 🟡 **touch mapped**; master chain unmapped | touch engine `0x600A5E60` (x/y/dominant axis, per view) | the **KAOSS mod** | structural |
| 7 | Row-fire / tick / transport / MIDI / storage | 🟢 **sequencer mapped**: clock node `0x22720`, row fire `0x24DE0`, per-tick executor (run addrs) — all in the audio IRQ | transport/MIDI/storage partly ([../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §3, §5) | ~130 rows across areas | structural (ITCM, audio thread) |

## D. `loop()` — decomposed ([static-m8-loop.md](static-m8-loop.md))

`loop()` (`0x60081BD4`) turned out to be a **cooperative scheduler**: subsystem groups behind timing gates,
not a flat list. Mapped this pass:

- **RENDER = `0x6004B514`** — the UI frame refresh (~15 ms gate; pixels leave via LPSPI4 `0x6008D920`). S2.
- **INPUT router = `0x6004C6C8`**, feeding the current view's vtable `+0x08`. S2 / S1.
- **TOUCH = `0x600A5E60`** — the touch/gesture engine (*not* a sequencer engine, as first logged). S2.
- Scheduler scaffolding: `0x60081A90` (~5 ms service group, 6 callees), `0x6008196C` (UI-frame gate),
  `0x6007BBB4` (µs read).

The UI framework behind it — `set_view`, the 8-slot `View` interface, per-view input handlers, the touch
engine, text/value drawing — is in [static-m8-ui.md](static-m8-ui.md). The sequencer is **not** called from
`loop()` at all.

## D2. The tools that made this fast

- **Switch census** (`python -m dirtyloader.re.switches`) — every `tbb`/`tbh` by encoding, with bound, bias and
  decoded targets; case-count + bias identify a switch without strings. 140 in 6.6.2A.
  ([static-m8-switches.md](static-m8-switches.md))
- **Vtable finder** (`python -m dirtyloader.re.vtables [--find addr…]`) — `{0,0}`-headed code-pointer runs =
  the class hierarchy; locating a function gives its virtual slot and its *true* entry. 61 vtables in 6.6.2A.

Both are byte-level, so they work on the parts of the image Ghidra's auto-analysis never reaches, and both
re-run unchanged on a new firmware build.

## E. The backlog, ordered by tractability

**Ready now (structural, no hardware):**

1. ~~Decompose `loop()`~~ **done**; ~~view framework~~ **done** (`set_view`, `View` vtable, input `+0x08`,
   touch engine). Follow-up: which of view `+0x0C`/`+0x10` draws.
2. **Parameter-object virtual interface** — decompile the shared `+0x88/+0x90/+0x94` (`0x6009B994/9C/A0`) and
   one instrument class's `+0xA0`; match the 7 big vtables to the 7 instrument types. *This is the most
   promising route to primitives 2 and 5 (param editing, LFO destinations).*
3. **FX default path** — the executor's default `0x60028BCA` (mixer/send commands, data-indexed?) and the
   second processor `0x60025ED4`.
4. **Instrument-command executor** (`0x80|n` via the instrument vtable) → instrument FX commands.
5. **Sequencer entry** — find who calls the scan loop `0x60029AA4`: the audio-update ISR, attached at runtime
   (search for writes into the RAM vector table / `attachInterruptVector`-style setup).
6. **MIDI in/out dispatch** (`0x6008A178` / `0x60089C80` are leads), storage/boot events.

**Blocked (interactive Ghidra or hardware):**

7. The parameter *label* tables themselves (RAM-indirected) — less important if item 2 pans out.
8. Audio-block / voice render (AUDIO_BLOCK) — interrupt/DMA-driven, hard statically.
9. Master chain for KAOSS (stage list / bypass / reorder) — touch is mapped, the chain is not.

## F. By the numbers

600 manual targets. Mapped dispatch points: the **FX executor** (69 rows), the **display driver** (screen 33 +
draw 33), **`set_view` + per-view input** (UI input 41, performance 12), and the **touch engine** (the KAOSS
mod's input). Six of the seven primitives now have a concrete anchor.

The honest summary: the UI side, the parameter model and the LFO destination lists are mapped; the sequencer
is located (an audio-graph node in the audio interrupt). The remaining unknowns are **which audio node is which
effect** (fastest on hardware, via per-node CPU counters), **the LFO apply step** in the audio thread, and
the eight screens without strings. See [../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §11.
