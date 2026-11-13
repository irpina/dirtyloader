# Firmware mapping backlog (M8 6.6.2A Model02)

What is mapped, what is left, and in what order to attack it. A living companion to
[SITES.md](SITES.md) (the site log) and [../manual-catalog/m8/SUMMARY.md](../manual-catalog/m8/SUMMARY.md)
(the 600-target manual catalog and its 7 high-value primitives). Addresses are flash addresses (image base
`0x60000000`). Re-derive per firmware version — every address here moves between releases.

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
- **Data-indirection wall — blocked.** The parameter / label / modulation tables are reached through a
  RAM-copied base pointer plus a computed offset, so byte-scans and Ghidra's static xrefs both return nothing
  (four passes confirmed this; see [MODULATION.md](../MODULATION.md)). Bridging it needs *interactive* Ghidra
  (define the base global by hand and follow the value) or *hardware* (poke and observe). No amount of one-shot
  scripting crosses it.

## C. The 7 high-value primitives (catalog priority list)

| # | Primitive | Status | Anchor / lead | Unlocks | Wall |
|---|---|---|---|---|---|
| 1 | FX command dispatch | 🟢 sequencer executor **mapped** (`0x600287A4`); siblings left | names/fmt/count tables + executor done; `tbb 0x60029C08` + 52 default cmds | FX commands **69** | structural |
| 2 | Parameter descriptor table + change event | 🔴 blocked | label region `0x601E3C00–0x601E5E00` known; table/site not found | param tables 43, param edit 30 | **indirection** |
| 3 | Key/input event + view context | 🔴 unmapped | inside `loop()` | UI input 41, performance 12, touch | structural |
| 4 | Draw hook per view (RENDER) | 🔴 unmapped | `loop()` render-gate (`func_0x6008196c` → `FUN_60030ecc`) | screen 33, draw 33 | structural |
| 5 | Modulator dest table + apply | 🟡 labels only; apply blocked | dest enum `0x601E3D24`, names `0x601E4214` | the **LFO mod**; voice render 34 | **indirection** |
| 6 | Master-chain + touch-axis | 🔴 unmapped | track table `0x601CFDD4` | the **KAOSS mod**; needs #3+#4 | structural |
| 7 | Row-fire / tick / transport / MIDI / storage | 🟡 BOOT+TICK only | all inside `loop()` | ~130 rows across areas | structural |

## D. `loop()` is the master key

Five of the seven primitives (3, 4, 6, 7) gate on one thing: **decomposing `loop()`'s ~15 per-frame subsystem
calls** (`0x60081BD4`). Its decompile already shows a render-gate branch and a USB/event veneer; the bindings
file notes two partial subsystem entries (`0x6007BBB4`, `0x6007C6C0`). Isolating those calls would hand over
RENDER, INPUT, transport, row-fire and tick timing in a single pass. Highest-leverage unmapped target, and
software-only.

> Caveat: the RENDER/INPUT leads come from one messy `loop()` decompile — they are directions, not pinned
> sites, until a focused pass down the call tree confirms each subsystem.

## E. The backlog, ordered by tractability

**Ready now (structural, no hardware):**

1. **Decompose `loop()`** → RENDER, INPUT, transport, row-fire, tick (biggest unlock).
2. **Sibling FX executors** → the 52 default-routed mixer/send/DJ/I2C commands + the `tbb` at `0x60029C08`.
3. **Instrument-command executor** (`0x80|n` via the instrument vtable) → instrument FX commands.
4. **MIDI in/out dispatch**, storage/boot events.

**Blocked (interactive Ghidra or hardware):**

5. Parameter descriptor table + param-change event (primitive 2).
6. Modulation apply + per-engine dest arrays — **the LFO mod's gate** (primitive 5).
7. Audio-block / voice render (AUDIO_BLOCK) — interrupt/DMA-driven, hard statically.
8. Touch-axis + master chain for KAOSS — needs input + draw mapped first.

## F. By the numbers

600 manual targets; structural coverage was ~0 until the FX executor landed — the **first real dispatch hook
mapped**, addressing the single largest area (69 rows). The next pass on `loop()` would be the first to touch
the UI/transport majority (~180 rows).

The honest summary: **~85% of the hookable surface is still unmapped, but most of it is the *tractable* kind** —
behind `loop()`'s call tree and a few more switch tables, not behind the indirection wall. Only the parameter
and modulation tables (primitives 2 and 5) are genuinely stuck until interactive RE or the Teensy.
