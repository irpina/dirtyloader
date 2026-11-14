# Sites log (M8)

Every firmware hook site found for a dirtyloader hook bus, in one place. Same method and confidence scale as
the Elekloader kit's `notes/manual-catalog/events/SITES.md`: code-only hunts log their sites here, and a core
PR takes its sites from this log and confirms them in one batch (on the Teensy). Targets come from
`docs/manual-catalog/m8/SUMMARY.md`.

Firmware: **M8 6.6.2A Model02** (stock sha256 `fbc15296…`). Addresses are flash addresses (image base
`0x60000000`); file offset = address - 0x60000000 + 0x200.

**Confidence:** **E** seen firing (emulator: none for the M8); **H** on hardware (only when the user says so);
**S1** decompile + strings + callers agree and a second independent line of evidence (e.g. the case-count
fingerprint) agrees; **S2** decompile, strings and callers agree; **S3** a lead. Never raise a row without new
evidence; mark contradicted rows `superseded`.

## `ev_fx_command`: the FX-command bus ([static-m8-fxcmd.md](static-m8-fxcmd.md))

Command encoding (from the name lookup): `0xFF` empty; `0x00..0x4D` the 78 global commands (sequencer, mixer,
send effects, master); `0x80 | n` instrument command `n`, routed through the current instrument object's
vtable.

### Data and calls (not sites)

| what | address | conf | notes |
|---|---|---|---|
| global command name table | 0x601D6FD8 | S1 | 78 x 4-byte slots, ids 0x00 ARP .. 0x4D MTT; long-name/help table follows at 0x601D7118 |
| command name lookup | 0x6008C4A4 | S2 | (_, cmd) -> name; 0xFF none; cmd < 0x4E -> table; 0x80+ -> instrument vtable +0xA4 (count at +0xD4) |
| command help/long-name lookups | 0x6008C578, 0x6008C658 | S2 | same split; the second is used by the help view path |
| command value formatter | 0x6005ED66 | S2 | (_, cmd, value, rel) -> display text; 78-case `tbh` at 0x6005EE1E; instrument cmds via vtable +0xC8. UI only, NOT the executor |
| total command count | 0x60029B3C | S2 | 0x4E + instrument vtable +0xD4 |
| command property helpers | 0x60029B5C, 0x60029B7C, 0x60029BB4, 0x60029BDC | S3 | instrument cmds via vtable +0x118 / +0xC0; pitch-command (0x0C..0x0F) handling; exact meaning unread |
| **executor** (global/track cmds) | **0x600287A4** | **S1** | the 78-way dispatch: `cmp r8,#0x4D` + `tbh [pc,r8]` at 0x60028802; cmd id in r8/r2. 26 cmds handled in-function, 52 route to default 0x60028BCA (sibling executors). Full map: [static-m8-fxcmd.md](static-m8-fxcmd.md) |
| per-command jump table | 0x60028806 | S1 | 78 × u16; `target = 0x60028806 + 2·entry`; decoded |
| per-slot FX scan loop | 0x60029AA4 | S2 | walks a track's command column (body from 0x60029AD2); per slot calls the ratchet + the dispatch wrapper |
| command dispatch wrapper | 0x60029270 | S1 | called per slot by the scan loop; **calls the executor 0x600287A4** (confirmed Ghidra call ref) |
| ratchet / retrigger tick | 0x60028700 | S2 | per-slot counter at +0x78; resets slot on cmd==0x10. **NOT** the executor (supersedes the earlier lead) |
| pitch-command helper | 0x60029BDC | S2 | holds the `tbb` at 0x60029C08: bias 0x0C, 4 cases = PSL/PBN/PVB/PVX. **Not** a sibling executor (supersedes) |
| row-fire FX applier | 0x60025ED4 (run 0x24854) | S2 | called by row fire 0x24DE0 once per FX column (0,1,2); 72-case (cmds 0x00..0x47). *Superseded: first logged as the per-tick side* |
| row fire / note trigger | 0x60026460 (run 0x24DE0) | S2 | note, instrument, volume, then FX columns via 0x24854 |
| sequencer clock node | 0x60023DA0 (run 0x22720) | S1 | AudioStream `update()`: double phase accumulator → ticks; runs in the audio IRQ |
| mixer/send cmds 0x1C..0x40 | — | S3 | no switch anywhere is biased 0x1C / bounded 37 ([census](static-m8-switches.md)) → data-indexed, not switched |

### Sites

| site | event / call | conf | notes | report |
|---|---|---|---|---|
| 0x600287A4 | `ev_fx_command`: a global/track command fires | S1 | detour the executor entry (or the `bl` to it inside 0x60029270); handler gets the command id (r8/r2) before the 78-way `tbh`. observe / veto / re-range / extend. [static-m8-fxcmd.md](static-m8-fxcmd.md) | (HW pending) |

## `loop()` per-frame subsystems ([static-m8-loop.md](static-m8-loop.md))

`main()` (0x600AE04C) confirmed: `setup(); while(1){ loop(); yield(); }`. `loop()` (0x60081BD4) is a
cooperative scheduler — subsystem groups behind timing gates, not a flat list.

### Data and calls (not sites)

| what | address | conf | notes |
|---|---|---|---|
| touch / gesture engine | 0x600A5E60 | S2 | unconditional each frame; touch dx/dy/x/y → per-view handlers. *Superseded: first logged as a sequencer "TICK engine".* See the UI section below |
| ~5 ms service group | 0x60081A90 | S2 | 6 subsystems (0x6007CBFC, 0x6007D23C, 0x6007C9E4, 0x6007BFB8, 0x60079A7C, 0x60039964) |
| UI-frame gate | 0x6008196C | S2 | returns a byte behind a ~10 ms gate; `loop()` branches on it for the UI frame |
| GPIO6 read | 0x6007BBB4 | S2 | a button/pin read (GPIO6). *Superseded: first logged as a micros() timer* |
| watchdog kick | 0x60081958 | S2 | WDOG1 |
| display SPI driver | 0x6008D920 | S2 | LPSPI4 — where pixels reach the panel |
| ~~view draw vtable slot +0xA0~~ | — | superseded | `+0xA0` is not a view method (the `View` vtable has 8 slots); it is on a large parameter-object class |

### Sites

| site | event / call | conf | notes | report |
|---|---|---|---|---|
| 0x6004B514 | `ev_render`: UI frame refresh (whole frame) | S2 | last step of `loop()`'s UI branch, ~15 ms gate; its NVIC bracket is the audio lock (IRQ 70), not a display IRQ; pixels go out via LPSPI4 0x6008D920. Detour `bl 0x6004B514` in `loop()`. [static-m8-loop.md](static-m8-loop.md) | (HW pending) |
| 0x6004C6C8 | `ev_input` (global): the input router | S2 | runs just before the flush; action code in r1; the action reaches the current view's vtable `+0x08` (below) | (HW pending) |

## UI framework ([static-m8-ui.md](static-m8-ui.md))

### Data and calls (not sites)

| what | address | conf | notes |
|---|---|---|---|
| UI context fields | ui+0x04 / +0x15 / +0x17 / +0x2D | S1 | current view object / **current view id** / previous id / nav group |
| `View` vtable (base, 8 slots) | e.g. 0x601DFDC8 | S1 | `+0x00` enter, `+0x08` input, `+0x0C`/`+0x10` view-specific (draw candidates), `+0x14` leave, `+0x18`/`+0x1C` queries; 26 such classes + 5 32-slot list views |
| per-view input handlers | 19 × slot `+0x08` | S1 | `(this, action)` switches; list with true entries in the ui doc |
| text-draw wrapper | 0x60030ECC | S2 | → glyph renderer 0x6002E2A8 (ASCII 0x20..0x7A); second font 0x6002FDEC |
| value formatter | 0x600785C0 | S2 | printf-style: format codes `'b'..'x'`, draws via 0x60030ECC |
| parameter-object classes | 7 × 102–109 slots, 5 × 46 | S3 | shared base `+0x88/+0x90/+0x94` (0x6009B994/9C/A0), each overrides `+0xA0`. 7 = the M8's instrument types (hypothesis) |
| RAM vector table | 0x2000C000 | S1 | 176 entries, filled at boot; IRQ 70 audio, 110 SD, 157 buttons, 92 watchdog attached at run time ([map](../FIRMWARE-MAP.md) §6). *Supersedes "IRQ vector template 0x601E9A38"* — that is a 128-entry callback table of unknown purpose |
| instrument classes | 7 vtables (102–109 slots) | S1 | named by their own name methods: WAVSYNTH 0x601DFE18, MACROSYNTH 0x601E0220, SAMPLER 0x601E07EC, MIDI OUT 0x601DFBBC, FMSYNTH 0x601DF97C, HYPERSYNTH 0x601E0058, EXTERNAL 0x601E0A14 |
| parameter descriptor tables | 8 tables, 254 params | S1 | [static-m8-params.md](static-m8-params.md) |

### Sites

| site | event / call | conf | notes | report |
|---|---|---|---|---|
| 0x6004C13C | `ev_view_change`: `set_view(ui, id)` | S1 | leave old (`+0x14`) → `ui+0x15 = id` → 30-way id→singleton switch → enter new (`+0x00`). Observe / veto / route a **new id** to a mod view (the KAOSS screen) | (HW pending) |
| view vtable `+0x08` | `ev_input` (per view) | S1 | wrap one view's input handler (copy its vtable to a cave, repoint the singleton) | (HW pending) |
| 0x600A5E60 | `ev_touch`: touch / gesture frame | S2 | dx/dy at +0x30/+0x34, x/y at +0x40/+0x44, dominant axis; per-view handlers (view 0x12 → 0x60067744 gets x, y, axis) | (HW pending) |
| 0x60030ECC | `ev_draw_text` | S2 | every string drawn goes through it — overlays, re-labelling | (HW pending) |
