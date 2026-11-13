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
| 3 | Key/input event + view context | 🟡 candidate located | `0x6004C6C8` (event code in r1, key at ctx+0x15) | UI input 41, performance 12, touch | structural |
| 4 | Draw hook per view (RENDER) | 🟢 **display driver mapped** | `0x6004B514` (NVIC-guarded) + view vtable `+0xA0` | screen 33, draw 33 | structural |
| 5 | Modulator dest table + apply | 🟡 labels only; apply blocked | dest enum `0x601E3D24`, names `0x601E4214` | the **LFO mod**; voice render 34 | **indirection** |
| 6 | Master-chain + touch-axis | 🔴 unmapped | track table `0x601CFDD4` | the **KAOSS mod**; needs #3+#4 | structural |
| 7 | Row-fire / tick / transport / MIDI / storage | 🟡 engine located | `0x600A5E60` (24-call TICK engine); subtree unmapped | ~130 rows across areas | structural |

## D. `loop()` — decomposed ([static-m8-loop.md](static-m8-loop.md))

`loop()` (`0x60081BD4`) turned out to be a **cooperative scheduler**: subsystem groups behind timing gates,
not a flat list. Mapped this pass:

- **RENDER = `0x6004B514`** — the display driver (NVIC-guarded framebuffer, per-view vtable `+0xA0` draw,
  ~15 ms gate). The one clean, evidence-backed UI site so far. S2.
- **INPUT candidate = `0x6004C6C8`** — the event/view-update stage before the flush (event code in r1, key at
  ctx+0x15, bitmask dispatch). S3 — input-routing vs. view-build still to confirm.
- **TICK engine = `0x600A5E60`** — the unconditional 24-call per-frame engine; transport / row-fire / groove
  live in its (unmapped) subtree.
- Scheduler scaffolding: `0x60081A90` (~5 ms service group, 6 callees), `0x6008196C` (UI-frame gate),
  `0x6007BBB4` (µs read).

Still open from here (software-only): the view-object **vtable layout** (for a per-view draw hook), the
`0x6004C6C8` jump-table arms (confirm INPUT), and the `0x600A5E60` subtree (transport/row-fire).

## E. The backlog, ordered by tractability

**Ready now (structural, no hardware):**

1. ~~Decompose `loop()`~~ **done** → RENDER mapped (`0x6004B514`), INPUT candidate (`0x6004C6C8`), TICK engine
   (`0x600A5E60`). See [static-m8-loop.md](static-m8-loop.md). Follow-ups:
   - the view-object **vtable layout** (per-view draw hook at `+0xA0`);
   - `0x6004C6C8`'s jump-table arms (confirm INPUT vs. view-build);
   - the `0x600A5E60` subtree (transport, row-fire, groove, tick).
2. **Sibling FX executors** → the 52 default-routed mixer/send/DJ/I2C commands + the `tbb` at `0x60029C08`.
3. **Instrument-command executor** (`0x80|n` via the instrument vtable) → instrument FX commands.
4. **MIDI in/out dispatch**, storage/boot events.

**Blocked (interactive Ghidra or hardware):**

5. Parameter descriptor table + param-change event (primitive 2).
6. Modulation apply + per-engine dest arrays — **the LFO mod's gate** (primitive 5).
7. Audio-block / voice render (AUDIO_BLOCK) — interrupt/DMA-driven, hard statically.
8. Touch-axis + master chain for KAOSS — needs input + draw mapped first.

## F. By the numbers

600 manual targets. Two dispatch hooks are now mapped: the **FX executor** (69 rows) and the **RENDER display
driver** (screen 33 + draw 33). With `loop()` decomposed, the INPUT and TICK-engine anchors are located too —
so the UI/transport majority (~180 rows) has first anchors, pending the subtree passes.

The honest summary: **~85% of the hookable surface is still unmapped, but most of it is the *tractable* kind** —
behind `loop()`'s call tree and a few more switch tables, not behind the indirection wall. Only the parameter
and modulation tables (primitives 2 and 5) are genuinely stuck until interactive RE or the Teensy.
